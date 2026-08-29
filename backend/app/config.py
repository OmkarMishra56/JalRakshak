
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aquaalert:aquaalert@localhost:5432/aquaalert"
    sync_database_url: str = "postgresql://aquaalert:aquaalert@localhost:5432/aquaalert"

    
    jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_env_JWT_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12  

    
    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False  

    
    report_decay_half_life_minutes: float = 90.0
    report_max_age_hours: float = 3.0
    weight_unverified_report: float = 1.0
    weight_verified_report: float = 3.0
    weight_sensor: float = 2.5
    weight_weather: float = 1.5
    weight_municipal_override: float = 5.0
    threshold_moderate: float = 35.0
    threshold_severe: float = 65.0
    max_reports_per_user_per_hour: int = 5
    max_reports_per_ip_per_hour: int = 8
    report_min_distance_meters: float = 15.0  
    report_min_interval_seconds: int = 60

    
    openweather_api_key: str = ""
    weather_poll_interval_seconds: int = 600  

    scoring_tick_seconds: int = 30

    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
