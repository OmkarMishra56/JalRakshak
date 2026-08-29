"""
Municipal/admin dashboard endpoints: moderation queue, historical analytics
(which zones flood most + rainfall correlation), and CSV export for
infrastructure/drainage planning.
"""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Zone, Report, ZoneScoreHistory, ZoneStatus, User
from ..schemas import ReportOut, ZoneAnalytics
from ..auth import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/reports/pending", response_model=list[ReportOut])
async def pending_reports(db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)):
    """Unverified, non-dismissed reports -- the municipal review queue."""
    rows = (
        await db.execute(
            select(Report)
            .where(Report.is_verified.is_(False), Report.is_dismissed.is_(False))
            .order_by(Report.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [ReportOut.model_validate(r) for r in rows]


@router.get("/analytics", response_model=list[ZoneAnalytics])
async def analytics(db: AsyncSession = Depends(get_db), days: int = 30, _admin: User = Depends(require_admin)):
    """
    'Which zones flood most, correlation with rainfall' -- aggregated per zone
    over the trailing `days` window, driving the admin dashboard's ranked table.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    zones = (await db.execute(select(Zone))).scalars().all()
    out = []
    for z in zones:
        hist = (
            await db.execute(
                select(ZoneScoreHistory).where(
                    ZoneScoreHistory.zone_id == z.id, ZoneScoreHistory.recorded_at >= cutoff
                )
            )
        ).scalars().all()
        scores = [h.score for h in hist]
        severe_count = sum(1 for h in hist if h.status == ZoneStatus.severe)

        report_count = (
            await db.execute(
                select(func.count(Report.id)).where(Report.zone_id == z.id, Report.created_at >= cutoff)
            )
        ).scalar_one()
        verified_count = (
            await db.execute(
                select(func.count(Report.id)).where(
                    Report.zone_id == z.id, Report.created_at >= cutoff, Report.is_verified.is_(True)
                )
            )
        ).scalar_one()

        out.append(ZoneAnalytics(
            zone_id=z.id, name=z.name, code=z.code,
            avg_score_30d=round(sum(scores) / len(scores), 1) if scores else 0.0,
            max_score_30d=round(max(scores), 1) if scores else 0.0,
            severe_incidents_30d=severe_count,
            total_reports_30d=report_count,
            verified_reports_30d=verified_count,
        ))
    out.sort(key=lambda a: a.avg_score_30d, reverse=True)
    return out


@router.get("/export/reports.csv")
async def export_reports_csv(db: AsyncSession = Depends(get_db), days: int = 90, _admin: User = Depends(require_admin)):
    """
    Raw report export for infrastructure/drainage planning -- e.g. feed into GIS
    tooling to prioritize which wards need drainage upgrades.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(Report, Zone.name, Zone.code)
            .join(Zone, Zone.id == Report.zone_id)
            .where(Report.created_at >= cutoff)
            .order_by(Report.created_at.desc())
        )
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "report_id", "zone_code", "zone_name", "lat", "lng", "water_depth_cm",
        "is_verified", "is_municipal_override", "is_dismissed", "created_at",
    ])
    for report, zone_name, zone_code in rows:
        writer.writerow([
            report.id, zone_code, zone_name, report.lat, report.lng, report.water_depth_cm,
            report.is_verified, report.is_municipal_override, report.is_dismissed,
            report.created_at.isoformat(),
        ])
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aquaalert_reports_export.csv"},
    )


@router.get("/dashboard-summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)):
    zones = (await db.execute(select(Zone))).scalars().all()
    severe = [z for z in zones if z.current_status == ZoneStatus.severe]
    moderate = [z for z in zones if z.current_status == ZoneStatus.moderate]
    pending = (
        await db.execute(
            select(func.count(Report.id)).where(Report.is_verified.is_(False), Report.is_dismissed.is_(False))
        )
    ).scalar_one()
    return {
        "total_zones": len(zones),
        "severe_zones": len(severe),
        "moderate_zones": len(moderate),
        "safe_zones": len(zones) - len(severe) - len(moderate),
        "pending_reports": pending,
        "severe_zone_names": [z.name for z in severe],
    }
