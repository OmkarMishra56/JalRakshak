"""
Zone read endpoints: live map data, zone detail (drill-down), and score history
(for the "historical pattern" sparkline / admin analytics charts).
"""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Zone, Report, WeatherSnapshot, ZoneScoreHistory
from ..schemas import ZoneOut, ZoneDetailOut, ReportOut, ZoneScoreHistoryPoint

router = APIRouter(prefix="/zones", tags=["zones"])


def _zone_to_geojson(zone: Zone) -> dict:
    shape = to_shape(zone.geom)
    return mapping(shape)


def _zone_base_dict(zone: Zone) -> dict:
    """
    Build the plain dict ZoneOut needs, including `geojson` (which lives on
    the Zone ORM object only as a WKB geometry, not a field ZoneOut/pydantic
    can pull via model_validate directly -- so we compute it up front rather
    than validating the ORM object as-is and patching the dump afterward).
    """
    return {
        "id": zone.id,
        "name": zone.name,
        "code": zone.code,
        "centroid_lat": zone.centroid_lat,
        "centroid_lng": zone.centroid_lng,
        "current_score": zone.current_score,
        "current_status": zone.current_status,
        "score_updated_at": zone.score_updated_at,
        "geojson": _zone_to_geojson(zone),
    }


@router.get("", response_model=list[ZoneOut])
async def list_zones(db: AsyncSession = Depends(get_db)):
    """Full live snapshot for the map -- called on load, then kept fresh via WebSocket."""
    zones = (await db.execute(select(Zone))).scalars().all()
    return [_zone_base_dict(z) for z in zones]


@router.get("/{zone_id}", response_model=ZoneDetailOut)
async def zone_detail(zone_id: str, db: AsyncSession = Depends(get_db)):
    zone = (await db.execute(select(Zone).where(Zone.id == zone_id))).scalars().first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    recent_reports = (
        await db.execute(
            select(Report)
            .where(Report.zone_id == zone.id, Report.is_dismissed.is_(False), Report.created_at >= cutoff)
            .order_by(Report.created_at.desc())
            .limit(25)
        )
    ).scalars().all()

    latest_weather = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.zone_id == zone.id)
            .order_by(WeatherSnapshot.recorded_at.desc())
            .limit(1)
        )
    ).scalars().first()

    base = _zone_base_dict(zone)
    base["recent_reports"] = [ReportOut.model_validate(r) for r in recent_reports]
    base["rainfall_1h_mm"] = latest_weather.rainfall_1h_mm if latest_weather else 0.0
    base["rainfall_24h_mm"] = latest_weather.rainfall_24h_mm if latest_weather else 0.0
    base["historical_flood_prior"] = zone.historical_flood_prior
    return base


@router.get("/{zone_id}/history", response_model=list[ZoneScoreHistoryPoint])
async def zone_history(
    zone_id: str,
    hours: int = Query(default=24, le=24 * 30),
    db: AsyncSession = Depends(get_db),
):
    """Historical score pattern for a zone -- powers the sparkline + rainfall correlation chart."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (
        await db.execute(
            select(ZoneScoreHistory)
            .where(ZoneScoreHistory.zone_id == zone_id, ZoneScoreHistory.recorded_at >= cutoff)
            .order_by(ZoneScoreHistory.recorded_at.asc())
        )
    ).scalars().all()
    return [ZoneScoreHistoryPoint.model_validate(r) for r in rows]


@router.get("/lookup/flood-prone", response_model=list[ZoneOut])
async def flood_prone_zones(db: AsyncSession = Depends(get_db), min_prior: float = 30.0):
    """
    'Historical flood-prone area lookup before commuting' feature: zones whose
    long-run historical_flood_prior is high, regardless of current live score.
    """
    zones = (
        await db.execute(select(Zone).where(Zone.historical_flood_prior >= min_prior))
    ).scalars().all()
    return [_zone_base_dict(z) for z in zones]
