"""Pydantic schemas for operational metrics and sub-risk assessment models."""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class CongestionMetrics(BaseModel):
    """Real-time and baseline congestion metrics."""

    model_config = ConfigDict(populate_by_name=True)

    anchorageQueueCount: int = Field(..., ge=0, description="Count of stationary/anchored vessels.")
    avgWaitingTimeHours: float = Field(..., ge=0.0, description="Average anchorage waiting time in hours.")
    berthOccupancyPct: float = Field(..., ge=0.0, le=100.0, description="Current berth occupancy percentage.")
    rolling30dAvgQueue: float = Field(..., ge=0.0, description="Rolling 30-day historical average queue count.")
    rolling30dAvgWaitHours: float = Field(..., ge=0.0, description="Rolling 30-day historical average wait hours.")


class TerminalMetrics(BaseModel):
    """Terminal turnaround, dwell, and operational processing metrics."""

    model_config = ConfigDict(populate_by_name=True)

    berthTurnaroundHours: float = Field(..., ge=0.0, description="Average turnaround time at berth in hours.")
    berthToAnchorageWaitRatio: float = Field(..., ge=0.0, description="Ratio of berth time to anchorage waiting time.")
    dwellTimeAnomalyScore: float = Field(..., ge=0.0, le=100.0, description="Dwell time anomaly score (0-100).")
    rolling30dAvgTurnaround: float = Field(..., ge=0.0, description="Rolling 30-day baseline turnaround hours.")


class WeatherMetrics(BaseModel):
    """Real-time marine swell and atmospheric weather metrics."""

    model_config = ConfigDict(populate_by_name=True)

    windSpeedKnots: float = Field(..., ge=0.0, description="Sustained wind speed in knots.")
    waveHeightM: float = Field(..., ge=0.0, description="Significant wave height in meters.")
    swellPeriodSec: float = Field(..., ge=0.0, description="Primary swell period in seconds.")
    visibilityNm: float = Field(..., ge=0.0, description="Visibility distance in nautical miles.")
    gustSpeedKnots: float = Field(..., ge=0.0, description="Peak wind gusts in knots.")


class NavigationalMetrics(BaseModel):
    """Physical channel depth, tidal water level, and air draft clearances."""

    model_config = ConfigDict(populate_by_name=True)

    underKeelClearanceM: float = Field(..., description="Under-Keel Clearance (UKC) margin in meters.")
    channelDepthM: float = Field(..., ge=0.0, description="Controlling channel depth in meters.")
    airDraftClearanceM: float = Field(..., description="Air draft clearance beneath bridges/cables in meters.")
    pilotageAvailable: bool = Field(..., description="Whether harbor pilotage is operational.")
    tideHeightM: float = Field(..., description="Current water tide elevation in meters.")


class PortMetrics(BaseModel):
    """Unified 4-dimensional operational metrics for a port."""

    model_config = ConfigDict(populate_by_name=True)

    portId: str = Field(..., min_length=1, description="Unique port identifier.")
    timestamp: datetime = Field(..., description="Timestamp of observation in UTC.")
    congestion: CongestionMetrics
    terminal: TerminalMetrics
    weather: WeatherMetrics
    navigational: NavigationalMetrics

    @field_validator("portId")
    @classmethod
    def validate_port_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("portId cannot be empty or solely whitespace.")
        return v.strip()

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info: Any) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SubRiskResult(BaseModel):
    """Individual operational sub-risk evaluation result."""

    model_config = ConfigDict(populate_by_name=True)

    category: Literal["congestion", "terminalDelays", "weather", "navigational"]
    tier: Literal["low", "medium", "high"]
    score: float = Field(..., ge=0.0, le=100.0, description="Normalized risk score (Low ~25, Medium ~60, High ~90).")
    detail: str = Field(..., min_length=1, description="Analytical explanation of risk tier.")
    factors: list[str] = Field(..., description="Specific contributing factors triggering thresholds.")
