"""Tests for external API clients, mocking HTTP requests and verifying fallback behaviors."""

import httpx
import pytest
from app.clients.ais_client import AISClient
from app.clients.ports_client import PortDirectoryClient
from app.clients.weather_client import MarineWeatherClient


@pytest.mark.asyncio
async def test_weather_client_with_successful_mock_response(monkeypatch):
    """When weather API returns 200, client correctly parses response."""
    mock_payload = {
        "current": {"wave_height": 2.8},
        "hourly": {
            "wind_speed_10m": [32.5, 30.1],
            "wind_gusts_10m": [42.0, 39.5],
        },
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_payload

    async def mock_get(self, url, params=None, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    result = await client.get_marine_weather(lat=51.9, lon=4.4, port_id="port-rotterdam")

    assert result.waveHeightM == 2.8
    assert result.windSpeedKnots == 32.5
    assert result.gustSpeedKnots == 42.0


@pytest.mark.asyncio
async def test_weather_client_fallback_on_network_error(monkeypatch):
    """When weather API throws network error, client provides deterministic fallback."""
    async def mock_get_error(self, url, **kwargs):
        raise httpx.ConnectError("Network unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_error)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    result = await client.get_marine_weather(lat=51.9, lon=4.4, port_id="port-rotterdam")

    assert result.windSpeedKnots > 0
    assert result.gustSpeedKnots >= result.windSpeedKnots
    assert result.waveHeightM > 0
    assert result.visibilityNm > 0


@pytest.mark.asyncio
async def test_ais_client_with_mock_response(monkeypatch):
    """When AIS API returns 200, client parses congestion, terminal, and navigational metrics."""
    mock_payload = {
        "congestion": {
            "anchorageQueueCount": 15,
            "avgWaitingTimeHours": 24.0,
            "berthOccupancyPct": 80.0,
            "rolling30dAvgQueue": 12.0,
            "rolling30dAvgWaitHours": 20.0,
        },
        "terminal": {
            "berthTurnaroundHours": 30.0,
            "berthToAnchorageWaitRatio": 0.5,
            "dwellTimeAnomalyScore": 35.0,
            "rolling30dAvgTurnaround": 28.0,
        },
        "navigational": {
            "underKeelClearanceM": 2.5,
            "channelDepthM": 16.0,
            "airDraftClearanceM": 8.0,
            "pilotageAvailable": True,
            "tideHeightM": 1.5,
        },
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_payload

    async def mock_get(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = AISClient(api_key="test-api-key", base_url="https://mock-ais.example.com")
    congestion, terminal, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "panamax"
    )

    assert congestion.anchorageQueueCount == 15
    assert terminal.berthTurnaroundHours == 30.0
    assert navigational.channelDepthM == 16.0


@pytest.mark.asyncio
async def test_ais_client_fallback_when_unconfigured():
    """When no API key is provided, AISClient generates deterministic fallback metrics."""
    client = AISClient(api_key="", base_url="https://api.aisstream.io/v1")
    congestion, terminal, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "neoPanamax"
    )

    assert congestion.anchorageQueueCount > 0
    assert terminal.berthTurnaroundHours > 0
    assert navigational.channelDepthM > 0


@pytest.mark.asyncio
async def test_port_directory_client_fallback_search():
    """PortDirectoryClient searches fallback reference data successfully."""
    client = PortDirectoryClient(base_url="")
    results = await client.search_ports("Singapore")
    assert len(results) >= 1
    assert results[0].locode == "SGSIN"
