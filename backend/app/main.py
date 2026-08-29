"""
AquaAlert FastAPI application entrypoint.

Wires together:
  - REST routers (auth, zones, reports, sensors, weather, admin, routes)
  - WebSocket endpoint (/ws/zones) for live map updates
  - APScheduler background jobs:
      * periodic "tick" rescoring of every zone (lets old reports decay away
        even with zero new input, and catches anything missed by event-driven
        rescoring)
      * optional real-weather polling (OpenWeatherMap) if OPENWEATHER_API_KEY set
  - Global rate limiting (slowapi) as a second line of defense on top of the
    report-specific limiter in routers/reports.py
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, text

from .config import get_settings
from .database import async_engine, AsyncSessionLocal, Base
from .models import Zone
from .scoring import compute_zone_score, apply_score_result
from .websocket_manager import manager
from .schemas import ZoneUpdateEvent
from .weather_provider import start_weather_poller

from .routers import auth as auth_router
from .routers import zones as zones_router
from .routers import reports as reports_router
from .routers import sensors as sensors_router
from .routers import weather as weather_router
from .routers import admin as admin_router
from .routers import routes as routes_router
from .routers import ws as ws_router

logging.basicConfig(level=logging.INFO)
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

scheduler = AsyncIOScheduler()


async def scoring_tick():
    """Periodic rescoring pass -- lets decay reduce scores even with no new events,
    and is a safety net that guarantees every zone reflects reality within one tick."""
    async with AsyncSessionLocal() as db:
        zones = (await db.execute(select(Zone))).scalars().all()
        for zone in zones:
            result = await compute_zone_score(db, zone)
            await apply_score_result(db, zone, result)
            if result.status_changed:
                event = ZoneUpdateEvent(
                    zone_id=zone.id, code=zone.code, name=zone.name,
                    score=result.score, status=result.status,
                    status_changed=True, updated_at=zone.score_updated_at,
                )
                await manager.broadcast(event.model_dump(mode="json"))
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure PostGIS extension + tables exist (idempotent). For production,
    # prefer Alembic migrations -- this is convenient for local/demo bootstrap.
    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)

    scheduler.add_job(scoring_tick, "interval", seconds=settings.scoring_tick_seconds, id="scoring_tick")
    start_weather_poller(scheduler)
    scheduler.start()

    yield

    scheduler.shutdown(wait=False)
    await async_engine.dispose()


app = FastAPI(
    title="AquaAlert API",
    description="Real-time urban waterlogging aggregation and flood-risk API.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(zones_router.router)
app.include_router(reports_router.router)
app.include_router(sensors_router.router)
app.include_router(weather_router.router)
app.include_router(admin_router.router)
app.include_router(routes_router.router)
app.include_router(ws_router.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logging.getLogger("aquaalert").exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
