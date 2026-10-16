"""Models package re-exporting all schemas and database cache models."""

try:
    from app.models import *
    from app.models.external_cache import ExternalAISTrafficCache, ExternalWeatherCache
except ImportError:
    from backend.app.models import *
    from backend.app.models.external_cache import ExternalAISTrafficCache, ExternalWeatherCache

__all__ = [
    "RiskTier",
    "SubRiskCategory",
    "VesselSector",
    "VesselClass",
    "Port",
    "CreatePortRequest",
    "UpdatePortNotificationsRequest",
    "CongestionMetrics",
    "TerminalMetrics",
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
