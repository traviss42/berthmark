"""SQLAlchemy 2.0 ORM models for Berthmark."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy 2.0 models."""
    pass


class User(Base):
    """User account entity for platform authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Port(Base):
    """Port entity storing physical channel depths and geospatial location."""

    __tablename__ = "ports"
    __table_args__ = (
        Index("ix_ports_country_subdivision", "country_code", "subdivision_code"),
    )

    unlocode: Mapped[str] = mapped_column(String(5), primary_key=True)
    port_name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_code: Mapped[str] = mapped_column(CHAR(2), nullable=False)
    subdivision_code: Mapped[str] = mapped_column(String(10), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    wpi_number: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    channel_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    cargo_pier_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    anchorage_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_depth_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reconciliation_method: Mapped[str] = mapped_column(
        String(20), default="EXACT_UNLOCODE", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    watchlists: Mapped[list["UserWatchlist"]] = relationship(
        back_populates="port", cascade="all, delete-orphan"
    )
    baselines: Mapped[list["PortTrafficBaseline"]] = relationship(
        back_populates="port", cascade="all, delete-orphan"
    )
    risk_snapshots: Mapped[list["PortRiskSnapshot"]] = relationship(
        back_populates="port", cascade="all, delete-orphan"
    )
    alert_logs: Mapped[list["AlertLog"]] = relationship(
        back_populates="port", cascade="all, delete-orphan"
    )


class VesselClass(Base):
    """Standard commercial vessel class taxonomy definition."""

    __tablename__ = "vessel_classes"

    class_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    class_name: Mapped[str] = mapped_column(String(50), nullable=False)
    draft_m: Mapped[float] = mapped_column(Float, nullable=False)
    beam_m: Mapped[float] = mapped_column(Float, nullable=False)
    loa_m: Mapped[float] = mapped_column(Float, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(30), nullable=True)
    criteria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    significance: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    watchlists: Mapped[list["UserWatchlist"]] = relationship(
        back_populates="vessel_class", cascade="all, delete-orphan"
    )
    risk_snapshots: Mapped[list["PortRiskSnapshot"]] = relationship(
        back_populates="vessel_class", cascade="all, delete-orphan"
    )
    alert_logs: Mapped[list["AlertLog"]] = relationship(
        back_populates="vessel_class", cascade="all, delete-orphan"
    )


class UserWatchlist(Base):
    """User-specific watchlist subscription pairing a port and vessel class."""

    __tablename__ = "user_watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "unlocode", "vessel_class_id", name="uq_user_watchlist_entry"),
    )

    watchlist_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    unlocode: Mapped[str] = mapped_column(
        String(5), ForeignKey("ports.unlocode", ondelete="CASCADE"), nullable=False
    )
    vessel_class_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("vessel_classes.class_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    port: Mapped["Port"] = relationship(back_populates="watchlists")
    vessel_class: Mapped["VesselClass"] = relationship(back_populates="watchlists")


class PortTrafficBaseline(Base):
    """Historical traffic baselines across 168 weekly hourly slots."""

    __tablename__ = "port_traffic_baselines"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="chk_baseline_day_of_week"),
        CheckConstraint("hour_of_day BETWEEN 0 AND 23", name="chk_baseline_hour_of_day"),
        UniqueConstraint("unlocode", "day_of_week", "hour_of_day", name="uq_port_baseline_slot"),
    )

    baseline_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    unlocode: Mapped[str] = mapped_column(
        String(5), ForeignKey("ports.unlocode", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_anchored_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_underway_count: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_total_active: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    port: Mapped["Port"] = relationship(back_populates="baselines")


class PortRiskSnapshot(Base):
    """Dynamic operational risk snapshot per port and vessel class."""

    __tablename__ = "port_risk_snapshots"
    __table_args__ = (
        CheckConstraint(
            "grounding_risk_level IS NULL OR grounding_risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name="chk_snapshot_grounding_risk",
        ),
        CheckConstraint(
            "congestion_risk_level IS NULL OR congestion_risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name="chk_snapshot_congestion_risk",
        ),
        CheckConstraint(
            "weather_risk_level IS NULL OR weather_risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name="chk_snapshot_weather_risk",
        ),
        CheckConstraint(
            "overall_risk_level IS NULL OR overall_risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name="chk_snapshot_overall_risk",
        ),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    unlocode: Mapped[str] = mapped_column(
        String(5), ForeignKey("ports.unlocode", ondelete="CASCADE"), nullable=False
    )
    vessel_class_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("vessel_classes.class_id", ondelete="CASCADE"), nullable=False
    )
    grounding_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    anchored_vessel_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    underway_vessel_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_active_geofence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_avg_queue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    queue_variance_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    congestion_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    weather_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    overall_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    swell_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kts: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    # Relationships
    port: Mapped["Port"] = relationship(back_populates="risk_snapshots")
    vessel_class: Mapped["VesselClass"] = relationship(back_populates="risk_snapshots")


class AlertLog(Base):
    """Historical record of threshold state changes for user alert feeds."""

    __tablename__ = "alert_logs"

    alert_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    unlocode: Mapped[str] = mapped_column(
        String(5), ForeignKey("ports.unlocode", ondelete="CASCADE"), nullable=False
    )
    vessel_class_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("vessel_classes.class_id", ondelete="CASCADE"), nullable=False
    )
    previous_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    new_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    port: Mapped["Port"] = relationship(back_populates="alert_logs")
    vessel_class: Mapped["VesselClass"] = relationship(back_populates="alert_logs")
