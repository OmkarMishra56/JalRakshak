"""
Low-cost sensor ingestion (e.g. an ESP32 + ultrasonic depth sensor posting a
webhook every N seconds). Auth is a simple per-device API key, not a JWT --
these are unattended devices, not users.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Sensor, SensorReading, Zone
from ..schemas import SensorReadingIn, SensorOut
from ..scoring import compute_zone_score, apply_score_result
from ..websocket_manager import manager
from ..schemas import ZoneUpdateEvent

router = APIRouter(prefix="/sensors", tags=["sensors"])


async def _authenticate_sensor(db: AsyncSession, sensor_id: str, x_api_key: str | None) -> Sensor:
    sensor = (await db.execute(select(Sensor).where(Sensor.id == sensor_id))).scalars().first()
    if not sensor or not sensor.is_active:
        raise HTTPException(status_code=404, detail="Sensor not found or inactive")
    if not x_api_key or x_api_key != sensor.api_key:
        raise HTTPException(status_code=401, detail="Invalid sensor API key")
    return sensor


@router.post("/{sensor_id}/readings")
async def post_reading(
    sensor_id: str,
    payload: SensorReadingIn,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
):
    """
    Webhook endpoint a physical device calls, e.g.:
      POST /sensors/{sensor_id}/readings
      Header: X-API-Key: <sensor.api_key>
      Body: {"water_depth_cm": 34.5, "battery_pct": 88}
    """
    sensor = await _authenticate_sensor(db, sensor_id, x_api_key)

    reading = SensorReading(
        sensor_id=sensor.id,
        water_depth_cm=payload.water_depth_cm,
        battery_pct=payload.battery_pct,
    )
    db.add(reading)
    await db.commit()

    zone = (await db.execute(select(Zone).where(Zone.id == sensor.zone_id))).scalars().first()
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


@router.get("/zone/{zone_id}", response_model=list[SensorOut])
async def list_sensors_for_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Sensor).where(Sensor.zone_id == zone_id))).scalars().all()
    return [SensorOut.model_validate(s) for s in rows]
