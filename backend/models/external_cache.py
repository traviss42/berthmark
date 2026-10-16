"""SQLAlchemy models for external API caching re-exported for backend.models namespace."""

try:
    from app.models.external_cache import ExternalAISTrafficCache, ExternalWeatherCache
except ImportError:
    from backend.app.models.external_cache import ExternalAISTrafficCache, ExternalWeatherCache

__all__ = ["ExternalWeatherCache", "ExternalAISTrafficCache"]
