"""Integration tests for Single Port Risk Assessment Endpoint."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import get_db_session
from backend.main import app
from backend.models import Base, Port, PortRiskSnapshot
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def risk_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy and sample ports."""
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

        # Seed benchmark ports
        ports = [
            Port(
                unlocode="NLRTM",
                port_name="Port of Rotterdam",
                country_code="NL",
                subdivision_code="NL-ZH",
                latitude=51.9244,
                longitude=4.4777,
                channel_depth_m=16.5,
                cargo_pier_depth_m=15.0,
                anchorage_depth_m=18.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="SGSIN",
                port_name="Port of Singapore",
                country_code="SG",
                subdivision_code="SG",
                latitude=1.2648,
                longitude=103.8408,
                channel_depth_m=16.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
        ]
        session.add_all(ports)
        await session.commit()

    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_port_risk_success_and_schema_validation(risk_test_db):
    """Verify GET /api/v1/ports/{portId}/risk returns 200 with schema-compliant payload."""
    async def override_get_db():
        async with risk_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Test canonical benchmark ID /api/v1/ports/port-rotterdam/risk?vesselClass=neoPanamax
        res = await client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=neoPanamax")
        assert res.status_code == 200
        data = res.json()

        # Required fields in RiskAssessment
        assert "id" in data
        assert data["id"].startswith("risk-port-rotterdam-neoPanamax-")
        assert data["portId"] == "port-rotterdam"
        assert data["portName"] == "Port of Rotterdam"
        assert data["vesselClass"] == "neoPanamax"
        assert data["vesselClassLabel"] == "Neo-Panamax"
        assert "timestamp" in data
        assert data["compositeTier"] in ["low", "medium", "high"]
        assert isinstance(data["compositeScore"], (int, float))
        assert 0.0 <= data["compositeScore"] <= 100.0

        # Sub-risks validation
        sub = data["subRisks"]
        assert "terminalDelays" not in sub
        for cat in ["congestion", "weather", "navigational"]:
            assert cat in sub
            sr = sub[cat]
            assert sr["category"] == cat
            assert sr["tier"] in ["low", "medium", "high"]
            assert isinstance(sr["score"], (int, float))
            assert isinstance(sr["detail"], str) and len(sr["detail"]) > 0
            assert isinstance(sr["factors"], list)

        # PortMetrics validation
        m = data["metrics"]
        assert m["portId"] == "port-rotterdam"
        assert "timestamp" in m
        assert "congestion" in m
        assert "weather" in m
        assert "navigational" in m

        # 2. Test root prefix route /ports/{portId}/risk
        res_root = await client.get("/ports/port-rotterdam/risk?vesselClass=neoPanamax")
        assert res_root.status_code == 200

    # 3. Verify snapshot persistence in database
    async with risk_test_db() as session:
        stmt = (
            select(PortRiskSnapshot)
            .where(
                PortRiskSnapshot.unlocode == "NLRTM",
                PortRiskSnapshot.vessel_class_id == "neoPanamax",
            )
            .order_by(PortRiskSnapshot.updated_at.desc())
            .limit(1)
        )
        snap_res = await session.execute(stmt)
        snapshot = snap_res.scalar_one_or_none()
        assert snapshot is not None
        assert snapshot.overall_risk_level in ["LOW", "MEDIUM", "HIGH"]
        assert snapshot.vessel_class_id == "neoPanamax"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_port_name_query_override(risk_test_db):
    """Verify optional portName query parameter override."""
    async def override_get_db():
        async with risk_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/api/v1/ports/port-rotterdam/risk?vesselClass=panamax&portName=Europort%20Terminal"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["portName"] == "Europort Terminal"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_case_insensitive_locode_lookup(risk_test_db):
    """Verify case-insensitive UN/LOCODE path parameter lookup."""
    async def override_get_db():
        async with risk_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Lowercase UN/LOCODE
        res_lower = await client.get("/api/v1/ports/nlrtm/risk?vesselClass=feeder")
        assert res_lower.status_code == 200

        # Uppercase UN/LOCODE
        res_upper = await client.get("/api/v1/ports/NLRTM/risk?vesselClass=feeder")
        assert res_upper.status_code == 200

        # Singapore lowercase
        res_sg = await client.get("/api/v1/ports/sgsin/risk?vesselClass=vlcc")
        assert res_sg.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_validation_errors_and_404(risk_test_db):
    """Verify 400 Bad Request on missing/invalid vesselClass and 404 on nonexistent port."""
    async def override_get_db():
        async with risk_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Missing vesselClass query parameter -> 400
        res_missing = await client.get("/api/v1/ports/port-rotterdam/risk")
        assert res_missing.status_code == 400
        err_missing = res_missing.json()
        assert err_missing["error"] == "Bad Request"
        assert err_missing["statusCode"] == 400

        # Invalid vesselClass -> 400
        res_invalid = await client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=submarine")
        assert res_invalid.status_code == 400
        err_invalid = res_invalid.json()
        assert err_invalid["error"] == "Bad Request"
        assert "submarine" in err_invalid["message"]
        assert err_invalid["statusCode"] == 400

        # Non-existent port -> 404
        res_notfound = await client.get("/api/v1/ports/nonexistent-port/risk?vesselClass=neoPanamax")
        assert res_notfound.status_code == 404
        err_notfound = res_notfound.json()
        assert err_notfound["error"] == "Not Found"
        assert "nonexistent-port" in err_notfound["message"]
        assert err_notfound["statusCode"] == 404

    app.dependency_overrides.clear()
