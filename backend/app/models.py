
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Enum,
    Text, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

from .database import Base


def gen_uuid():
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    citizen = "citizen"
    municipal_admin = "municipal_admin"
    super_admin = "super_admin"


class ZoneStatus(str, enum.Enum):
    safe = "safe"          
    moderate = "moderate"  
    severe = "severe"      


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, unique=True, nullable=True, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.citizen, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reports = relationship("Report", back_populates="reporter")


class Zone(Base):
    """
    A ward / administrative zone. Geometry is a polygon in WGS84 (lat/lng, SRID 4326).
    current_score / current_status are denormalized cache columns updated by the
    scoring engine so reads (map load) never need to recompute on the fly.
    """
    __tablename__ = "zones"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False)  
    geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    centroid_lat = Column(Float, nullable=False)
    centroid_lng = Column(Float, nullable=False)

    
    historical_flood_prior = Column(Float, default=10.0)  
    current_score = Column(Float, default=0.0, nullable=False)
    current_status = Column(Enum(ZoneStatus), default=ZoneStatus.safe, nullable=False)
    score_updated_at = Column(DateTime(timezone=True), server_default=func.now())

    reports = relationship("Report", back_populates="zone")
    sensors = relationship("Sensor", back_populates="zone")
    weather_snapshots = relationship("WeatherSnapshot", back_populates="zone")
    score_history = relationship("ZoneScoreHistory", back_populates="zone")

    

class Report(Base):
    """
    Citizen (or municipal) waterlogging report.
    verified reports come from municipal_admin review or a municipal override
    and are weighted much higher in the scoring engine.
    """
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    zone_id = Column(UUID(as_uuid=False), ForeignKey("zones.id"), nullable=False, index=True)
    reporter_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)

    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)

    water_depth_cm = Column(Float, nullable=False)  
    photo_url = Column(String, nullable=True)
    note = Column(Text, nullable=True)

    is_verified = Column(Boolean, default=False)          
    is_municipal_override = Column(Boolean, default=False)  
    is_dismissed = Column(Boolean, default=False)       

    source_ip = Column(String, nullable=True)  
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    zone = relationship("Zone", back_populates="reports")
    reporter = relationship("User", back_populates="reports")

    __table_args__ = (
        Index("idx_reports_zone_created", "zone_id", "created_at"),
    )


class Sensor(Base):
    """
    A physical ultrasonic depth sensor (or any IoT depth device) registered to a zone.
    Pushes readings via the /sensors/{id}/readings webhook.
    """
    __tablename__ = "sensors"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    zone_id = Column(UUID(as_uuid=False), ForeignKey("zones.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    api_key = Column(String, nullable=False, unique=True) 
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    zone = relationship("Zone", back_populates="sensors")
    readings = relationship("SensorReading", back_populates="sensor")


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    sensor_id = Column(UUID(as_uuid=False), ForeignKey("sensors.id"), nullable=False, index=True)
    water_depth_cm = Column(Float, nullable=False)
    battery_pct = Column(Float, nullable=True)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    sensor = relationship("Sensor", back_populates="readings")


class WeatherSnapshot(Base):
    """
    Per-zone rainfall snapshot, polled from a weather provider (e.g. OpenWeatherMap)
    or pushed manually. rainfall_1h / rainfall_24h in mm.
    """
    __tablename__ = "weather_snapshots"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    zone_id = Column(UUID(as_uuid=False), ForeignKey("zones.id"), nullable=False, index=True)
    rainfall_1h_mm = Column(Float, default=0.0)
    rainfall_24h_mm = Column(Float, default=0.0)
    condition = Column(String, nullable=True)  # e.g. "Heavy Rain", "Clear"
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    zone = relationship("Zone", back_populates="weather_snapshots")


class ZoneScoreHistory(Base):
    """
    Append-only log of score changes, used for the admin analytics dashboard
    (which zones flood most, correlation with rainfall) and for status-change
    detection (so we only push a WebSocket event when Safe/Moderate/Severe
    actually flips, not on every minor score wobble).
    """
    __tablename__ = "zone_score_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    zone_id = Column(UUID(as_uuid=False), ForeignKey("zones.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    status = Column(Enum(ZoneStatus), nullable=False)
    contributing_reports = Column(Integer, default=0)
    contributing_sensors = Column(Integer, default=0)
    rainfall_component = Column(Float, default=0.0)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    zone = relationship("Zone", back_populates="score_history")

    __table_args__ = (
        Index("idx_score_history_zone_time", "zone_id", "recorded_at"),
    )
