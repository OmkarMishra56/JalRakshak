# JalRakshak

Real-time, crowd-sourced + sensor-based urban waterlogging visibility. The
city is divided into zones (wards); each zone has a live 0–100 waterlogging
score computed from citizen reports, IoT depth sensors, weather, and
municipal verification, pushed to every connected client over WebSocket the
moment it changes.

```
backend/    FastAPI + PostgreSQL/PostGIS + WebSockets
frontend/   Next.js (App Router) + Leaflet live map
docker-compose.yml   spins up db + redis + backend + frontend together
```

---

## Architecture

### System diagram

```mermaid
flowchart TB
    subgraph Sources["Data Sources"]
        Citizen["📱 Citizen<br/>(geo-tagged report)"]
        Sensor["📡 IoT Depth Sensor<br/>(webhook, API key auth)"]
        Weather["🌧️ Weather Provider<br/>(OpenWeatherMap poller)"]
        Admin["🏛️ Municipal Admin<br/>(verify / override)"]
    end

    subgraph Backend["FastAPI Backend"]
        API["REST Routers<br/>reports · sensors · weather · admin · zones · routes"]
        Scoring["Scoring Engine<br/>(scoring.py)<br/>decay + weighting + blend"]
        Scheduler["APScheduler<br/>30s rescoring tick<br/>10min weather poll"]
        WS["WebSocket Manager<br/>(websocket_manager.py)"]
    end

    subgraph Data["Data Layer"]
        PG[("PostgreSQL + PostGIS<br/>zones · reports · sensors<br/>weather_snapshots · score_history")]
        Redis[("Redis Pub/Sub<br/>(optional, multi-instance<br/>WS fan-out)")]
    end

    subgraph Clients["Clients"]
        Map["Live Map<br/>(Next.js + Leaflet)"]
        Dash["Admin Dashboard<br/>(moderation, analytics, CSV export)"]
    end

    Citizen -->|POST /reports| API
    Sensor -->|POST /sensors/:id/readings| API
    Weather -.->|poll| Scheduler
    Admin -->|PATCH /reports/:id/moderate| API

    API --> PG
    API -->|on every write| Scoring
    Scheduler -->|periodic sweep| Scoring
    Scoring --> PG
    Scoring -->|status changed| WS
    WS -.->|optional| Redis
    WS ==>|zone_update event, <5s| Map
    WS ==> Dash

    Map -->|GET /zones, /zones/:id| API
    Dash -->|GET /admin/*| API
```

### Request lifecycle: how a report becomes a live map update

```
1. Citizen taps "Report waterlogging" → browser geolocates → POST /reports
2. Backend rate-limits (per-user, per-IP, duplicate-suppression), then
   geofences the point into a zone via PostGIS ST_Contains
3. Report is written to Postgres
4. Scoring engine recomputes that zone's score synchronously:
     - pulls recent reports + sensor readings (last N hours)
     - applies exponential time-decay per signal
     - blends with latest weather + the zone's historical prior
     - classifies into Safe / Moderate / Severe
5. New score is persisted + appended to zone_score_history
6. If status changed (not just a score wobble), a zone_update event is
   broadcast over WebSocket to every connected client
7. Every open map instantly patches that one zone's color -- no reload,
   no polling. End-to-end: comfortably under the 5-second requirement.
```

A background APScheduler job re-runs step 4 for **every** zone every 30
seconds regardless of new input, so scores decay smoothly even when nothing
new is being reported.

### Component responsibilities

| Component | File(s) | Responsibility |
|---|---|---|
| Zone-based data model | `models.py` | PostGIS polygons (zones) and points (reports/sensors), SRID 4326 |
| Ingestion | `routers/reports.py`, `routers/sensors.py`, `routers/weather.py` | Validates, rate-limits, geofences, persists |
| Scoring engine | `scoring.py` | Pure function: signals in → 0–100 score out (see below) |
| Route suggestion | `routing.py` | Zone-adjacency Dijkstra, penalizes severe zones |
| Real-time fan-out | `websocket_manager.py` | In-process broadcast, optional Redis Pub/Sub for horizontal scale |
| Background jobs | `main.py` (`scoring_tick`), `weather_provider.py` | Periodic decay sweep + weather polling |
| Auth | `auth.py` | JWT, bcrypt hashing, role-gated dependencies (citizen / municipal_admin / super_admin) |
| Live map | `frontend/components/MapView.tsx`, `lib/ws.ts` | Leaflet + WebSocket hook, patches one zone in place per event |
| Admin dashboard | `frontend/app/admin/page.tsx` | Moderation queue, analytics table, CSV export |

### Why these tech choices

- **PostGIS** for zone polygons + `ST_Contains`/`ST_Touches`/`ST_DWithin` —
  geofencing reports and building the route-suggestion adjacency graph both
  need real spatial queries, not lat/lng bounding-box hacks.
- **WebSocket over polling** — the <5s propagation requirement rules out
  reasonable polling intervals; push is the only way to get there cheaply.
- **Redis Pub/Sub is optional, not required** — a single backend instance
  broadcasts in-process for free; Redis only enters the picture once you run
  multiple backend replicas behind a load balancer (see `USE_REDIS` in
  `config.py`).
- **Scoring is a pure function** (`compute_zone_score`) — it takes DB rows in
  and returns a result, with no side effects. This is what makes it callable
  identically from an HTTP handler, the background scheduler, and (if you
  outgrow it) an external rules microservice, without duplicating logic.

---

## Quick start

### Option A — Docker

```bash
cp backend/.env.example backend/.env        # edit JWT_SECRET at minimum
cp frontend/.env.local.example frontend/.env.local
docker compose up --build
```

Seed the demo city once containers are up:
```bash
docker compose exec backend python -m app.seed
```

- Citizen map: http://localhost:3000
- Municipal dashboard: http://localhost:3000/admin (`admin@demo.aquaalert.io` / `password123`)
- API docs: http://localhost:8000/docs

**If Docker Desktop misbehaves** (stuck pulls, "read-only file system",
engine ping errors — all fixable): quit Docker Desktop fully, run
`wsl --shutdown` in PowerShell, relaunch Docker Desktop, and retry. If that
doesn't clear it, use Docker Desktop → Settings → Troubleshoot → "Reset to
factory defaults." If Docker keeps being unreliable on your machine, Option B
below avoids it entirely and is equally valid for local dev.

### Option B — Native / WSL2 (no Docker)

Requires PostgreSQL 14+ with PostGIS. On Windows, run this inside **WSL2**
(`wsl` from PowerShell); your project folder is visible at `/mnt/d/aquaalert`
if it's on `D:\`. On Linux/Mac, run it directly.

```bash
# Postgres + PostGIS
sudo apt install -y postgresql postgresql-contrib postgis postgresql-16-postgis-3
sudo service postgresql start
sudo -u postgres psql -c "CREATE USER aquaalert WITH PASSWORD 'aquaalert';"
sudo -u postgres psql -c "CREATE DATABASE aquaalert OWNER aquaalert;"
sudo -u postgres psql -d aquaalert -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Backend
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://aquaalert:aquaalert@localhost:5432/aquaalert
SYNC_DATABASE_URL=postgresql://aquaalert:aquaalert@localhost:5432/aquaalert
JWT_SECRET=dev_only_secret_change_me
USE_REDIS=false
CORS_ORIGINS=["http://localhost:3000"]
EOF
./venv/bin/python -m app.seed
./venv/bin/uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Then open http://localhost:3000 (WSL2 forwards `localhost` to Windows
automatically, so your regular browser works unchanged).

---

## The scoring algorithm

Every zone has a live score in `[0, 100]`, recomputed (a) instantly whenever a
new report/sensor reading/weather update arrives, and (b) on a periodic tick
(`SCORING_TICK_SECONDS`, default 30s). Full inline math and rationale live in
`backend/app/scoring.py`; summary:

1. **Per-signal severity** — a report's water depth (cm) maps to 0–100
   (`100cm ≈ chest-deep ⇒ severity 100`). Sensor readings use the same mapping.
2. **Exponential time decay** — each report's weight halves every
   `REPORT_DECAY_HALF_LIFE_MINUTES` (default 90 min) and is dropped entirely
   past `REPORT_MAX_AGE_HOURS` (default 3h) — an old puddle doesn't haunt the
   map after it's dried up.
3. **Trust weighting** — unverified citizen reports, verified reports,
   municipal overrides, and sensor readings each carry a different weight
   (verified ≫ unverified; municipal override is treated as ground truth).
4. **Volume bonus** — many independent low-severity reports clustered
   together nudge the score up even if no single report looks severe (a
   `log2` bonus on effective, decay-weighted report count, capped at +15).
5. **Weather component** — rainfall intensity (mm/hr) mapped to meteorological
   intensity bands, plus a soil-saturation bonus from 24h accumulation.
6. **Historical prior + graceful degradation** — each zone has a static
   `historical_flood_prior` (how flood-prone it's been historically). With
   **zero** live reports/sensors, the score is `0.55·weather + 0.45·prior` —
   the system never shows "no data," it always shows a best-effort estimate.
   As real reports/sensor readings accumulate, their weight in the blend
   scales up and the historical prior's weight shrinks proportionally.
7. **Status thresholds** — `score < 35` → Safe (green), `< 65` → Moderate
   (yellow), `≥ 65` → Severe (red). A WebSocket push only fires on a **status
   change**, not every score wobble.

## Real-time propagation

`reports.py`, `sensors.py`, and `weather.py` each call `compute_zone_score` →
`apply_score_result` → `manager.broadcast(...)` synchronously after every
write, so an update reaches connected clients in well under a second in
practice. A background APScheduler job (`scoring_tick`) also sweeps all zones
every 30s so decay is reflected even with zero new events.

For horizontal scaling (multiple backend replicas behind a load balancer), set
`USE_REDIS=true` — `websocket_manager.py` then also publishes to a shared
Redis Pub/Sub channel so every replica's locally-connected clients get every
update, not just the replica that received the write.

## Plugging in a real weather API

`app/weather_provider.py` already implements an OpenWeatherMap adapter:

1. Get a free API key from https://openweathermap.org/api
2. Set `OPENWEATHER_API_KEY` in `backend/.env`
3. Restart the backend — an APScheduler job polls each zone's centroid every
   `WEATHER_POLL_INTERVAL_SECONDS` (default 10 min) and feeds results through
   the same `/weather/ingest` pipeline demo/manual data uses.

For a paid-tier upgrade, swap the endpoint for OpenWeatherMap's One Call API
(gives real 24h accumulation instead of the rolling-sum approximation used
here), or point the adapter at any other provider (IMD, Weatherbit,
Tomorrow.io) — just keep returning `{rainfall_1h_mm, rainfall_24h_mm,
condition}` per zone.

## Plugging in real sensors

Any device that can make an HTTPS POST works. Register a `Sensor` row (see
`app/seed.py` for an example) and have the device call:

```
POST /sensors/{sensor_id}/readings
Header: X-API-Key: <sensor.api_key>
Body:   {"water_depth_cm": 34.5, "battery_pct": 88}
```

An ESP32 + waterproof ultrasonic rangefinder (HC-SR04 in a housing, or a
JSN-SR04T for outdoor use) mounted over a drain/street low-point, posting
every 1–5 minutes, is the reference cheap setup this was designed around.

## Anti-spam / rate limiting

Implemented in `app/routers/reports.py`:
- Max reports per user per hour, and per IP per hour (independent limits).
- Duplicate suppression: a report within ~15m of the same IP's last report
  inside a 60s window is rejected.
- Geofencing: a report must fall inside a real zone polygon (`ST_Contains`)
  or it's rejected outright.
- Global `slowapi` rate limiting is also wired into `main.py` as a second
  line of defense.

## Route suggestion (avoid flooded zones)

`app/routing.py` builds a zone-adjacency graph (zones sharing a border) and
runs Dijkstra with a heavy penalty on entering a severe zone and a smaller
penalty for moderate zones. This is a **zone-level** router, not a full
street-network router. To get turn-by-turn street routing that avoids
flooded segments, swap this for a call to OSRM/GraphHopper with a dynamic
"avoid" polygon built from the current severe zones (the geometries you'd
need are already sitting in `Zone.geom`).

## Database schema

See `backend/app/models.py`. Core tables: `users`, `zones` (PostGIS
`POLYGON`), `reports` (PostGIS `POINT`), `sensors` + `sensor_readings`,
`weather_snapshots`, `zone_score_history` (append-only, powers the admin
analytics + sparkline charts). All geometry is SRID 4326 (WGS84 lat/lng).
Tables + the `postgis` extension are created automatically on backend
startup (`Base.metadata.create_all`) — for production, replace this with
Alembic migrations.

## Where a Java scoring microservice would slot in (optional path)

The scoring math in `scoring.py` is intentionally pure/stateless (inputs in,
score out) — if the rules engine grows complex enough to warrant a dedicated
service (per-zone custom rule sets, ML-based severity classification of
report photos, a rules DSL for municipal engineers), extract it behind an
HTTP/gRPC call: `reports.py` / `sensors.py` / `weather.py` would call out to
it instead of calling `compute_zone_score` directly, and everything
downstream (broadcast, history logging) stays unchanged.

## What's stubbed vs. production-ready

- **Production-ready**: scoring math, decay logic, WebSocket fan-out
  (including Redis multi-instance path), rate limiting/anti-spam, JWT auth +
  role gating, PostGIS geospatial queries, moderation queue, CSV export.
- **Demo-grade, swap before production**: table creation via `create_all`
  (use Alembic), photo upload is a raw URL field (wire to S3/Cloudinary + an
  upload endpoint), push/SMS alerts described in the spec are not
  implemented (the WebSocket event stream is the hook point — pipe
  `status_changed` events for zones a user has marked "near me" into
  FCM/Twilio), and the route suggester is zone-level, not street-level.
