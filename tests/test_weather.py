"""Unit and integration tests for Open-Meteo Weather Ingestion Client."""

import time
import uuid
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, Port, PortRiskSnapshot, VesselClass
from backend.services.weather import (
    KMH_TO_KNOTS,
    METERS_TO_NM,
    WeatherClient,
    WeatherMetrics,
    compute_weather_risk,
)
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def weather_test_db():
    """Create in-memory SQLite database seeded with vessel classes and a test port."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        await seed_vessel_classes(session)
        port = Port(
            unlocode="NLRTM",
            port_name="Port of Rotterdam",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.9244,
            longitude=4.4777,
            channel_depth_m=11.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        await session.commit()

    yield session_factory
    await engine.dispose()


# ─── 1. Unit Tests: Weather Risk Computation ────────────────────────────────────

def test_compute_weather_risk_tiers():
    """Verify compute_weather_risk accurately maps metrics to LOW, MEDIUM, and HIGH tiers."""
    # Calm conditions -> LOW
    calm = WeatherMetrics(
        windSpeedKnots=10.0,
        waveHeightM=0.8,
        swellPeriodSec=6.0,
        visibilityNm=10.0,
        gustSpeedKnots=12.0,
    )
    assert compute_weather_risk(calm) == "LOW"

    # Moderate wave (1.8m >= 1.5m) -> MEDIUM
    med_wave = WeatherMetrics(
        windSpeedKnots=12.0,
        waveHeightM=1.8,
        swellPeriodSec=7.0,
        visibilityNm=8.0,
        gustSpeedKnots=15.0,
    )
    assert compute_weather_risk(med_wave) == "MEDIUM"

    # Moderate wind (22 kts > 20 kts) -> MEDIUM
    med_wind = WeatherMetrics(
        windSpeedKnots=22.0,
        waveHeightM=1.0,
        swellPeriodSec=5.0,
        visibilityNm=6.0,
        gustSpeedKnots=25.0,
    )
    assert compute_weather_risk(med_wind) == "MEDIUM"

    # Moderate gust (29 kts > 28 kts) -> MEDIUM
    med_gust = WeatherMetrics(
        windSpeedKnots=18.0,
        waveHeightM=1.0,
        swellPeriodSec=5.0,
        visibilityNm=7.0,
        gustSpeedKnots=29.0,
    )
    assert compute_weather_risk(med_gust) == "MEDIUM"

    # High wave (3.2m > 2.5m) -> HIGH
    high_wave = WeatherMetrics(
        windSpeedKnots=15.0,
        waveHeightM=3.2,
        swellPeriodSec=10.0,
        visibilityNm=5.0,
        gustSpeedKnots=20.0,
    )
    assert compute_weather_risk(high_wave) == "HIGH"

    # Storm wind (35 kts > 30 kts) -> HIGH
    storm_wind = WeatherMetrics(
        windSpeedKnots=35.0,
        waveHeightM=2.0,
        swellPeriodSec=8.0,
        visibilityNm=4.0,
        gustSpeedKnots=42.0,
    )
    assert compute_weather_risk(storm_wind) == "HIGH"

    # Extreme gusts (45 kts > 40 kts) with moderate sustained wind -> HIGH
    high_gust = WeatherMetrics(
        windSpeedKnots=25.0,
        waveHeightM=1.2,
        swellPeriodSec=6.0,
        visibilityNm=5.0,
        gustSpeedKnots=45.0,
    )
    assert compute_weather_risk(high_gust) == "HIGH"


# ─── 2. Integration Tests: Response Parsing & Conversions ───────────────────────

@pytest.mark.asyncio
async def test_calm_weather_parsing():
    """Verify calm weather parsing, unit conversions, and resulting LOW risk level."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            return httpx.Response(
                200,
                json={
                    "latitude": 51.92,
                    "longitude": 4.48,
                    "current": {
                        "time": "2026-10-24T23:00",
                        "wave_height": 0.9,
                        "wave_period": 5.5,
                    },
                },
            )
        elif "forecast" in url:
            return httpx.Response(
                200,
                json={
                    "latitude": 51.92,
                    "longitude": 4.48,
                    "current_units": {
                        "wind_speed_10m": "km/h",
                        "wind_gusts_10m": "km/h",
                        "visibility": "m",
                    },
                    "current": {
                        "time": "2026-10-24T23:00",
                        "wind_speed_10m": 20.0,  # 20 * 0.539957 ≈ 10.8 kts
                        "wind_gusts_10m": 25.0,  # 25 * 0.539957 ≈ 13.5 kts
                        "visibility": 18520.0,   # 18520 / 1852 = 10.0 NM
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client)
        metrics = await client.get_weather(51.9244, 4.4777)

        assert metrics.waveHeightM == 0.9
        assert metrics.swellPeriodSec == 5.5
        assert metrics.windSpeedKnots == 10.8
        assert metrics.gustSpeedKnots == 13.5
        assert metrics.visibilityNm == 10.0
        assert compute_weather_risk(metrics) == "LOW"


@pytest.mark.asyncio
async def test_high_swell_parsing():
    """Verify high wave/swell conditions (Hs = 3.2m > 2.5m) and HIGH risk level."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            return httpx.Response(
                200,
                json={
                    "current": {
                        "wave_height": 3.2,
                        "wave_period": 11.0,
                    },
                },
            )
        elif "forecast" in url:
            return httpx.Response(
                200,
                json={
                    "current_units": {"wind_speed_10m": "km/h"},
                    "current": {
                        "wind_speed_10m": 15.0,
                        "wind_gusts_10m": 20.0,
                        "visibility": 15000.0,
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client)
        metrics = await client.get_weather(51.92, 4.48)

        assert metrics.waveHeightM == 3.2
        assert metrics.swellPeriodSec == 11.0
        assert compute_weather_risk(metrics) == "HIGH"


@pytest.mark.asyncio
async def test_storm_wind_conditions_parsing():
    """Verify storm winds (> 30 kts sustained or > 40 kts gusts) trigger HIGH risk."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            return httpx.Response(
                200,
                json={
                    "current": {
                        "wave_height": 2.0,
                        "wave_period": 7.0,
                    },
                },
            )
        elif "forecast" in url:
            return httpx.Response(
                200,
                json={
                    "current_units": {"wind_speed_10m": "km/h"},
                    "current": {
                        "wind_speed_10m": 60.0,  # 60 * 0.539957 ≈ 32.4 kts
                        "wind_gusts_10m": 80.0,  # 80 * 0.539957 ≈ 43.2 kts
                        "visibility": 5000.0,
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client)
        metrics = await client.get_weather(51.92, 4.48)

        assert metrics.windSpeedKnots == 32.4
        assert metrics.gustSpeedKnots == 43.2
        assert compute_weather_risk(metrics) == "HIGH"


@pytest.mark.asyncio
async def test_inland_coordinates_missing_marine_data():
    """Verify inland coordinates (400 or missing wave data) fall back to 0.0m wave height without raising."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            # Inland coordinate returns HTTP 400
            return httpx.Response(400, json={"error": True, "reason": "No marine grid cell found"})
        elif "forecast" in url:
            return httpx.Response(
                200,
                json={
                    "current_units": {"wind_speed_10m": "km/h"},
                    "current": {
                        "wind_speed_10m": 10.0,
                        "wind_gusts_10m": 12.0,
                        "visibility": 10000.0,
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client)
        # Cologne/Frankfurt inland coords
        metrics = await client.get_weather(50.9375, 6.9603)

        assert metrics.waveHeightM == 0.0
        assert metrics.swellPeriodSec == 0.0
        assert metrics.windSpeedKnots == 5.4
        assert compute_weather_risk(metrics) == "LOW"


# ─── 3. Integration Tests: In-Memory TTL Caching ───────────────────────────────

@pytest.mark.asyncio
async def test_ttl_cache_hit_and_expiry():
    """Verify in-memory cache hits avoid outbound calls, and expired entries refresh."""
    call_count = {"marine": 0, "forecast": 0}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            call_count["marine"] += 1
            return httpx.Response(200, json={"current": {"wave_height": 1.0, "wave_period": 6.0}})
        elif "forecast" in url:
            call_count["forecast"] += 1
            return httpx.Response(200, json={"current": {"wind_speed_10m": 10.0, "visibility": 10000.0}})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(ttl_seconds=1.0, http_client=http_client)

        # 1. First call: dispatches requests
        m1 = await client.get_weather(51.9244, 4.4777)
        assert call_count["marine"] == 1
        assert call_count["forecast"] == 1

        # 2. Second call with slightly different coords that round to same 2 decimals: cache hit!
        m2 = await client.get_weather(51.9211, 4.4799)
        assert call_count["marine"] == 1
        assert call_count["forecast"] == 1
        assert m2 == m1

        # 3. Wait for TTL to expire (simulate time passing in cache)
        cache_key = (round(51.9244, 2), round(4.4777, 2))
        cached_metric, _ = client._cache[cache_key]
        client._cache[cache_key] = (cached_metric, time.time() - 10.0)

        # 4. Third call after expiry: dispatches new requests
        m3 = await client.get_weather(51.9244, 4.4777)
        assert call_count["marine"] == 2
        assert call_count["forecast"] == 2


# ─── 4. Integration Tests: Resilient Error Handling ────────────────────────────

@pytest.mark.asyncio
async def test_upstream_timeout_and_error_fallback():
    """Verify network timeouts or 500 errors fall back gracefully without unhandled exceptions."""
    def mock_failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out to Open-Meteo")

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_failing_handler)) as http_client:
        client = WeatherClient(http_client=http_client)

        # Should return safe default metrics without crashing
        metrics = await client.get_weather(51.9244, 4.4777)
        assert metrics.windSpeedKnots == 0.0
        assert metrics.waveHeightM == 0.0
        assert metrics.swellPeriodSec == 0.0
        assert metrics.visibilityNm == 10.0
        assert metrics.gustSpeedKnots == 0.0


# ─── 5. Integration Tests: Database Snapshot Persistence ───────────────────────

@pytest.mark.asyncio
async def test_database_snapshot_persistence(weather_test_db):
    """Verify weather observations are persisted into port_risk_snapshots."""
    session_factory = weather_test_db

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "marine" in url:
            return httpx.Response(200, json={"current": {"wave_height": 2.8, "wave_period": 9.0}})
        elif "forecast" in url:
            return httpx.Response(
                200,
                json={
                    "current_units": {"wind_speed_10m": "km/h"},
                    "current": {"wind_speed_10m": 45.0, "visibility": 12000.0},
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client, session_factory=session_factory)

        # Call with unlocode="NLRTM"
        metrics = await client.get_weather(51.9244, 4.4777, unlocode="NLRTM")
        assert metrics.waveHeightM == 2.8
        assert compute_weather_risk(metrics) == "HIGH"

        # Check port_risk_snapshots table in database
        async with session_factory() as session:
            stmt = select(PortRiskSnapshot).where(PortRiskSnapshot.unlocode == "NLRTM")
            result = await session.execute(stmt)
            snapshot = result.scalars().first()

            assert snapshot is not None
            assert snapshot.unlocode == "NLRTM"
            assert snapshot.swell_height_m == 2.8
            assert snapshot.weather_risk_level == "HIGH"
            assert snapshot.wind_speed_kts is not None


@pytest.mark.asyncio
async def test_database_persistence_error_resilience():
    """Verify database persistence failure does not crash weather retrieval."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"current": {"wind_speed_10m": 15.0, "visibility": 10000.0}})

    # Bogus session factory that raises exception
    class FailingSessionFactory:
        def __call__(self):
            raise RuntimeError("Database connection lost")

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_handler)) as http_client:
        client = WeatherClient(http_client=http_client, session_factory=FailingSessionFactory())

        # Should still successfully return weather metrics
        metrics = await client.get_weather(51.9244, 4.4777, unlocode="NLRTM")
        assert metrics is not None
        assert isinstance(metrics, WeatherMetrics)


@pytest.mark.asyncio
async def test_get_tide_offset_success():
    """Verify live tide offset parses sea_level_height_msl correctly."""
    def mock_tide_handler(request: httpx.Request) -> httpx.Response:
        assert "sea_level_height_msl" in str(request.url)
        return httpx.Response(
            200,
            json={
                "latitude": 33.74,
                "longitude": -118.27,
                "current": {"time": "2026-10-27T02:00", "sea_level_height_msl": 0.85},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_tide_handler)) as http_client:
        client = WeatherClient(http_client=http_client)
        res = await client.get_tide_offset(33.74, -118.27)
        assert res.tide_offset_m == 0.85
        assert res.tide_data_available is True
        assert res.source == "open-meteo-marine"


@pytest.mark.asyncio
async def test_get_tide_offset_caching():
    """Verify in-memory TTL caching prevents redundant HTTP calls for tide offset."""
    call_count = 0

    def mock_tide_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "current": {"sea_level_height_msl": 0.42},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_tide_handler)) as http_client:
        client = WeatherClient(http_client=http_client, ttl_seconds=60.0)
        res1 = await client.get_tide_offset(51.92, 4.48)
        res2 = await client.get_tide_offset(51.92, 4.48)
        assert res1.tide_offset_m == 0.42
        assert res2.tide_offset_m == 0.42
        assert call_count == 1

