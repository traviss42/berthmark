"""Port domain models for tracking, search, and configuration."""

from typing import Optional
from pydantic import BaseModel, Field


class Port(BaseModel):
    id: str = Field(..., description="Unique port identifier", examples=["port-rotterdam"])
    name: str = Field(..., description="Official port name", examples=["Port of Rotterdam"])
    locode: str = Field(
        ...,
        pattern=r"^[A-Z]{2}[A-Z0-9]{3}$",
        description="UN/LOCODE standard 5-character port code",
        examples=["NLRTM"],
    )
    country: str = Field(..., description="Country name", examples=["Netherlands"])
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees", examples=[51.9244])
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees", examples=[4.4777])
    isDefault: bool = Field(..., description="Whether this is a global default port", examples=[True])
    geofenceRadiusNm: float = Field(..., description="Configured geofence boundary in nautical miles", examples=[8.0])
    addedByUserId: Optional[str] = Field(
        default=None,
        description="User ID for private custom ports; null for default ports",
        examples=[None],
    )
    notificationsEnabled: bool = Field(
        default=True,
        description="Whether email notifications and risk alerts are enabled for this port",
        examples=[True],
    )


class CreatePortRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Official port name", examples=["Port of Antwerp-Bruges"])
    locode: str = Field(
        ...,
        pattern=r"^[A-Z]{2}[A-Z0-9]{3}$",
        description="UN/LOCODE 5-character code",
        examples=["BEANR"],
    )
    country: str = Field(..., min_length=1, description="Country name", examples=["Belgium"])
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees", examples=[51.3])
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees", examples=[4.3])
    geofenceRadiusNm: float = Field(
        default=8.0,
        ge=1.0,
        le=50.0,
        description="Configured geofence radius in nautical miles",
        examples=[8.0],
    )
    notificationsEnabled: bool = Field(
        default=True,
        description="Opt into state transition email alerts for this port by default",
        examples=[True],
    )


class UpdatePortNotificationsRequest(BaseModel):
    notificationsEnabled: bool = Field(
        ...,
        description="Enable or disable email alerts for this port",
        examples=[True],
    )
