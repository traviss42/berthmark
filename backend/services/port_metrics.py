"""Unified operational port metrics aggregator."""

from datetime import datetime, timezone
from typing import Any

from backend.schemas.metrics import (
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    TerminalMetrics,
    WeatherMetrics,
)


def assemble_port_metrics(
    port_id: str,
    congestion: CongestionMetrics,
    weather: WeatherMetrics,
    navigational: NavigationalMetrics,
    terminal: TerminalMetrics | None = None,
    timestamp: datetime | str | None = None,
) -> PortMetrics:
    """Aggregate operational domains into a unified PortMetrics schema object.

    Args:
        port_id: Unique port identifier (e.g. 'port-rotterdam').
        congestion: CongestionMetrics instance.
        weather: WeatherMetrics instance.
        navigational: NavigationalMetrics instance.
        terminal: Optional TerminalMetrics instance.
        timestamp: Optional observation timestamp (defaults to current UTC).

    Returns:
        PortMetrics conforming to openapi.yaml.

    Raises:
        ValueError: If port_id is empty or missing, or required sub-metric is None.
    """
    if not port_id or not port_id.strip():
        raise ValueError("port_id cannot be empty or solely whitespace.")

    if congestion is None:
        raise ValueError("congestion metrics cannot be None.")
    if weather is None:
        raise ValueError("weather metrics cannot be None.")
    if navigational is None:
        raise ValueError("navigational metrics cannot be None.")

    if timestamp is None:
        obs_time = datetime.now(timezone.utc)
    elif isinstance(timestamp, str):
        obs_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    else:
        obs_time = timestamp

    if obs_time.tzinfo is None:
        obs_time = obs_time.replace(tzinfo=timezone.utc)

    return PortMetrics(
        portId=port_id.strip(),
        timestamp=obs_time,
        congestion=congestion,
        weather=weather,
        navigational=navigational,
        terminal=terminal,
    )
