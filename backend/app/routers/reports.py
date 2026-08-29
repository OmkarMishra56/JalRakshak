"""
Citizen report ingestion.

Anti-spam / rate-limiting strategy (kept intentionally simple + dependency-light
so it's easy to reason about and swap for Redis-backed limiting at scale):
  1. Per-user rate limit: max `max_reports_per_user_per_hour` (checked when authenticated).
  2. Per-IP rate limit: max `max_reports_per_ip_per_hour` (checked always, catches anonymous spam).
  3. Duplicate suppression: a new report within `report_min_distance_meters` of
     the same user/IP's last report AND within `report_min_interval_seconds`
     is rejected (stops rapid double-taps / bot flooding of one spot).
  4. Geofencing: the report's point MUST fall inside a known zone polygon
     (ST_Contains), otherwise it's rejected -- keeps garbage coordinates out.

On every accepted report we immediately recompute that zone's score and
broadcast over WebSocket if the status changed -- this is what gets updates
to clients in well under 5 seconds.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from geoalchemy2.functions import ST_Contains, ST_SetSRID, ST_Point, ST_DWithin
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Report, Zone, User
from ..schemas import ReportCreate, ReportOut, ReportModerate
from ..auth import get_current_user_optional, require_admin
from ..config import get_settings
from ..scoring import compute_zone_score, apply_score_result
from ..websocket_manager import manager
from ..schemas import ZoneUpdateEvent

router = APIRouter(prefix="/reports", tags=["reports"])
settings = get_settings()


async def _find_zone_for_point(db: AsyncSession, lat: float, lng: float) -> Zone | None:
    point = ST_SetSRID(ST_Point(lng, lat), 4326)
    result = await db.execute(select(Zone).where(ST_Contains(Zone.geom, point)))
    return result.scalars().first()


async def _check_rate_limits(db: AsyncSession, request: Request, user: User | None, lat: float, lng: float):
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    client_ip = request.client.host if request.client else "unknown"

    if user is not None:
        count = (
            await db.execute(
                select(func.count(Report.id)).where(Report.reporter_id == user.id, Report.created_at >= hour_ago)
            )
        ).scalar_one()
        if count >= settings.max_reports_per_user_per_hour:
            raise HTTPException(status_code=429, detail="Too many reports from this account. Please wait before reporting again.")

    ip_count = (
        await db.execute(
            select(func.count(Report.id)).where(Report.source_ip == client_ip, Report.created_at >= hour_ago)
        )
    ).scalar_one()
    if ip_count >= settings.max_reports_per_ip_per_hour:
        raise HTTPException(status_code=429, detail="Too many reports from this network. Please wait before reporting again.")

    # Duplicate/spam suppression: same-ish location within a short interval
    interval_ago = now - timedelta(seconds=settings.report_min_interval_seconds)
    point = ST_SetSRID(ST_Point(lng, lat), 4326)
    dup_query = select(func.count(Report.id)).where(
        Report.created_at >= interval_ago,
        Report.source_ip == client_ip,
        ST_DWithin(Report.location, point, settings.report_min_distance_meters / 111320.0),
        # rough degrees-per-meter conversion at equator; fine for anti-spam purposes
    )
    dup_count = (await db.execute(dup_query)).scalar_one()
    if dup_count > 0:
        raise HTTPException(status_code=429, detail="Duplicate report suppressed. Thanks -- we already logged this spot recently.")


@router.post("", response_model=ReportOut)
async def create_report(
    payload: ReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    await _check_rate_limits(db, request, user, payload.lat, payload.lng)

    zone = await _find_zone_for_point(db, payload.lat, payload.lng)
    if zone is None:
        raise HTTPException(status_code=400, detail="Location is outside any tracked zone")

    client_ip = request.client.host if request.client else None
    report = Report(
        zone_id=zone.id,
        reporter_id=user.id if user else None,
        location=f"SRID=4326;POINT({payload.lng} {payload.lat})",
        lat=payload.lat,
        lng=payload.lng,
        water_depth_cm=payload.water_depth_cm,
        photo_url=payload.photo_url,
        note=payload.note,
        source_ip=client_ip,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    await _rescore_and_broadcast(db, zone.id)
    return ReportOut.model_validate(report)


@router.get("/zone/{zone_id}", response_model=list[ReportOut])
async def list_reports_for_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(Report).where(Report.zone_id == zone_id).order_by(Report.created_at.desc()).limit(50)
        )
    ).scalars().all()
    return [ReportOut.model_validate(r) for r in rows]


@router.patch("/{report_id}/moderate", response_model=ReportOut)
async def moderate_report(
    report_id: str,
    payload: ReportModerate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Municipal admin verifies or dismisses a report -- immediately reweights scoring."""
    report = (await db.execute(select(Report).where(Report.id == report_id))).scalars().first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if payload.action == "verify":
        report.is_verified = True
    elif payload.action == "dismiss":
        report.is_dismissed = True
    else:
        raise HTTPException(status_code=400, detail="action must be 'verify' or 'dismiss'")

    db.add(report)
    await db.commit()
    await db.refresh(report)

    await _rescore_and_broadcast(db, report.zone_id)
    return ReportOut.model_validate(report)


async def _rescore_and_broadcast(db: AsyncSession, zone_id: str):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalars().first()
    if not zone:
        return
    result = await compute_zone_score(db, zone)
    await apply_score_result(db, zone, result)
    await db.commit()

    event = ZoneUpdateEvent(
        zone_id=zone.id,
        code=zone.code,
        name=zone.name,
        score=result.score,
        status=result.status,
        status_changed=result.status_changed,
        updated_at=zone.score_updated_at,
    )
    await manager.broadcast(event.model_dump(mode="json"))
