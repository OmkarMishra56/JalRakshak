"""
Central configuration. All values overridable via environment variables / .env file.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- Database ---
    database_url: str = "postgresql+asyncpg://aquaalert:aquaalert@localhost:5432/aquaalert"
    sync_database_url: str = "postgresql://aquaalert:aquaalert@localhost:5432/aquaalert"

    # --- Auth ---
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_env_JWT_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  # 12 hours

    # --- Redis (pub/sub for horizontally-scaled websocket fan-out) ---
    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False  # falls back to in-process pub/sub if False (fine for single-instance demo)

    # --- Scoring engine ---
    # Exponential decay half-life for citizen reports (minutes).
    # A report's contribution halves every `report_decay_half_life_minutes`.
    report_decay_half_life_minutes: float = 90.0
    # Reports older than this stop contributing at all (hours)
    report_max_age_hours: float = 3.0

    # Weight given to each signal type when blending into the 0-100 zone score.
    weight_unverified_report: float = 1.0
    weight_verified_report: float = 3.0
    weight_sensor: float = 2.5
    weight_weather: float = 1.5
    weight_municipal_override: float = 5.0

    # Zone status thresholds (0-100 score)
    threshold_moderate: float = 35.0
    threshold_severe: float = 65.0

    # Rate limiting
    max_reports_per_user_per_hour: int = 5
    max_reports_per_ip_per_hour: int = 8
    report_min_distance_meters: float = 15.0  # dedup near-identical spam reports
    report_min_interval_seconds: int = 60

    # Weather integration
    openweather_api_key: str = ""
    weather_poll_interval_seconds: int = 600  # 10 min

    # Background scoring job cadence (also triggered instantly on new data)
    scoring_tick_seconds: int = 30

    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
