
import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text, select

from .database import async_engine, AsyncSessionLocal, Base
from .models import (
    User, UserRole, Zone, Report, Sensor, SensorReading,
    WeatherSnapshot, ZoneScoreHistory, ZoneStatus,
)
from .auth import hash_password
from .scoring import compute_zone_score, apply_score_result

random.seed(42)


CITY_LAT, CITY_LNG = 12.9716, 77.5946

WARDS = [
    {"name": "Koramangala", "code": "WARD-01", "prior": 62},   
    {"name": "Indiranagar", "code": "WARD-02", "prior": 28},
    {"name": "Whitefield", "code": "WARD-03", "prior": 45},
    {"name": "Jayanagar", "code": "WARD-04", "prior": 18},
    {"name": "HSR Layout", "code": "WARD-05", "prior": 55},
    {"name": "Malleswaram", "code": "WARD-06", "prior": 12},
    {"name": "Electronic City", "code": "WARD-07", "prior": 38},
    {"name": "Yeshwanthpur", "code": "WARD-08", "prior": 22},
]

GRID_COLS = 4
CELL = 0.03  


def ward_polygon(index: int):
    col = index % GRID_COLS
    row = index // GRID_COLS
    lng0 = CITY_LNG + col * CELL
    lat0 = CITY_LAT + row * CELL
    lng1 = lng0 + CELL
    lat1 = lat0 + CELL
    centroid_lat = (lat0 + lat1) / 2
    centroid_lng = (lng0 + lng1) / 2
    wkt = f"POLYGON(({lng0} {lat0}, {lng1} {lat0}, {lng1} {lat1}, {lng0} {lat1}, {lng0} {lat0}))"
    return wkt, centroid_lat, centroid_lng


async def seed():
    async with async_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Zone))).scalars().first()
        if existing:
            print("Database already seeded (zones exist). Skipping.")
            return


        citizen = User(
            email="citizen@demo.aquaalert.io", full_name="Demo Citizen",
            hashed_password=hash_password("password123"), role=UserRole.citizen,
        )
        admin = User(
            email="admin@demo.aquaalert.io", full_name="Demo Municipal Admin",
            hashed_password=hash_password("password123"), role=UserRole.municipal_admin,
        )
        db.add_all([citizen, admin])
        await db.flush()

    
        zones = []
        for i, w in enumerate(WARDS):
            wkt, clat, clng = ward_polygon(i)
            zone = Zone(
                name=w["name"], code=w["code"],
                geom=f"SRID=4326;{wkt}",
                centroid_lat=clat, centroid_lng=clng,
                historical_flood_prior=w["prior"],
            )
            db.add(zone)
            zones.append(zone)
        await db.flush()

    
        now = datetime.now(timezone.utc)
        for zone in zones:
            for day_offset in range(14, 0, -1):
                day = now - timedelta(days=day_offset)
    
                is_rain_day = random.random() < (0.25 + zone.historical_flood_prior / 200)
                rain_1h = round(random.uniform(5, 45), 1) if is_rain_day else round(random.uniform(0, 2), 1)
                rain_24h = round(rain_1h * random.uniform(1.5, 4), 1)
                db.add(WeatherSnapshot(
                    zone_id=zone.id, rainfall_1h_mm=rain_1h, rainfall_24h_mm=rain_24h,
                    condition="Heavy Rain" if is_rain_day else "Clear",
                    recorded_at=day,
                ))
                score = min(100, max(0, rain_1h * 1.6 + zone.historical_flood_prior * 0.3 + random.uniform(-5, 5)))
                status = ZoneStatus.severe if score >= 65 else (ZoneStatus.moderate if score >= 35 else ZoneStatus.safe)
                db.add(ZoneScoreHistory(
                    zone_id=zone.id, score=round(score, 1), status=status,
                    contributing_reports=random.randint(0, 6),
                    contributing_sensors=random.randint(0, 2),
                    rainfall_component=round(min(100, rain_1h / 50 * 100), 1),
                    recorded_at=day,
                ))
        await db.flush()


        for zone in zones[::2]:
            sensor = Sensor(
                zone_id=zone.id, name=f"{zone.code}-DEPTH-SENSOR-1",
                location=f"SRID=4326;POINT({zone.centroid_lng} {zone.centroid_lat})",
                lat=zone.centroid_lat, lng=zone.centroid_lng,
                api_key=str(uuid.uuid4()),
            )
            db.add(sensor)
            await db.flush()
            db.add(SensorReading(sensor_id=sensor.id, water_depth_cm=round(random.uniform(2, 20), 1), battery_pct=91))

        live_scenarios = [
            (zones[0], 55, False, "Ankle-deep water near the main junction, traffic backing up"),
            (zones[0], 78, True, "Water entering ground-floor shops, verified by ward officer"),
            (zones[4], 40, False, "Puddling near the metro station entrance"),
            (zones[2], 15, False, "Light waterlogging, mostly cleared"),
        ]
        for zone, depth, verified, note in live_scenarios:
            jitter_lat = zone.centroid_lat + random.uniform(-0.005, 0.005)
            jitter_lng = zone.centroid_lng + random.uniform(-0.005, 0.005)
            db.add(Report(
                zone_id=zone.id, reporter_id=citizen.id,
                location=f"SRID=4326;POINT({jitter_lng} {jitter_lat})",
                lat=jitter_lat, lng=jitter_lng,
                water_depth_cm=depth, is_verified=verified, note=note,
                created_at=now - timedelta(minutes=random.randint(2, 40)),
            ))

        await db.commit()

        for zone in zones:
            result = await compute_zone_score(db, zone)
            await apply_score_result(db, zone, result)
        await db.commit()

    print("Seed complete: 8 wards, 2 demo users, 14 days of history, 4 sensors, 4 live reports.")
    print("  citizen@demo.aquaalert.io / password123")
    print("  admin@demo.aquaalert.io   / password123")


if __name__ == "__main__":
    asyncio.run(seed())
