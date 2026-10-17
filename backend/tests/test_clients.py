"""Tests for external API clients, mocking HTTP requests and verifying real data parsing and SQLite caching."""

import httpx
import pytest
from app.clients.ais_client import AISClient
from app.clients.ports_client import PortDirectoryClient
from app.clients.weather_client import MarineWeatherClient


@pytest.mark.asyncio
async def test_weather_client_with_successful_mock_response(monkeypatch):
    """When weather API returns 200, client parses real wave_height, swell_wave_period, visibility, and wind."""
    mock_payload = {
        "current": {
            "wave_height": 2.8,
            "swell_wave_period": 8.4,
            "visibility": 14816.0,  # 8.0 Nm
        },
        "hourly": {
            "wind_speed_10m": [32.5, 30.1],
            "wind_gusts_10m": [42.0, 39.5],
        },
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return mock_payload

    async def mock_get(self, url, params=None, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    result = await client.get_marine_weather(lat=51.9, lon=4.4, port_id="port-rotterdam")

    assert result.waveHeightM == 2.8
    assert result.swellPeriodSec == 8.4
    assert result.visibilityNm == 8.0
    assert result.windSpeedKnots == 32.5
    assert result.gustSpeedKnots == 42.0


@pytest.mark.asyncio
async def test_weather_client_raises_on_network_error_without_fallback(monkeypatch):
    """When weather API throws network error and no cache exists, client raises rather than fabricating data."""
    async def mock_get_error(self, url, **kwargs):
        raise httpx.ConnectError("Network unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_error)

    client = MarineWeatherClient(base_url="https://mock-weather.example.com")
    with pytest.raises(httpx.ConnectError):
        await client.get_marine_weather(lat=51.9, lon=4.4, port_id="port-rotterdam")


@pytest.mark.asyncio
async def test_ais_client_with_mock_response(monkeypatch):
    """When AIS API returns 200, client parses congestion and navigational metrics."""
    mock_payload = {
        "congestion": {
            "anchorageQueueCount": 15,
            "activeVesselCount": 42,
            "movingVesselCount": 27,
            "rolling30dAvgQueue": 12.0,
        },
        "navigational": {
            "underKeelClearanceM": 2.5,
            "channelDepthM": 16.0,
            "cargoPierDepthM": 16.5,
            "anchorageDepthM": 18.0,
            "vesselDraftM": 12.5,
            "overheadLimits": "No",
            "pilotageAvailable": True,
            "tugsAssistance": True,
            "tideHeightM": 1.5,
            "harborSize": "Large",
            "shelterAfforded": "Good",
        },
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return mock_payload

    async def mock_get(self, url, **kwargs):
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = AISClient(api_key="test-api-key", base_url="https://mock-ais.example.com")
    congestion, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "panamax"
    )

    assert congestion.anchorageQueueCount == 15
    assert congestion.activeVesselCount == 42
    assert navigational.channelDepthM == 16.0


@pytest.mark.asyncio
async def test_ais_client_uses_real_wpi_navigational_data():
    """AISClient populates real NGA World Port Index depth and hydrographic metrics for matched ports."""
    client = AISClient(api_key="", base_url="https://api.aisstream.io/v1")
    congestion, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "neoPanamax"
    )

    assert congestion.anchorageQueueCount >= 0
    assert navigational.channelDepthM == 11.0
    assert navigational.anchorageDepthM == 11.0
    assert navigational.cargoPierDepthM == 6.4
    assert navigational.vesselDraftM == 15.2
    assert navigational.underKeelClearanceM == -4.2
    assert navigational.overheadLimits == "Yes"
    assert navigational.pilotageAvailable is True


@pytest.mark.asyncio
async def test_port_directory_client_search():
    """PortDirectoryClient searches the combined UN/LOCODE + NGA World Port Index database."""
    client = PortDirectoryClient(base_url="")
    results = await client.search_ports("Singapore")
    assert len(results) >= 1
    assert any(r.locode == "SGKEP" for r in results)
    kep = next(r for r in results if r.locode == "SGKEP")
    assert kep.channelDepthM == 12.5


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
        "current": {"wave_height": 2.9, "swell_wave_period": 7.8, "visibility": 18520.0},
        "hourly": {
            "wind_speed_10m": [28.0],
            "wind_gusts_10m": [36.0],
        },
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

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
            active_vessel_count=45,
            moving_vessel_count=26,
            rolling_30d_avg_queue=14.0,
            under_keel_clearance_m=2.0,
            channel_depth_m=16.5,
            cargo_pier_depth_m=17.0,
            anchorage_depth_m=18.0,
            vessel_draft_m=15.2,
            overhead_limits="Yes",
            pilotage_available=True,
            tugs_assistance=True,
            tide_height_m=1.5,
            harbor_size="Large",
            shelter_afforded="Good",
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
    congestion, navigational = await client.get_port_traffic_metrics(
        "port-rotterdam", "NLRTM", "neoPanamax"
    )

    assert congestion.anchorageQueueCount == 19
    assert congestion.activeVesselCount == 45
    assert navigational.channelDepthM == 16.5


@pytest.mark.asyncio
async def test_ais_client_calculate_bounding_box():
    """Verify calculate_bounding_box creates valid AISStream-compatible coordinates."""
    bbox = AISClient.calculate_bounding_box(lat=51.92, lon=4.48, radius_nm=8.0)
    assert len(bbox) == 2
    sw, ne = bbox[0], bbox[1]
    assert sw[0] < ne[0]  # min_lat < max_lat
    assert sw[1] < ne[1]  # min_lon < max_lon
    assert sw[0] < 51.92 < ne[0]
    assert sw[1] < 4.48 < ne[1]


@pytest.mark.asyncio
async def test_ais_client_query_multiple_bounding_boxes_ws(monkeypatch):
    """Verify _query_multiple_bounding_boxes_ws subscribes with multiple boxes and routes vessels correctly."""
    import asyncio
    import json
    import websockets

    sent_subscriptions = []

    mock_messages = [
        # Subscription confirmation (should be skipped)
        json.dumps({"MessageType": "SubscriptionConfirmation"}),
        # Vessel 1 in Rotterdam (stationary: Sog=0.1)
        json.dumps({
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 111111111,
                "latitude": 51.92,
                "longitude": 4.48,
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 51.92,
                    "Longitude": 4.48,
                    "Sog": 0.1,
                    "NavigationalStatus": 1,
                }
            },
        }),
        # Vessel 2 in Rotterdam (moving: Sog=12.5)
        json.dumps({
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 222222222,
                "latitude": 51.91,
                "longitude": 4.49,
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 51.91,
                    "Longitude": 4.49,
                    "Sog": 12.5,
                    "NavigationalStatus": 0,
                }
            },
        }),
        # Vessel 3 in Keppel / Singapore (moving: Sog=15.0)
        json.dumps({
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI": 333333333,
                "latitude": 1.266,
                "longitude": 103.833,
            },
            "Message": {
                "PositionReport": {
                    "Latitude": 1.266,
                    "Longitude": 103.833,
                    "Sog": 15.0,
                    "NavigationalStatus": 0,
                }
            },
        }),
    ]

    class MockWebSocket:
        def __init__(self):
            self.msg_queue = list(mock_messages)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, data):
            sent_subscriptions.append(json.loads(data))

        async def recv(self):
            if self.msg_queue:
                return self.msg_queue.pop(0)
            raise asyncio.TimeoutError()

    def mock_connect(*args, **kwargs):
        return MockWebSocket()

    monkeypatch.setattr(websockets, "connect", mock_connect)

    client = AISClient(api_key="mock-api-key")
    boxes = {
        "port-nlrtm": {"lat": 51.9167, "lon": 4.4, "radius_nm": 8.0},
        "port-sgkep": {"lat": 1.2667, "lon": 103.8333, "radius_nm": 8.0},
    }

    results = await client._query_multiple_bounding_boxes_ws(boxes, sample_seconds=0.5)

    # 1. Verify a single WebSocket subscription was sent with both bounding boxes
    assert len(sent_subscriptions) == 1
    sub = sent_subscriptions[0]
    assert sub["APIKey"] == "mock-api-key"
    assert len(sub["BoundingBoxes"]) == 2
    assert "FilterMessageTypes" in sub

    # 2. Verify results per port:
    # Rotterdam has 2 vessels: 1 stationary, 1 moving
    assert "port-nlrtm" in results
    rtm_active, rtm_stationary, rtm_moving = results["port-nlrtm"]
    assert rtm_active == 2
    assert rtm_stationary == 1
    assert rtm_moving == 1

    # Keppel has 1 vessel: 0 stationary, 1 moving
    assert "port-sgkep" in results
    kep_active, kep_stationary, kep_moving = results["port-sgkep"]
    assert kep_active == 1
    assert kep_stationary == 0
    assert kep_moving == 1

    # 3. Verify in-memory coordinate cache is primed for both ports
    coord_rtm = (round(51.9167, 2), round(4.4, 2))
    coord_kep = (round(1.2667, 2), round(103.8333, 2))
    assert coord_rtm in client._live_vessel_cache
    assert coord_kep in client._live_vessel_cache


@pytest.mark.asyncio
async def test_batch_query_ports_ws_with_aliasing(monkeypatch):
    """Verify batch_query_ports_ws resolves ports and provides both port_id and locode keys."""
    client = AISClient(api_key="mock-key")

    async def mock_multi_ws(boxes_by_port, sample_seconds=2.0):
        return {
            "port-nlrtm": (25, 10, 15),
            "port-sgkep": (30, 8, 22),
        }

    monkeypatch.setattr(client, "_query_multiple_bounding_boxes_ws", mock_multi_ws)

    ports = [
        {"id": "port-nlrtm", "locode": "NLRTM", "lat": 51.9167, "lon": 4.4},
        {"id": "port-sgkep", "locode": "SGKEP", "lat": 1.2667, "lon": 103.8333},
    ]

    res = await client.batch_query_ports_ws(ports)
    # Available by id
    assert res["port-nlrtm"] == (25, 10, 15)
    assert res["port-sgkep"] == (30, 8, 22)
    # Available by locode alias
    assert res["NLRTM"] == (25, 10, 15)
    assert res["SGKEP"] == (30, 8, 22)


@pytest.mark.asyncio
async def test_query_aisstream_ws_single_wrapper(monkeypatch):
    """Verify _query_aisstream_ws wraps _query_multiple_bounding_boxes_ws for backward compatibility."""
    client = AISClient(api_key="mock-key")

    async def mock_multi_ws(boxes_by_port, sample_seconds=1.5):
        assert "default" in boxes_by_port
        return {"default": (12, 4, 8)}

    monkeypatch.setattr(client, "_query_multiple_bounding_boxes_ws", mock_multi_ws)

    counts = await client._query_aisstream_ws(lat=51.92, lon=4.48, radius_nm=8.0)
    assert counts == (12, 4, 8)


