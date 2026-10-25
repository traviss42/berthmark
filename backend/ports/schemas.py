"""Pydantic schemas for Port Directory API."""

from pydantic import BaseModel, ConfigDict, Field


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
