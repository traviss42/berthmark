"""Notification models for user alerts and risk tier transitions."""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from app.models.common import RiskTier

NotificationType = Literal["stateChange", "dailyDigest", "inApp"]


class Notification(BaseModel):
    id: str = Field(..., examples=["notif-1729036800-abc123"])
    type: NotificationType
    portId: str = Field(..., examples=["port-rotterdam"])
    portName: str = Field(..., examples=["Port of Rotterdam"])
    title: str = Field(..., examples=["Port of Rotterdam: Risk tier changed to High"])
    message: str = Field(..., examples=["Port of Rotterdam risk status shifted from Medium to High."])
    tier: RiskTier
    previousTier: Optional[RiskTier] = Field(default=None, examples=["medium"])
    timestamp: str = Field(..., examples=["2026-10-16T00:00:00Z"])
    read: bool = Field(default=False)
    recipientEmail: Optional[str] = Field(
        default=None,
        description="Login email address where notification alert was dispatched",
        examples=["operations@maritime.com"],
    )
    emailDispatched: bool = Field(
        default=False,
        description="Whether outbound email notification was dispatched (suppressed during 30m cooldown or stream warm-up)",
    )


class CreateAlertRequest(BaseModel):
    portId: str = Field(..., examples=["port-rotterdam"])
    portName: str = Field(..., examples=["Port of Rotterdam"])
    newTier: RiskTier = Field(..., examples=["high"])
    previousTier: Optional[RiskTier] = Field(default=None, examples=["medium"])
