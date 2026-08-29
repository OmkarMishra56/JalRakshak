"""
=====================================================================================
AquaAlert Real-Time Waterlogging Scoring Engine
=====================================================================================

For each zone we compute a single 0-100 "waterlogging score" every time new data
arrives (a new report, sensor reading, or weather poll), and on a periodic tick
(to let old reports decay even with no new input).

The score blends four signal families:

  1. CITIZEN REPORTS (unverified)   - weight = settings.weight_unverified_report
  2. CITIZEN REPORTS (verified)     - weight = settings.weight_verified_report
  3. MUNICIPAL OVERRIDES            - weight = settings.weight_municipal_override
  4. SENSOR READINGS                - weight = settings.weight_sensor
  5. WEATHER (rainfall intensity)   - weight = settings.weight_weather

--------------------------------------------------------------------------------
STEP 1 - Per-report decay
--------------------------------------------------------------------------------
A report's influence decays exponentially with age so a puddle reported 3 hours
ago stops dominating the live picture:

    decay(age_minutes) = 0.5 ** (age_minutes / half_life_minutes)

Reports older than `report_max_age_hours` are excluded entirely (decay ~ 0 anyway,
but we filter at the query level for performance).

--------------------------------------------------------------------------------
STEP 2 - Per-signal raw score (0-100)
--------------------------------------------------------------------------------
Each report/sensor reading is converted to a 0-100 "severity" via water depth:

    severity(depth_cm) = clamp(depth_cm / 100 * 100, 0, 100)
    (i.e. 100cm / chest-deep water = 100 severity; 10cm ankle-deep = ~10)

--------------------------------------------------------------------------------
STEP 3 - Weighted, decayed aggregate for reports+sensors
--------------------------------------------------------------------------------
    numerator   = sum(severity_i * weight_i * decay_i)
    denominator = sum(weight_i * decay_i)
    report_component = numerator / denominator   (weighted average, 0-100)

We ALSO fold in report *count* as a confidence booster: many independent
low-severity reports clustered together indicate a spreading problem even if
no single report looks severe, so we apply a small volume bonus:

    volume_bonus = min(15, 3 * log2(1 + effective_report_count))

--------------------------------------------------------------------------------
STEP 4 - Weather component
--------------------------------------------------------------------------------
Rainfall intensity is converted to a 0-100 scale using standard meteorological
intensity bands (mm/hr): light <2.5, moderate 2.5-7.6, heavy 7.6-50, violent >50.

    weather_score = clamp(rainfall_1h_mm / 50 * 100, 0, 100)   [violent rain -> 100]

24h accumulation adds a soil-saturation modifier (waterlogged ground drains
slower), capped at +20:

    saturation_bonus = min(20, rainfall_24h_mm / 5)

--------------------------------------------------------------------------------
STEP 5 - Blend + sparse-data graceful degradation
--------------------------------------------------------------------------------
If there are ZERO reports/sensors in the window ("sparse data"), the zone score
is driven entirely by weather + the zone's historical_flood_prior (a static
baseline reflecting how flood-prone that zone has historically been), so the
system NEVER shows "no data" -- it always shows a best-effort estimate:

    if no reports and no sensors:
        score = 0.55 * weather_component + 0.45 * historical_prior

Otherwise we blend all available components by their own confidence weight,
where confidence is higher when there is real ground-truth (reports/sensors)
vs. the weather-only proxy:

    score = (
        report_sensor_weight * report_sensor_component +
        weather_weight        * weather_component +
        prior_weight           * historical_prior
    ) / (report_sensor_weight + weather_weight + prior_weight)

    where report_sensor_weight scales UP with how much verified/sensor data
    exists (more trust in ground truth as it accumulates), and prior_weight
    scales DOWN correspondingly (we don't need the historical fallback once
    we have live signal).

Final score is clamped to [0, 100].

--------------------------------------------------------------------------------
STEP 6 - Status classification
--------------------------------------------------------------------------------
    score <  threshold_moderate  -> SAFE     (green)
    score <  threshold_severe    -> MODERATE (yellow)
    score >= threshold_severe    -> SEVERE   (red)

A status CHANGE (not just a score wobble) is what triggers a WebSocket push,
keeping bandwidth low while guaranteeing sub-5s propagation of anything a
citizen actually needs to react to.
=====================================================================================
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .models import Report, Sensor, SensorReading, WeatherSnapshot, Zone, ZoneStatus, ZoneScoreHistory

settings = get_settings()


def _now():
    return datetime.now(timezone.utc)


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def decay_factor(age_minutes: float) -> float:
    """Exponential decay: contribution halves every `report_decay_half_life_minutes`."""
    if age_minutes < 0:
        age_minutes = 0
    return 0.5 ** (age_minutes / settings.report_decay_half_life_minutes)


def severity_from_depth(depth_cm: float) -> float:
    """Water depth (cm) -> 0-100 severity. 100cm+ (chest deep / car-submerging) = 100."""
    return clamp(depth_cm / 100.0 * 100.0)


def weather_component(rainfall_1h_mm: float, rainfall_24h_mm: float) -> float:
    base = clamp(rainfall_1h_mm / 50.0 * 100.0)
    saturation_bonus = min(20.0, rainfall_24h_mm / 5.0)
    return clamp(base + saturation_bonus)


def status_for_score(score: float) -> ZoneStatus:
    if score >= settings.threshold_severe:
        return ZoneStatus.severe
    if score >= settings.threshold_moderate:
        return ZoneStatus.moderate
    return ZoneStatus.safe


@dataclass
class SignalPoint:
    severity: float
    weight: float
    age_minutes: float


@dataclass
class ZoneScoreResult:
    zone_id: str
    score: float
    status: ZoneStatus
    previous_status: ZoneStatus
    status_changed: bool
    contributing_reports: int
    contributing_sensors: int
    rainfall_component: float


async def compute_zone_score(db: AsyncSession, zone: Zone) -> ZoneScoreResult:
    now = _now()
    max_age = timedelta(hours=settings.report_max_age_hours)
    cutoff = now - max_age

    # --- Pull recent, non-dismissed reports for this zone ---
    report_rows = (
        await db.execute(
            select(Report).where(
                Report.zone_id == zone.id,
                Report.is_dismissed.is_(False),
                Report.created_at >= cutoff,
            )
        )
    ).scalars().all()

    signals: list[SignalPoint] = []
    for r in report_rows:
        age_min = (now - r.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60.0
        if r.is_municipal_override:
            w = settings.weight_municipal_override
        elif r.is_verified:
            w = settings.weight_verified_report
        else:
            w = settings.weight_unverified_report
        signals.append(SignalPoint(severity=severity_from_depth(r.water_depth_cm), weight=w, age_minutes=age_min))

    # --- Pull recent sensor readings for sensors in this zone ---
    sensor_ids = [s.id for s in (
        await db.execute(select(Sensor).where(Sensor.zone_id == zone.id, Sensor.is_active.is_(True)))
    ).scalars().all()]

    sensor_reading_count = 0
    if sensor_ids:
        reading_rows = (
            await db.execute(
                select(SensorReading).where(
                    SensorReading.sensor_id.in_(sensor_ids),
                    SensorReading.recorded_at >= cutoff,
                )
            )
        ).scalars().all()
        sensor_reading_count = len(reading_rows)
        for sr in reading_rows:
            age_min = (now - sr.recorded_at.replace(tzinfo=timezone.utc)).total_seconds() / 60.0
            signals.append(
                SignalPoint(severity=severity_from_depth(sr.water_depth_cm),
                             weight=settings.weight_sensor, age_minutes=age_min)
            )

    # --- Weighted decayed aggregate of reports + sensors ---
    num = 0.0
    den = 0.0
    effective_count = 0.0
    for s in signals:
        d = decay_factor(s.age_minutes)
        num += s.severity * s.weight * d
        den += s.weight * d
        effective_count += d

    report_sensor_component = (num / den) if den > 0 else None
    volume_bonus = min(15.0, 3.0 * math.log2(1 + effective_count)) if effective_count > 0 else 0.0
    if report_sensor_component is not None:
        report_sensor_component = clamp(report_sensor_component + volume_bonus)

    # --- Latest weather snapshot for this zone ---
    latest_weather = (
        await db.execute(
            select(WeatherSnapshot)
            .where(WeatherSnapshot.zone_id == zone.id)
            .order_by(WeatherSnapshot.recorded_at.desc())
            .limit(1)
        )
    ).scalars().first()

    rainfall_1h = latest_weather.rainfall_1h_mm if latest_weather else 0.0
    rainfall_24h = latest_weather.rainfall_24h_mm if latest_weather else 0.0
    weather_score = weather_component(rainfall_1h, rainfall_24h)

    prior = zone.historical_flood_prior or 0.0

    # --- Graceful degradation: sparse-data blend ---
    if report_sensor_component is None:
        score = clamp(0.55 * weather_score + 0.45 * prior)
    else:
        # Trust in ground truth scales with effective (decay-weighted) signal count,
        # saturating around 6 effective reports/sensor readings.
        ground_truth_weight = clamp(effective_count / 6.0, 0.0, 1.0) * 3.0  # up to 3x
        weather_weight = 1.0
        prior_weight = clamp(1.0 - ground_truth_weight / 3.0, 0.1, 1.0)  # shrinks as ground truth grows

        score = (
            ground_truth_weight * report_sensor_component
            + weather_weight * weather_score
            + prior_weight * prior
        ) / (ground_truth_weight + weather_weight + prior_weight)
        score = clamp(score)

    new_status = status_for_score(score)
    previous_status = zone.current_status

    return ZoneScoreResult(
        zone_id=zone.id,
        score=round(score, 1),
        status=new_status,
        previous_status=previous_status,
        status_changed=(new_status != previous_status),
        contributing_reports=len(report_rows),
        contributing_sensors=sensor_reading_count,
        rainfall_component=round(weather_score, 1),
    )


async def apply_score_result(db: AsyncSession, zone: Zone, result: ZoneScoreResult) -> None:
    """Persist the new score onto the zone + append a history row."""
    zone.current_score = result.score
    zone.current_status = result.status
    zone.score_updated_at = _now()
    db.add(zone)
    db.add(
        ZoneScoreHistory(
            zone_id=zone.id,
            score=result.score,
            status=result.status,
            contributing_reports=result.contributing_reports,
            contributing_sensors=result.contributing_sensors,
            rainfall_component=result.rainfall_component,
        )
    )
