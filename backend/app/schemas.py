"""
Pydantic request/response schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, EmailStr

from .models import UserRole, ZoneStatus


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    role: UserRole = UserRole.citizen  # admin creation should be gated separately in production


class UserOut(BaseModel):
    id: str
    email: str
    phone: Optional[str] = None
    full_name: Optional[str] = None
    role: UserRole

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Zones ----------
class ZoneOut(BaseModel):
    id: str
    name: str
    code: str
    centroid_lat: float
    centroid_lng: float
    current_score: float
    current_status: ZoneStatus
    score_updated_at: datetime
    geojson: dict  # {"type": "Polygon", "coordinates": [...]}

    class Config:
        from_attributes = True


class ZoneDetailOut(ZoneOut):
    recent_reports: list["ReportOut"]
    rainfall_1h_mm: float
    rainfall_24h_mm: float
    historical_flood_prior: float


class ZoneScoreHistoryPoint(BaseModel):
    score: float
    status: ZoneStatus
    recorded_at: datetime
    rainfall_component: float

    class Config:
        from_attributes = True


# ---------- Reports ----------
class ReportCreate(BaseModel):
    lat: float
    lng: float
    water_depth_cm: float = Field(ge=0, le=300)
    photo_url: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


class ReportOut(BaseModel):
    id: str
    zone_id: str
    lat: float
    lng: float
    water_depth_cm: float
    photo_url: Optional[str] = None
    note: Optional[str] = None
    is_verified: bool
    is_municipal_override: bool
    is_dismissed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReportModerate(BaseModel):
    action: str  # "verify" | "dismiss"


# ---------- Sensors ----------
class SensorReadingIn(BaseModel):
    water_depth_cm: float = Field(ge=0, le=300)
    battery_pct: Optional[float] = Field(default=None, ge=0, le=100)


class SensorOut(BaseModel):
    id: str
    zone_id: str
    name: str
    lat: float
    lng: float
    is_active: bool

    class Config:
        from_attributes = True


# ---------- Weather ----------
class WeatherIngest(BaseModel):
    zone_id: str
    rainfall_1h_mm: float
    rainfall_24h_mm: float
    condition: Optional[str] = None


# ---------- WebSocket payloads ----------
class ZoneUpdateEvent(BaseModel):
    type: str = "zone_update"
    zone_id: str
    code: str
    name: str
    score: float
    status: ZoneStatus
    status_changed: bool
    updated_at: datetime


# ---------- Admin analytics ----------
class ZoneAnalytics(BaseModel):
    zone_id: str
    name: str
    code: str
    avg_score_30d: float
    max_score_30d: float
    severe_incidents_30d: int
    total_reports_30d: int
    verified_reports_30d: int


ZoneDetailOut.model_rebuild()
