"""Pydantic schemas for Port Directory and Watchlist APIs."""

import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortResponse(BaseModel):
    """Schema representing commercial port metadata matching OpenAPI."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    locode: str
    country: str
    lat: float
    lon: float
    isDefault: bool = Field(default=False, alias="isDefault")
    geofenceRadiusNm: float = Field(default=8.0, alias="geofenceRadiusNm")
    addedByUserId: str | None = Field(default=None, alias="addedByUserId")
    vesselClass: str | None = Field(default=None, alias="vesselClass")


class PortCreate(BaseModel):
    """Schema for adding a custom port to user watchlist."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, description="Name of the commercial port.")
    locode: str = Field(..., description="Standard 5-character UN/LOCODE.")
    country: str = Field(..., min_length=1, description="Country name.")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Port latitude coordinate.")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Port longitude coordinate.")
    geofenceRadiusNm: float = Field(
        default=8.0, ge=1.0, le=50.0, alias="geofenceRadiusNm", description="Geofence radius in nautical miles."
    )
    vesselClass: str | None = Field(default=None, alias="vesselClass")

    @field_validator("name", "country")
    @classmethod
    def check_not_empty_or_whitespace(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("String cannot be empty or solely whitespace.")
        return v.strip()

    @field_validator("locode")
    @classmethod
    def check_locode_format(cls, v: str) -> str:
        if not v or not re.match(r"^[A-Z]{2}[A-Z0-9]{3}$", v):
            raise ValueError("UN/LOCODE must match pattern ^[A-Z]{2}[A-Z0-9]{3}$.")
        return v
