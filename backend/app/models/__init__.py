"""Export all models."""

from app.models.common import RiskTier, SubRiskCategory, VesselClass, VesselSector
from app.models.error import ErrorResponse
from app.models.auth import LoginRequest, LoginResponse, UserResponse
from app.models.notification import CreateAlertRequest, Notification, NotificationType
from app.models.port import CreatePortRequest, Port, UpdatePortNotificationsRequest
from app.models.risk import (
    BulkRiskAssessmentRequest,
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    PortRef,
    RiskAssessment,
    SubRiskResult,
    WeatherMetrics,
)

def __getattr__(name: str):
    if name in ("ExternalAISTrafficCache", "ExternalWeatherCache"):
        from app.models import external_cache
        return getattr(external_cache, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "RiskTier",
    "SubRiskCategory",
    "VesselSector",
    "VesselClass",
    "Port",
    "CreatePortRequest",
    "UpdatePortNotificationsRequest",
    "CongestionMetrics",
    "WeatherMetrics",
    "NavigationalMetrics",
    "PortMetrics",
    "SubRiskResult",

    "RiskAssessment",
    "PortRef",
    "BulkRiskAssessmentRequest",
    "NotificationType",
    "Notification",
    "CreateAlertRequest",
    "ErrorResponse",
    "LoginRequest",
    "LoginResponse",
    "UserResponse",
    "ExternalWeatherCache",
    "ExternalAISTrafficCache",
]
