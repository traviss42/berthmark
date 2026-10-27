"""Integration and unit tests for Historical Risk Trend Time-Series API (Issue 16)."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import get_db_session
from backend.main import app
from backend.models import Base, Port, PortRiskSnapshot
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def history_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy, test port, and time-series snapshots."""
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

        # Seed benchmark port
        port = Port(
            unlocode="NLRTM",
            port_name="Port of Rotterdam",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.9244,
            longitude=4.4777,
            channel_depth_m=16.5,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        empty_port = Port(
            unlocode="EMPTY",
            port_name="Empty History Port",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=52.0,
            longitude=4.5,
            channel_depth_m=15.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add_all([port, empty_port])
        await session.commit()

        # Seed 50 historical snapshots for NLRTM at 6-hour intervals spanning the past 12 days
        now = datetime.now(timezone.utc)
        snapshots = []
        for i in range(50):
            eval_time = now - timedelta(hours=6 * (50 - i))
            tier = "LOW" if i < 15 else ("MEDIUM" if i < 35 else "HIGH")
            snapshots.append(
                PortRiskSnapshot(
                    snapshot_id=uuid.uuid4(),
                    unlocode="NLRTM",
                    vessel_class_id="neoPanamax",
                    grounding_risk_level="LOW",
                    anchored_vessel_count=5 + (i % 12),
                    underway_vessel_count=2,
                    total_active_geofence_count=7 + (i % 12),
                    historical_avg_queue=8.0,
                    queue_variance_pct=float((i % 12) * 5),
                    congestion_risk_level=tier,
                    weather_risk_level="LOW",
                    overall_risk_level=tier,
                    swell_height_m=1.0,
                    wind_speed_kts=12.0,
                    updated_at=eval_time,
                )
            )
        session.add_all(snapshots)
        await session.commit()

    yield engine, session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_risk_history_success_and_schema(history_test_db):
    """Verify GET /api/v1/ports/{portId}/risk/history returns chronologically ascending RiskAssessment items."""
    engine, session_factory = history_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=7")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert len(data) <= 40

        # Check ascending chronological order: oldest first, newest last
        timestamps = [item["timestamp"] for item in data]
        assert timestamps == sorted(timestamps)

        # Validate RiskAssessment schema structure
        for item in data:
            assert "id" in item
            assert item["portId"] == "port-rotterdam"
            assert item["portName"] == "Port of Rotterdam"
            assert item["vesselClass"] == "neoPanamax"
            assert item["vesselClassLabel"] == "Neo-Panamax"
            assert "timestamp" in item
            assert item["compositeTier"] in ["low", "medium", "high"]
            assert isinstance(item["compositeScore"], (int, float))

            sub = item["subRisks"]
            assert "terminalDelays" not in sub
            assert "congestion" in sub
            assert "weather" in sub
            assert "navigational" in sub

            m = item["metrics"]
            assert "congestion" in m
            assert "weather" in m
            assert "navigational" in m

        # Check root prefix /ports/{portId}/risk/history
        res_root = await client.get("/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=7")
        assert res_root.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_risk_history_capping_at_40_points(history_test_db):
    """Verify strict 40-point capping when queried range has >40 snapshots."""
    engine, session_factory = history_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Request 14 days (all 50 seeded snapshots fall within 14 days)
        res = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=14")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 40  # Strictly capped at 40 points

        # Chronological order verified
        timestamps = [item["timestamp"] for item in data]
        assert timestamps == sorted(timestamps)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_risk_history_default_days_and_empty_port(history_test_db):
    """Verify default days=7 and empty list on port with no snapshots."""
    engine, session_factory = history_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Default days=7 when parameter is omitted
        res_default = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax")
        assert res_default.status_code == 200
        data_default = res_default.json()
        assert isinstance(data_default, list)
        assert len(data_default) > 0

        # Port with no history returns empty array []
        res_empty = await client.get("/api/v1/ports/EMPTY/risk/history?vesselClass=neoPanamax")
        assert res_empty.status_code == 200
        assert res_empty.json() == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_risk_history_validations_and_404(history_test_db):
    """Verify 400 Bad Request on invalid/missing params and 404 on nonexistent port."""
    engine, session_factory = history_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Missing vesselClass -> 400
        res_missing_vc = await client.get("/api/v1/ports/port-rotterdam/risk/history")
        assert res_missing_vc.status_code == 400
        assert res_missing_vc.json()["statusCode"] == 400

        # 2. Invalid vesselClass -> 400
        res_bad_vc = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=submarine")
        assert res_bad_vc.status_code == 400
        assert "submarine" in res_bad_vc.json()["message"]

        # 3. days < 1 -> 400
        res_zero_days = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=0")
        assert res_zero_days.status_code == 400
        assert res_zero_days.json()["statusCode"] == 400

        res_neg_days = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=-5")
        assert res_neg_days.status_code == 400
        assert res_neg_days.json()["statusCode"] == 400

        # 4. days > 30 -> 400
        res_high_days = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=31")
        assert res_high_days.status_code == 400
        assert res_high_days.json()["statusCode"] == 400

        # 5. non-integer days -> 400
        res_str_days = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=abc")
        assert res_str_days.status_code == 400
        assert res_str_days.json()["statusCode"] == 400

        res_float_days = await client.get("/api/v1/ports/port-rotterdam/risk/history?vesselClass=neoPanamax&days=7.5")
        assert res_float_days.status_code == 400
        assert res_float_days.json()["statusCode"] == 400

        # 6. Nonexistent port -> 404
        res_404 = await client.get("/api/v1/ports/nonexistent-port/risk/history?vesselClass=neoPanamax")
        assert res_404.status_code == 404
        err_404 = res_404.json()
        assert err_404["error"] == "Not Found"
        assert "nonexistent-port" in err_404["message"]
        assert err_404["statusCode"] == 404

    app.dependency_overrides.clear()
