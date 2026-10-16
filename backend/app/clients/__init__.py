"""External API and dataset client package."""

from app.clients.ais_client import AISClient
from app.clients.ports_client import PortDirectoryClient
from app.clients.unlocode_db import (
    UnlocodeDatabase,
    is_maritime_port,
    parse_unlocode_coordinates,
)
from app.clients.weather_client import MarineWeatherClient

__all__ = [
    "MarineWeatherClient",
    "AISClient",
    "PortDirectoryClient",
    "UnlocodeDatabase",
    "parse_unlocode_coordinates",
    "is_maritime_port",
]
