"""Risk assessment, metric structures, and calculation models."""

from typing import Dict, List
from pydantic import BaseModel, Field
from app.models.common import RiskTier, SubRiskCategory, VesselClass


class CongestionMetrics(BaseModel):
    anchorageQueueCount: int = Field(..., description="Active vessels in anchorage queue", examples=[18])
    avgWaitingTimeHours: float = Field(..., description="Average anchorage wait time in hours", examples=[28.5])
    berthOccupancyPct: float = Field(..., ge=0.0, le=100.0, description="Berth occupancy percentage", examples=[82.0])
    rolling30dAvgQueue: float = Field(..., description="Historical 30-day average queue count", examples=[14.2])
    rolling30dAvgWaitHours: float = Field(..., description="Historical 30-day average wait time", examples=[22.1])


class TerminalMetrics(BaseModel):
    berthTurnaroundHours: float = Field(..., description="Average turnaround time at berth", examples=[36.4])
    berthToAnchorageWaitRatio: float = Field(..., description="Ratio of turnaround to wait time", examples=[1.28])
    dwellTimeAnomalyScore: float = Field(..., description="Dwell time anomaly score (0-100)", examples=[1.15])
    rolling30dAvgTurnaround: float = Field(..., description="Historical 30-day average turnaround", examples=[32.0])


class WeatherMetrics(BaseModel):
    windSpeedKnots: float = Field(..., description="Sustained wind speed in knots", examples=[28.4])
    waveHeightM: float = Field(..., description="Significant wave height in meters", examples=[2.3])
    swellPeriodSec: float = Field(..., description="Swell period in seconds", examples=[8.5])
    visibilityNm: float = Field(..., description="Visibility distance in nautical miles", examples=[6.2])
    gustSpeedKnots: float = Field(..., description="Peak wind gust speed in knots", examples=[35.1])


class NavigationalMetrics(BaseModel):
    underKeelClearanceM: float = Field(..., description="Under-keel clearance in meters", examples=[2.1])
    channelDepthM: float = Field(..., description="Channel navigation depth in meters", examples=[16.5])
    airDraftClearanceM: float = Field(..., description="Air draft clearance under bridges in meters", examples=[8.4])
    pilotageAvailable: bool = Field(..., description="Harbor pilot availability", examples=[True])
    tideHeightM: float = Field(..., description="Tidal height above chart datum in meters", examples=[1.8])


class PortMetrics(BaseModel):
    portId: str = Field(..., examples=["port-rotterdam"])
    timestamp: str = Field(..., examples=["2026-10-16T00:00:00Z"])
    congestion: CongestionMetrics
    terminal: TerminalMetrics
    weather: WeatherMetrics
    navigational: NavigationalMetrics


class SubRiskResult(BaseModel):
    category: SubRiskCategory
    tier: RiskTier
    score: float = Field(..., ge=0.0, le=100.0, examples=[60.0])
    detail: str = Field(..., examples=["Elevated congestion above rolling baseline."])
    factors: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    id: str = Field(..., examples=["risk-rotterdam-neoPanamax-1729036800"])
    portId: str = Field(..., examples=["port-rotterdam"])
    portName: str = Field(..., examples=["Port of Rotterdam"])
    vesselClass: VesselClass
    vesselClassLabel: str = Field(..., examples=["Neo-Panamax"])
    timestamp: str = Field(..., examples=["2026-10-16T00:00:00Z"])
    compositeTier: RiskTier
    compositeScore: float = Field(..., ge=0.0, le=100.0, examples=[60.0])
    subRisks: Dict[SubRiskCategory, SubRiskResult]
    metrics: PortMetrics


class PortRef(BaseModel):
    id: str = Field(..., examples=["port-rotterdam"])
    name: str = Field(..., examples=["Port of Rotterdam"])


class BulkRiskAssessmentRequest(BaseModel):
    ports: List[PortRef]
    vesselClass: VesselClass
