"""Integration and performance tests for Bulk Risk Assessment Endpoint (Issue 15)."""

import time
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import get_db_session
from backend.main import app
from backend.models import Base, Port
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def bulk_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy and 25 test ports."""
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
            Port(
                unlocode="USHOU",
                port_name="Port of Houston",
                country_code="US",
                subdivision_code="US-TX",
                latitude=29.75,
                longitude=-95.28,
                channel_depth_m=14.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
        ]

        # Seed 22 additional test ports for scale testing (total > 20)
        for i in range(1, 23):
            code = f"ZZ{i:03d}"
            ports.append(
                Port(
                    unlocode=code,
                    port_name=f"Bulk Test Port {i:02d}",
                    country_code="ZZ",
                    subdivision_code="ZZ-01",
                    latitude=10.0 + i * 0.5,
                    longitude=20.0 + i * 0.5,
                    channel_depth_m=12.0 + (i % 5),
                    is_depth_available=True,
                    reconciliation_method="EXACT_UNLOCODE",
                )
            )

        session.add_all(ports)
        await session.commit()

    yield engine, session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_bulk_risk_assessment_success_and_schema(bulk_test_db):
    """Verify POST /api/v1/risk/assessments/bulk returns 200 with schema-compliant RiskAssessment array."""
    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    payload = {
        "ports": [
            {"id": "port-rotterdam", "name": "Port of Rotterdam"},
            {"id": "port-singapore", "name": "Port of Singapore"},
            {"id": "port-houston", "name": "Port of Houston"},
        ],
        "vesselClass": "neoPanamax",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Test /api/v1 prefix
        res = await client.post("/api/v1/risk/assessments/bulk", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 3

        for item in data:
            assert "id" in item
            assert item["portId"] in ["port-rotterdam", "port-singapore", "port-houston"]
            assert item["vesselClass"] == "neoPanamax"
            assert item["vesselClassLabel"] == "Neo-Panamax"
            assert "timestamp" in item
            assert item["compositeTier"] in ["low", "medium", "high"]
            assert isinstance(item["compositeScore"], (int, float))
            assert 0.0 <= item["compositeScore"] <= 100.0

            sub = item["subRisks"]
            for category in ["congestion", "terminalDelays", "weather", "navigational"]:
                assert category in sub
                assert sub[category]["category"] == category
                assert sub[category]["tier"] in ["low", "medium", "high"]
                assert isinstance(sub[category]["score"], (int, float))
                assert isinstance(sub[category]["detail"], str)
                assert isinstance(sub[category]["factors"], list)

            metrics = item["metrics"]
            assert "congestion" in metrics
            assert "terminal" in metrics
            assert "weather" in metrics
            assert "navigational" in metrics

        # Test root prefix /risk/assessments/bulk
        res_root = await client.post("/risk/assessments/bulk", json=payload)
        assert res_root.status_code == 200
        assert len(res_root.json()) == 3

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_risk_deduplication(bulk_test_db):
    """Verify duplicate port IDs in the ports array are deduplicated."""
    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    payload = {
        "ports": [
            {"id": "port-rotterdam", "name": "Port of Rotterdam"},
            {"id": "port-rotterdam"},
            {"id": "NLRTM"},  # Same UN/LOCODE
            {"id": "port-singapore"},
        ],
        "vesselClass": "panamax",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/v1/risk/assessments/bulk", json=payload)
        assert res.status_code == 200
        data = res.json()
        # Should be deduplicated to 2 unique ports
        assert len(data) == 2
        port_ids = [item["portId"] for item in data]
        assert "port-rotterdam" in port_ids
        assert "port-singapore" in port_ids

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_risk_unresolvable_ports_omitted(bulk_test_db):
    """Verify non-existent ports are omitted without raising 500 errors."""
    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    # Mix of valid and invalid
    payload_mixed = {
        "ports": [
            {"id": "port-rotterdam"},
            {"id": "ghost-port-999"},
            {"id": "fake-harbor"},
        ],
        "vesselClass": "feeder",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/v1/risk/assessments/bulk", json=payload_mixed)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["portId"] == "port-rotterdam"

        # None exist -> empty array []
        payload_all_fake = {
            "ports": [
                {"id": "ghost-1"},
                {"id": "ghost-2"},
            ],
            "vesselClass": "feeder",
        }
        res_empty = await client.post("/api/v1/risk/assessments/bulk", json=payload_all_fake)
        assert res_empty.status_code == 200
        assert res_empty.json() == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_risk_validation_errors(bulk_test_db):
    """Verify HTTP 400 Bad Request on empty ports, missing fields, or invalid vesselClass."""
    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Empty ports array
        res = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": [], "vesselClass": "neoPanamax"},
        )
        assert res.status_code == 400
        err = res.json()
        assert err["error"] == "Bad Request"
        assert err["statusCode"] == 400

        # 2. Missing ports field
        res = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"vesselClass": "neoPanamax"},
        )
        assert res.status_code == 400
        assert res.json()["statusCode"] == 400

        # 3. Missing vesselClass field
        res = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": [{"id": "port-rotterdam"}]},
        )
        assert res.status_code == 400
        assert res.json()["statusCode"] == 400

        # 4. Invalid vesselClass value (e.g. spaceship)
        res = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": [{"id": "port-rotterdam"}], "vesselClass": "spaceship"},
        )
        assert res.status_code == 400
        assert "spaceship" in res.json()["message"]

        # 5. Malformed port item (missing id or empty id)
        res = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": [{"name": "Only Name"}], "vesselClass": "neoPanamax"},
        )
        assert res.status_code == 400

        res_empty_id = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": [{"id": "   "}], "vesselClass": "neoPanamax"},
        )
        assert res_empty_id.status_code == 400

        # 6. Malformed non-JSON Content-Type or invalid syntax
        res_text = await client.post(
            "/api/v1/risk/assessments/bulk",
            content="not a json",
            headers={"Content-Type": "application/json"},
        )
        assert res_text.status_code == 400

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_risk_o1_query_complexity_and_sub_500ms_performance(bulk_test_db):
    """Verify O(1) database query count scalability and sub-500ms latency on 20 ports."""
    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    # Prepare batch of 2 ports
    batch_2 = [
        {"id": "port-rotterdam"},
        {"id": "port-singapore"},
    ]

    # Prepare batch of 20 ports
    batch_20 = [
        {"id": "port-rotterdam"},
        {"id": "port-singapore"},
        {"id": "port-houston"},
    ] + [{"id": f"ZZ{i:03d}"} for i in range(1, 18)]

    assert len(batch_20) == 20

    query_counts = {"count": 0}

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        query_counts["count"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Query 2 ports
        query_counts["count"] = 0
        res2 = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": batch_2, "vesselClass": "neoPanamax"},
        )
        assert res2.status_code == 200
        queries_for_2 = query_counts["count"]

        # Query 20 ports
        query_counts["count"] = 0
        start_time = time.perf_counter()
        res20 = await client.post(
            "/api/v1/risk/assessments/bulk",
            json={"ports": batch_20, "vesselClass": "neoPanamax"},
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        assert res20.status_code == 200
        queries_for_20 = query_counts["count"]

        # Latency check: < 500ms
        assert len(res20.json()) == 20
        assert elapsed_ms < 500.0, f"Bulk evaluation took {elapsed_ms:.1f}ms (> 500ms limit)"

        # O(1) query complexity assertion: querying 20 ports issues same constant number of SQL queries as 2 ports
        assert queries_for_20 == queries_for_2, (
            f"Queries scaled with batch size! (2 ports: {queries_for_2} queries, 20 ports: {queries_for_20} queries)"
        )

    event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_risk_user_watchlist_id_resolution(bulk_test_db):
    """Verify bulk risk evaluation correctly resolves user watchlist IDs (port-user-<uuid>)."""
    import uuid
    from backend.models import User, UserWatchlist

    engine, session_factory = bulk_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    test_user_id = uuid.uuid4()
    watchlist_id = uuid.uuid4()

    async with session_factory() as session:
        user = User(
            id=test_user_id,
            email="watchlist_operator@test.com",
            hashed_password="fakehashedpassword",
            name="Watchlist Operator",
        )
        session.add(user)
        uw = UserWatchlist(
            watchlist_id=watchlist_id,
            user_id=test_user_id,
            unlocode="NLRTM",
            vessel_class_id="neoPanamax",
        )
        session.add(uw)
        await session.commit()

    payload = {
        "ports": [
            {"id": f"port-user-{watchlist_id}", "name": "Custom Rotterdam Watchlist Entry"},
        ],
        "vesselClass": "neoPanamax",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/v1/risk/assessments/bulk", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assessment = data[0]
        assert assessment["portId"] == f"port-user-{watchlist_id}"
        assert assessment["portName"] == "Custom Rotterdam Watchlist Entry"
        assert assessment["vesselClass"] == "neoPanamax"
        assert "compositeScore" in assessment
        assert "subRisks" in assessment

    app.dependency_overrides.clear()
