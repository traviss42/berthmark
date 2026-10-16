"""Risk assessment, metric structures, and calculation models."""

from typing import Dict, List
from pydantic import BaseModel, Field
from app.models.common import RiskTier, SubRiskCategory, VesselClass


class CongestionMetrics(BaseModel):
    anchorageQueueCount: int = Field(..., description="Stationary/anchored vessels in port geofence (SOG <= 0.5 kn)", examples=[8])
    activeVesselCount: int = Field(default=0, description="Total live vessels detected in port geofence via AISStream", examples=[21])
    movingVesselCount: int = Field(default=0, description="Moving/maneuvering vessels in port geofence (SOG > 0.5 kn)", examples=[13])
    rolling30dAvgQueue: float = Field(default=0.0, description="Historical 30-day average stationary vessel count from SQLite snapshots", examples=[7.5])


class WeatherMetrics(BaseModel):
    windSpeedKnots: float = Field(..., description="Sustained wind speed in knots from Open-Meteo", examples=[28.4])
    waveHeightM: float = Field(..., description="Significant wave height in meters from Open-Meteo", examples=[2.3])
    swellPeriodSec: float = Field(..., description="Swell wave period in seconds from Open-Meteo", examples=[8.5])
    visibilityNm: float = Field(..., description="Visibility distance in nautical miles from Open-Meteo", examples=[6.2])
    gustSpeedKnots: float = Field(..., description="Peak wind gust speed in knots from Open-Meteo", examples=[35.1])


class NavigationalMetrics(BaseModel):
    underKeelClearanceM: float = Field(..., description="Derived depth margin: WPI controlling depth minus vessel class design draft (m)", examples=[2.1])
    channelDepthM: float = Field(..., description="Channel depth in meters from NGA World Port Index (Pub 150)", examples=[16.5])
    cargoPierDepthM: float = Field(default=0.0, description="Cargo pier / terminal depth in meters from NGA World Port Index (Pub 150)", examples=[14.0])
    anchorageDepthM: float = Field(default=0.0, description="Anchorage depth in meters from NGA World Port Index (Pub 150)", examples=[15.5])
    vesselDraftM: float = Field(default=12.0, description="Selected vessel class design draft in meters", examples=[12.0])
    overheadLimits: str = Field(default="Unknown", description="Overhead bridge/cable limits (Yes / No / Unknown) from NGA World Port Index", examples=["Yes"])
    pilotageAvailable: bool = Field(..., description="Harbor pilot availability from NGA World Port Index", examples=[True])
    tugsAssistance: bool = Field(default=True, description="Tug assistance availability from NGA World Port Index", examples=[True])
    tideHeightM: float = Field(..., description="Tidal range in meters from NGA World Port Index", examples=[1.8])
    harborSize: str = Field(default="Unknown", description="Harbor size from NGA World Port Index", examples=["Large"])
    shelterAfforded: str = Field(default="Unknown", description="Shelter afforded from NGA World Port Index", examples=["Good"])


class PortMetrics(BaseModel):
    portId: str = Field(..., examples=["port-nlrtm"])
    timestamp: str = Field(..., examples=["2026-10-16T00:00:00Z"])
    congestion: CongestionMetrics
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
    forceRefresh: bool = False
