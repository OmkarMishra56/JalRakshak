"""
Real weather API adapter (OpenWeatherMap).

Polls current + 1h rainfall for each zone's centroid on a timer and feeds it
through the same `/weather/ingest` pipeline that manual/demo data uses --
so the scoring engine never needs to know or care where the number came from.

To enable: set OPENWEATHER_API_KEY in your .env, then call
`start_weather_poller(app)` from main.py (already wired in).

Free-tier OpenWeatherMap's "Current Weather" endpoint returns `rain.1h` (mm in
last hour) directly. 24h accumulation is approximated by keeping a rolling sum
of our own polled snapshots (since the free tier doesn't expose historical
accumulation) -- swap in the One Call API's daily summary for a more accurate
number if you have a paid key (see README).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from .config import get_settings
from .database import AsyncSessionLocal
from .models import Zone, WeatherSnapshot
from .scoring import compute_zone_score, apply_score_result
from .websocket_manager import manager
from .schemas import ZoneUpdateEvent

logger = logging.getLogger("aquaalert.weather")
settings = get_settings()

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"


async def _rolling_24h_sum(db, zone_id: str, new_1h_mm: float) -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = (
        await db.execute(
            select(WeatherSnapshot.rainfall_1h_mm).where(
                WeatherSnapshot.zone_id == zone_id, WeatherSnapshot.recorded_at >= cutoff
            )
        )
    ).scalars().all()
    return sum(rows) + new_1h_mm


async def poll_all_zones_once():
    if not settings.openweather_api_key:
        logger.info("OPENWEATHER_API_KEY not set -- skipping real weather poll (demo/manual data only).")
        return

    async with AsyncSessionLocal() as db:
        zones = (await db.execute(select(Zone))).scalars().all()
        async with httpx.AsyncClient(timeout=10) as client:
            for zone in zones:
                try:
                    resp = await client.get(
                        OWM_URL,
                        params={
                            "lat": zone.centroid_lat,
                            "lon": zone.centroid_lng,
                            "appid": settings.openweather_api_key,
                            "units": "metric",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    rain_1h = data.get("rain", {}).get("1h", 0.0)
                    condition = (data.get("weather") or [{}])[0].get("main")

                    rain_24h = await _rolling_24h_sum(db, zone.id, rain_1h)

                    db.add(WeatherSnapshot(
                        zone_id=zone.id, rainfall_1h_mm=rain_1h,
                        rainfall_24h_mm=rain_24h, condition=condition,
                    ))
                    await db.commit()

                    result = await compute_zone_score(db, zone)
                    await apply_score_result(db, zone, result)
                    await db.commit()

                    if result.status_changed:
                        event = ZoneUpdateEvent(
                            zone_id=zone.id, code=zone.code, name=zone.name,
                            score=result.score, status=result.status,
                            status_changed=True, updated_at=zone.score_updated_at,
                        )
                        await manager.broadcast(event.model_dump(mode="json"))
                except Exception as e:
                    logger.warning(f"Weather poll failed for zone {zone.code}: {e}")


def start_weather_poller(scheduler: AsyncIOScheduler):
    scheduler.add_job(
        poll_all_zones_once,
        "interval",
        seconds=settings.weather_poll_interval_seconds,
        id="weather_poll",
        replace_existing=True,
    )
