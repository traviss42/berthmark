"""Pydantic schemas for alternative port diversion recommendations."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AlternativePortRecommendation(BaseModel):
    """Recommended alternative port when primary port experiences elevated operational risk."""

    model_config = ConfigDict(populate_by_name=True)

    portId: str = Field(..., description="Unique port identifier or LOCODE.")
    unlocode: str = Field(..., min_length=5, max_length=5, description="5-character UN/LOCODE.")
    portName: str = Field(..., description="Official commercial port name.")
    country: str = Field(..., description="ISO 3166-1 alpha-2 country code.")
    distanceNm: float = Field(..., ge=0.0, description="Nautical distance from primary port in NM.")
    channelDepthM: float = Field(..., ge=0.0, description="Controlling channel depth in meters.")
    depthMarginM: float = Field(..., description="Controlling channel depth minus required UKC clearance in meters.")
    swellHeightM: float = Field(..., ge=0.0, description="Significant swell wave height in meters.")
    riskTier: Literal["low", "medium"] = Field(..., description="Alternative port operational risk tier.")
    trafficStatus: str = Field(..., description="Summary of anchored and underway vessel traffic.")
    lat: float | None = Field(default=None, description="Geographic latitude of alternative port.")
    lon: float | None = Field(default=None, description="Geographic longitude of alternative port.")


# Alias for flexible naming convention
PortRecommendation = AlternativePortRecommendation
