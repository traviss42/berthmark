"""Pydantic schemas for Notification feed and alert models conforming to openapi.yaml."""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from backend.schemas.risk import RiskTier

NotificationType = Literal["stateChange", "dailyDigest", "inApp"]


class Notification(BaseModel):
    """User alert notification representation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Unique notification identifier.")
    type: NotificationType = Field(..., description="Notification category event.")
    portId: str = Field(..., description="Associated port identifier.")
    portName: str = Field(..., description="Associated commercial port name.")
    title: str = Field(..., description="Descriptive headline of the alert.")
    message: str = Field(..., description="Detailed narrative of the state change or alert.")
    tier: RiskTier = Field(..., description="Active operational risk tier.")
    previousTier: RiskTier | None = Field(None, description="Previous risk tier before transition.")
    timestamp: datetime = Field(..., description="Timestamp of notification creation in UTC.")
    read: bool = Field(..., description="Whether notification has been marked as read.")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime):
            return v
        raise ValueError(f"Invalid timestamp: {v}")

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info: Any) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class NotificationCreate(BaseModel):
    """Payload to trigger or record a new risk state-change alert."""

    model_config = ConfigDict(populate_by_name=True)

    type: NotificationType = Field(default="stateChange", description="Notification category.")
    portId: str = Field(..., min_length=1, description="Associated port identifier.")
    portName: str = Field(..., min_length=1, description="Associated commercial port name.")
    newTier: RiskTier = Field(..., description="New operational risk tier.")
    previousTier: RiskTier | None = Field(None, description="Previous risk tier.")
