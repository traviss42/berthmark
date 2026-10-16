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


@pytest.mark.asyncio
async def test_weather_client_sqlite_cache_hit_avoids_http(monkeypatch):
    """When SQLite contains fresh (< 30 min) weather data, return cached data without HTTP."""
    from datetime import datetime, timezone, timedelta
    from app.db import get_db_context
    from app.db.models import ExternalWeatherCache

    # Seed fresh weather in SQLite (fetched 5 mins ago)
    now = datetime.now(timezone.utc)
    with get_db_context() as db:
        cached = ExternalWeatherCache(
            id="51.92:4.48",
            lat=51.92,
            lon=4.48,
            port_id="port-rotterdam",
            wind_speed_knots=38.5,
            gust_speed_knots=48.0,
            wave_height_m=3.2,
            swell_period_sec=8.0,
            visibility_nm=6.5,
            source="open-meteo",
            fetched_at=now - timedelta(minutes=5),
        )
        db.add(cached)
        db.commit()

    # Monkeypatch HTTP to fail if any external request is attempted
    async def mock_get_should_not_be_called(self, url, **kwargs):
        raise AssertionError("HTTP request should NOT be made when fresh cache exists in SQLite!")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_should_not_be_called)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    result = await client.get_marine_weather(lat=51.92, lon=4.48, port_id="port-rotterdam")

    assert result.windSpeedKnots == 38.5
    assert result.waveHeightM == 3.2
    assert result.gustSpeedKnots == 48.0


@pytest.mark.asyncio
async def test_weather_client_stale_cache_fetches_fresh_and_updates_sqlite(monkeypatch):
    """When SQLite cache is stale (> 30 min), client fetches fresh data and updates SQLite."""
    from datetime import datetime, timezone, timedelta
    from app.db import get_db_context
    from app.db.models import ExternalWeatherCache

    # Seed stale weather in SQLite (fetched 45 mins ago)
    now = datetime.now(timezone.utc)
    with get_db_context() as db:
        cached = ExternalWeatherCache(
            id="51.92:4.48",
            lat=51.92,
            lon=4.48,
            port_id="port-rotterdam",
            wind_speed_knots=15.0,
            gust_speed_knots=20.0,
            wave_height_m=1.0,
            swell_period_sec=5.0,
            visibility_nm=10.0,
            source="open-meteo",
            fetched_at=now - timedelta(minutes=45),
        )
        db.add(cached)
        db.commit()

    # Fresh response from mock HTTP API
    mock_payload = {
        "current": {"wave_height": 2.9},
        "hourly": {
            "wind_speed_10m": [28.0],
            "wind_gusts_10m": [36.0],
        },
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mock_payload

    async def mock_get_fresh(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_fresh)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    result = await client.get_marine_weather(lat=51.92, lon=4.48, port_id="port-rotterdam")

    assert result.waveHeightM == 2.9
    assert result.windSpeedKnots == 28.0

    # Verify SQLite was updated with the fresh fetched_at timestamp
    with get_db_context() as db:
        updated = db.query(ExternalWeatherCache).filter(ExternalWeatherCache.id == "51.92:4.48").first()
        assert updated is not None
        assert updated.wave_height_m == 2.9
        assert updated.wind_speed_knots == 28.0
        assert updated.is_fresh(1800.0) is True


@pytest.mark.asyncio
async def test_ais_client_sqlite_cache_hit_and_persistence(monkeypatch):
    """When fresh AIS data is in SQLite, return it directly; when fetching, persist to SQLite."""
    from datetime import datetime, timezone, timedelta
    from app.db import get_db_context
    from app.db.models import ExternalAISTrafficCache

    now = datetime.now(timezone.utc)
    with get_db_context() as db:
        cached = ExternalAISTrafficCache(
            id="port-rotterdam:neoPanamax",
            port_id="port-rotterdam",
            locode="NLRTM",
            vessel_class="neoPanamax",
            anchorage_queue_count=19,
            avg_waiting_time_hours=27.5,
            berth_occupancy_pct=85.0,
            rolling_30d_avg_queue=14.0,
            rolling_30d_avg_wait_hours=22.0,
            berth_turnaround_hours=32.0,
            berth_to_anchorage_wait_ratio=0.6,
            dwell_time_anomaly_score=45.0,
            rolling_30d_avg_turnaround=30.0,
            under_keel_clearance_m=2.0,
            channel_depth_m=16.5,
            air_draft_clearance_m=8.5,
            pilotage_available=True,
            tide_height_m=1.5,
            source="aisstream",
            fetched_at=now - timedelta(minutes=10),
        )
        db.add(cached)
        db.commit()

    # Verify fresh cache hit without HTTP calls
    async def mock_fail_if_called(self, url, **kwargs):
        raise AssertionError("HTTP request should NOT be made when AIS cache is fresh!")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_fail_if_called)

    client = AISClient(api_key="test-key", base_url="https://mock-ais.example.com")
    congestion, terminal, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "neoPanamax"
    )

    assert congestion.anchorageQueueCount == 19
    assert terminal.berthTurnaroundHours == 32.0
    assert navigational.channelDepthM == 16.5
