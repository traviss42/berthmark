"""Service module exposing external API client functions with SQLite caching."""

from typing import Optional, Tuple
from app.clients.ais_client import AISClient
from app.clients.weather_client import MarineWeatherClient
from app.models.risk import (
    CongestionMetrics,
    NavigationalMetrics,
    TerminalMetrics,
    WeatherMetrics,
)

weather_client = MarineWeatherClient()
ais_client = AISClient()


async def get_marine_weather(
    lat: float, lon: float, port_id: str = "", force_refresh: bool = False
) -> WeatherMetrics:
    """Fetch marine weather with SQLite caching (< 30 min freshness)."""
    return await weather_client.get_marine_weather(
        lat=lat, lon=lon, port_id=port_id, force_refresh=force_refresh
    )


async def get_port_traffic_metrics(
    port_id: str,
    locode: str,
    vessel_class: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    geofence_radius_nm: float = 8.0,
    force_refresh: bool = False,
) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
    """Fetch AIS traffic metrics with SQLite caching (< 30 min freshness)."""
    return await ais_client.get_port_traffic_metrics(
        port_id=port_id,
        locode=locode,
        vessel_class=vessel_class,
        lat=lat,
        lon=lon,
        geofence_radius_nm=geofence_radius_nm,
        force_refresh=force_refresh,
    )


# Aliases for convenience
fetch_marine_weather = get_marine_weather
fetch_ais_traffic = get_port_traffic_metrics
