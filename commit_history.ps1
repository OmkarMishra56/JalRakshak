# ============================================================================
# AquaAlert / JalRakshak -- incremental commit history builder
#
# Run this from D:\aquaalert in PowerShell. It replays the project as 34
# logical commits (scaffolding -> schema -> scoring engine -> real-time
# layer -> citizen/admin flows -> docs), matching how the project actually
# came together, instead of one giant squashed commit.
#
# Safe to re-run from scratch: delete the .git folder first if you want to
# start over (`Remove-Item -Recurse -Force .git`).
# ============================================================================

git init
git branch -M main

# Helper: stage exact paths then commit. Using explicit paths (not `git add .`)
# per step keeps each commit scoped to what it claims to introduce.
function Commit-Step {
    param([string[]]$Paths, [string]$Message)
    git add -- $Paths
    git commit -m $Message
}

# ---------------------------------------------------------------------------
# 1. Project scaffolding
# ---------------------------------------------------------------------------
Commit-Step @(".gitignore") `
    "chore: initial .gitignore"

Commit-Step @("docker-compose.yml") `
    "chore: add docker-compose for db + redis + backend + frontend"

# ---------------------------------------------------------------------------
# 2. Backend: config, database, schema
# ---------------------------------------------------------------------------
Commit-Step @("backend/requirements.txt") `
    "backend: add Python dependencies"

Commit-Step @("backend/app/__init__.py", "backend/app/routers/__init__.py") `
    "backend: scaffold app package structure"

Commit-Step @("backend/app/config.py") `
    "backend: centralized settings (scoring weights, thresholds, rate limits)"

Commit-Step @("backend/app/database.py") `
    "backend: async SQLAlchemy engine/session setup"

Commit-Step @("backend/app/models.py") `
    "backend: PostGIS data model - zones, reports, sensors, weather, score history"

# ---------------------------------------------------------------------------
# 3. Backend: scoring engine (the core of the system)
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/scoring.py") `
    "backend: real-time waterlogging scoring engine (decay + weighting + blend)"

# ---------------------------------------------------------------------------
# 4. Backend: auth + schemas
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/auth.py") `
    "backend: JWT auth, password hashing, role-gated dependencies"

Commit-Step @("backend/app/schemas.py") `
    "backend: Pydantic request/response schemas"

# ---------------------------------------------------------------------------
# 5. Backend: real-time layer
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/websocket_manager.py") `
    "backend: WebSocket connection manager with optional Redis pub/sub fan-out"

Commit-Step @("backend/app/routers/ws.py") `
    "backend: WebSocket endpoint for live zone updates"

# ---------------------------------------------------------------------------
# 6. Backend: ingestion + read routers
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/routers/auth.py") `
    "backend: auth routes (register, login, me)"

Commit-Step @("backend/app/routers/zones.py") `
    "backend: zone read endpoints - live map data, detail, history, flood-prone lookup"

Commit-Step @("backend/app/routers/reports.py") `
    "backend: citizen report ingestion with rate limiting, dedup, and geofencing"

Commit-Step @("backend/app/routers/sensors.py") `
    "backend: IoT sensor webhook ingestion (API-key authenticated)"

Commit-Step @("backend/app/routers/weather.py", "backend/app/weather_provider.py") `
    "backend: weather ingestion + OpenWeatherMap polling adapter"

# ---------------------------------------------------------------------------
# 7. Backend: routing + admin
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/routing.py", "backend/app/routers/routes.py") `
    "backend: zone-level route suggestion avoiding flooded zones (Dijkstra)"

Commit-Step @("backend/app/routers/admin.py") `
    "backend: municipal dashboard endpoints - moderation, analytics, CSV export"

# ---------------------------------------------------------------------------
# 8. Backend: app entrypoint + demo data
# ---------------------------------------------------------------------------
Commit-Step @("backend/app/main.py") `
    "backend: FastAPI app entrypoint, background scoring tick, CORS, rate limiting"

Commit-Step @("backend/app/seed.py") `
    "backend: seed script - mock city, demo users, 14 days of history"

Commit-Step @("backend/Dockerfile", "backend/.env.example") `
    "backend: Dockerfile and env template"

# ---------------------------------------------------------------------------
# 9. Frontend: scaffolding + config
# ---------------------------------------------------------------------------
Commit-Step @("frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig.json", "frontend/next-env.d.ts") `
    "frontend: Next.js project scaffolding"

Commit-Step @("frontend/next.config.js", "frontend/postcss.config.js", "frontend/tailwind.config.js") `
    "frontend: build config + design tokens"

Commit-Step @("frontend/Dockerfile", "frontend/.env.local.example") `
    "frontend: Dockerfile and env template"

# ---------------------------------------------------------------------------
# 10. Frontend: data layer
# ---------------------------------------------------------------------------
Commit-Step @("frontend/lib/api.ts") `
    "frontend: typed REST client for the AquaAlert API"

Commit-Step @("frontend/lib/ws.ts") `
    "frontend: WebSocket hook for live zone updates with reconnect backoff"

# ---------------------------------------------------------------------------
# 11. Frontend: shell + map
# ---------------------------------------------------------------------------
Commit-Step @("frontend/app/globals.css", "frontend/app/layout.tsx") `
    "frontend: root layout and global styles"

Commit-Step @("frontend/components/MapView.tsx") `
    "frontend: live color-coded zone map (Leaflet)"

Commit-Step @("frontend/app/page.tsx") `
    "frontend: main citizen map page wiring live updates + report FAB"

# ---------------------------------------------------------------------------
# 12. Frontend: citizen flows
# ---------------------------------------------------------------------------
Commit-Step @("frontend/components/ZonePanel.tsx") `
    "frontend: zone detail panel - recent reports, rainfall, 24h trend"

Commit-Step @("frontend/components/ReportModal.tsx") `
    "frontend: one-tap geolocated waterlogging report flow"

# ---------------------------------------------------------------------------
# 13. Frontend: admin dashboard
# ---------------------------------------------------------------------------
Commit-Step @("frontend/app/admin/page.tsx") `
    "frontend: municipal dashboard - login, moderation queue, analytics, CSV export"

# NOTE on bug fixes: models.py, requirements.txt, and routers/zones.py above
# are committed already containing fixes found during live end-to-end testing
# (duplicate GIST index removed, bcrypt pinned to 4.0.1, email-validator
# added, geojson built before schema validation). There's no separate "fix:"
# commit for these -- the pre-fix broken versions were never saved to disk,
# so faking a "broken then fixed" history here would just be invented commits
# with no real diff behind them. If you want that history to exist for real,
# see the bottom of this script for how to add it honestly.

# ---------------------------------------------------------------------------
# 14. Docs
# ---------------------------------------------------------------------------
Commit-Step @("README.md") `
    "docs: setup guide, scoring algorithm writeup, architecture diagram"

$commitCount = (git log --oneline | Measure-Object -Line).Lines
Write-Host ""
Write-Host "Done. $commitCount commits created." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  git remote add origin https://github.com/OmkarMishra56/JalRakshak.git"
Write-Host "  git push -u origin main"

# ============================================================================
# Optional: if you want the 4 bug fixes to be REAL separate commits (each with
# an actual diff), you'd need to commit the broken version first, then the
# fixed version. This repo only has the final, fixed files, so that history
# doesn't exist to replay. If it matters to you, the honest way to get it is:
# manually revert those 4 spots to what they'd have looked like broken, commit
# that, then re-apply the fix and commit again. Not scripted here since it
# means writing intentionally-wrong code just to commit it.
# ============================================================================
