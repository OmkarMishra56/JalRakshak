"""
Weather ingestion.

`POST /weather/ingest` is the generic entry point -- used by:
  (a) the built-in OpenWeatherMap poller (see app/weather_provider.py), and
  (b) manual/admin pushes, and
  (c) the seed script for historical demo data.

Keeping ingestion as a plain endpoint (rather than baking OpenWeatherMap calls
directly into the scoring engine) is what makes it easy to "plug in a real
weather API later" -- see README for the OpenWeatherMap adapter.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import WeatherSnapshot, Zone
from ..schemas import WeatherIngest
from ..auth import require_admin
from ..models import User
from ..scoring import compute_zone_score, apply_score_result
from ..websocket_manager import manager
from ..schemas import ZoneUpdateEvent

router = APIRouter(prefix="/weather", tags=["weather"])


@router.post("/ingest")
async def ingest_weather(
    payload: WeatherIngest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    snapshot = WeatherSnapshot(
        zone_id=payload.zone_id,
        rainfall_1h_mm=payload.rainfall_1h_mm,
        rainfall_24h_mm=payload.rainfall_24h_mm,
        condition=payload.condition,
    )
    db.add(snapshot)
    await db.commit()

    zone = (await db.execute(select(Zone).where(Zone.id == payload.zone_id))).scalars().first()
    if zone:
        result = await compute_zone_score(db, zone)
        await apply_score_result(db, zone, result)
        await db.commit()
        event = ZoneUpdateEvent(
            zone_id=zone.id, code=zone.code, name=zone.name,
            score=result.score, status=result.status,
            status_changed=result.status_changed, updated_at=zone.score_updated_at,
        )
        await manager.broadcast(event.model_dump(mode="json"))

    return {"status": "ok"}
