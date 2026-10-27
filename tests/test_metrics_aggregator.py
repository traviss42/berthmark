"""Unit tests for Unified PortMetrics aggregator."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from backend.schemas.metrics import (
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    TerminalMetrics,
    WeatherMetrics,
)
from backend.services.port_metrics import assemble_port_metrics


@pytest.fixture
def sample_metrics_bundle():
    """Create valid sample instances of all 4 sub-metric domains."""
    congestion = CongestionMetrics(
        anchorageQueueCount=12,
        avgWaitingTimeHours=18.5,
        berthOccupancyPct=82.0,
        rolling30dAvgQueue=8.4,
        rolling30dAvgWaitHours=12.0,
    )
    terminal = TerminalMetrics(
        berthTurnaroundHours=26.4,
        berthToAnchorageWaitRatio=1.43,
        dwellTimeAnomalyScore=45.0,
        rolling30dAvgTurnaround=22.0,
    )
    weather = WeatherMetrics(
        windSpeedKnots=24.5,
        waveHeightM=1.8,
        swellPeriodSec=8.5,
        visibilityNm=6.0,
        gustSpeedKnots=32.0,
    )
    navigational = NavigationalMetrics(
        underKeelClearanceM=2.1,
        channelDepthM=16.5,
        airDraftClearanceM=8.5,
        pilotageAvailable=True,
        tideHeightM=0.0,
    )
    return congestion, terminal, weather, navigational


def test_assemble_port_metrics_success(sample_metrics_bundle):
    """Verify successful assembly of operational domains into PortMetrics."""
    congestion, terminal, weather, navigational = sample_metrics_bundle

    port_metrics = assemble_port_metrics(
        port_id="port-rotterdam",
        congestion=congestion,
        weather=weather,
        navigational=navigational,
        terminal=terminal,
        timestamp="2026-10-19T03:00:00Z",
    )

    assert port_metrics.portId == "port-rotterdam"
    assert port_metrics.congestion.anchorageQueueCount == 12
    assert port_metrics.terminal.berthTurnaroundHours == 26.4
    assert port_metrics.weather.windSpeedKnots == 24.5
    assert port_metrics.navigational.channelDepthM == 16.5

    # Serialization test
    serialized = port_metrics.model_dump(by_alias=True)
    assert serialized["portId"] == "port-rotterdam"
    assert serialized["timestamp"] == "2026-10-19T03:00:00Z"
    assert "congestion" in serialized
    assert "terminal" in serialized
    assert "weather" in serialized
    assert "navigational" in serialized


def test_assemble_port_metrics_without_terminal(sample_metrics_bundle):
    """Verify assembling PortMetrics cleanly without optional terminal metrics."""
    congestion, _, weather, navigational = sample_metrics_bundle

    port_metrics = assemble_port_metrics(
        port_id="port-rotterdam",
        congestion=congestion,
        weather=weather,
        navigational=navigational,
    )

    assert port_metrics.portId == "port-rotterdam"
    assert port_metrics.terminal is None
    assert port_metrics.congestion.anchorageQueueCount == 12
    assert port_metrics.weather.windSpeedKnots == 24.5
    assert port_metrics.navigational.channelDepthM == 16.5


def test_assemble_port_metrics_validation_errors(sample_metrics_bundle):
    """Verify validation error when portId is empty or any required sub-metric is None."""
    congestion, terminal, weather, navigational = sample_metrics_bundle

    # Blank port_id
    with pytest.raises(ValueError):
        assemble_port_metrics("", congestion, weather, navigational)

    with pytest.raises(ValueError):
        assemble_port_metrics("   ", congestion, weather, navigational)

    # Missing congestion
    with pytest.raises(ValueError):
        assemble_port_metrics("port-rotterdam", None, weather, navigational)

    # Missing weather
    with pytest.raises(ValueError):
        assemble_port_metrics("port-rotterdam", congestion, None, navigational)

    # Missing navigational
    with pytest.raises(ValueError):
        assemble_port_metrics("port-rotterdam", congestion, weather, None)
