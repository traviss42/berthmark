"""SQLAlchemy database models for monitored ports and notifications."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.port import Port
from app.models.notification import Notification


class MonitoredPort(Base):
    """Database model for ports monitored by users."""

    __tablename__ = "monitored_ports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    locode: Mapped[str] = mapped_column(String(10), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    geofence_radius_nm: Mapped[float] = mapped_column(Float, default=8.0, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "locode", name="uq_user_port_locode"),
    )

    def to_pydantic(self) -> Port:
        """Convert database entity to Pydantic Port schema."""
        return Port(
            id=self.id,
            name=self.name,
            locode=self.locode,
            country=self.country,
            lat=self.lat,
            lon=self.lon,
            isDefault=self.is_default,
            geofenceRadiusNm=self.geofence_radius_nm,
            addedByUserId=self.user_id,
            notificationsEnabled=self.notifications_enabled,
        )


class NotificationRecord(Base):
    """Database model for user risk alerts and notifications."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="stateChange")
    port_id: Mapped[str] = mapped_column(String(64), nullable=False)
    port_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    timestamp: Mapped[str] = mapped_column(String(50), nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),
    )

    def to_pydantic(self) -> Notification:
        """Convert database entity to Pydantic Notification schema."""
        return Notification(
            id=self.id,
            type=self.type,  # type: ignore
            portId=self.port_id,
            portName=self.port_name,
            title=self.title,
            message=self.message,
            tier=self.tier,  # type: ignore
            previousTier=self.previous_tier,  # type: ignore
            timestamp=self.timestamp,
            read=self.read,
            recipientEmail=self.recipient_email,
        )
