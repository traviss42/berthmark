import httpx
import pytest
from app.clients.ais_client import AISClient
from app.db import get_db_context
from app.db.models import ExternalAISTrafficCache, ExternalWeatherCache, MonitoredPort
from app.services.ingestion import (
    get_ingestion_scheduler,
    is_ingestion_running,
    run_ingestion_cycle,
    start_ingestion_scheduler,
    stop_ingestion_scheduler,
)
from app.services.external_client import get_marine_weather, get_port_traffic_metrics


@pytest.fixture(autouse=True)
def mock_external_network_apis(monkeypatch):
    """Mock external HTTP and WebSocket requests to test DB caching logic fast and deterministically."""
    mock_weather = {
        "current": {
            "wave_height": 2.2,
            "swell_wave_period": 7.4,
            "visibility": 18520.0,
        },
        "hourly": {
            "wind_speed_10m": [22.0],
            "wind_gusts_10m": [28.0],
        },
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return mock_weather

    async def mock_get(self, url, **kwargs):
        return MockResponse()

    async def mock_ws(*args, **kwargs):
        return (18, 7, 11)  # 18 active, 7 anchored/stationary, 11 underway

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    monkeypatch.setattr(AISClient, "_query_aisstream_ws", mock_ws)


@pytest.mark.asyncio
async def test_run_ingestion_cycle_persists_data_into_sqlite():
    """Verify run_ingestion_cycle updates SQLite weather and AIS traffic tables."""
    # Seed a user-monitored port that exists in UN/LOCODE + NGA WPI
    with get_db_context() as db:
        port = MonitoredPort(
            id="port-custom-ingest-1",
            user_id="analyst@maritime.com",
            name="Port of Oakland",
            locode="USOAK",
            country="United States",
            lat=37.795,
            lon=-122.28,
            is_default=False,
            geofence_radius_nm=8.0,
            notifications_enabled=True,
        )
        db.add(port)
        db.commit()

    # Execute ingestion cycle
    result = await run_ingestion_cycle()

    assert result["status"] == "success"
    assert result["ports_processed"] >= 1
    assert result["weather_records_updated"] >= 1
    assert result["ais_records_updated"] >= 1

    # Verify weather record was stored in SQLite
    with get_db_context() as db:
        weather_records = db.query(ExternalWeatherCache).all()
        assert len(weather_records) >= 1
        for rec in weather_records:
            assert rec.is_fresh(1800.0) is True
            assert rec.wind_speed_knots > 0

        # Verify AIS records were stored in SQLite
        ais_records = db.query(ExternalAISTrafficCache).all()
        assert len(ais_records) >= 1
        for rec in ais_records:
            assert rec.is_fresh(1800.0) is True
            assert rec.anchorage_queue_count >= 0


@pytest.mark.asyncio
async def test_ingestion_scheduler_lifecycle():
    """Verify start_ingestion_scheduler starts scheduler and stop_ingestion_scheduler shuts it down."""
    scheduler = start_ingestion_scheduler(interval_minutes=30)
    assert scheduler is not None
    assert is_ingestion_running() is True
    assert scheduler.get_job("external_api_ingestion_job") is not None

    # Clean shutdown
    stop_ingestion_scheduler()
    assert is_ingestion_running() is False


@pytest.mark.asyncio
async def test_service_client_functions_use_sqlite_caching():
    """Verify external_client functions read and write to SQLite cache."""
    # 1. Fetch weather via service
    weather = await get_marine_weather(lat=24.98, lon=55.02, port_id="port-jebel-ali")
    assert weather.windSpeedKnots > 0

    # Verify cached in SQLite
    with get_db_context() as db:
        rec = db.query(ExternalWeatherCache).filter(ExternalWeatherCache.port_id == "port-jebel-ali").first()
        assert rec is not None
        assert rec.is_fresh(1800.0) is True

    # 2. Fetch AIS traffic + WPI navigational metrics via service
    cong, nav = await get_port_traffic_metrics(
        port_id="port-jebel-ali",
        locode="AEJEA",
        vessel_class="neoPanamax",
        lat=24.98,
        lon=55.02,
    )
    assert cong.anchorageQueueCount >= 0
    assert nav.channelDepthM == 12.5

    # Verify cached in SQLite
    with get_db_context() as db:
        rec = db.query(ExternalAISTrafficCache).filter(ExternalAISTrafficCache.port_id == "port-jebel-ali").first()
        assert rec is not None
        assert rec.is_fresh(1800.0) is True

