"""Pydantic schemas for risk assessment models conforming to openapi.yaml."""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from backend.schemas.metrics import PortMetrics, SubRiskResult

RiskTier = Literal["low", "medium", "high"]


class BulkRiskPortItem(BaseModel):
    """Port item within bulk risk assessment request."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., min_length=1, description="Target port ID or UN/LOCODE.")
    name: str | None = Field(None, description="Optional human-readable port name.")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Port id must be a non-empty string.")
        return v.strip()


VALID_VESSEL_CLASSES: set[str] = {
    "feeder",
    "panamax",
    "neoPanamax",
    "ulcv",
    "mrTanker",
    "aframax",
    "suezmax",
    "vlcc",
    "handysize",
    "panamaxBulk",
    "capesize",
    "pctc",
    "lng",
}


class BulkRiskAssessmentRequest(BaseModel):
    """Request payload for bulk risk assessment evaluations."""

    model_config = ConfigDict(populate_by_name=True)

    ports: list[BulkRiskPortItem] = Field(..., min_length=1, description="List of target ports to assess.")
    vesselClass: str = Field(..., min_length=1, description="Target benchmark vessel class.")

    @field_validator("vesselClass")
    @classmethod
    def validate_vessel_class(cls, v: Any) -> str:
        if not isinstance(v, str) or v not in VALID_VESSEL_CLASSES:
            raise ValueError(f"Invalid vesselClass '{v}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}")
        return v


class SubRisksDict(BaseModel):
    """Container for the four operational sub-risk evaluation results."""

    model_config = ConfigDict(populate_by_name=True)

    congestion: SubRiskResult
    terminalDelays: SubRiskResult
    weather: SubRiskResult
    navigational: SubRiskResult


class RiskAssessment(BaseModel):
    """Complete composite risk assessment for a port and vessel class."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Unique assessment calculation key.")
    portId: str = Field(..., description="Unique port ID.")
    portName: str = Field(..., description="Human-readable port name.")
    vesselClass: str = Field(..., description="Target vessel benchmark class.")
    vesselClassLabel: str = Field(..., description="Human-readable vessel class label.")
    timestamp: datetime = Field(..., description="Assessment timestamp in UTC.")
    compositeTier: RiskTier = Field(..., description="Overall composite risk tier.")
    compositeScore: float = Field(..., ge=0.0, le=100.0, description="Overall composite score (0-100).")
    subRisks: SubRisksDict
    metrics: PortMetrics

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt
        if isinstance(v, datetime):
            return v
        raise ValueError(f"Invalid timestamp value: {v}")

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime, _info: Any) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
