"""Integration tests for Port Directory Search and Lookup Endpoints."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import get_db_session
from backend.main import app
from backend.models import Base, Port


@pytest_asyncio.fixture
async def ports_test_db():
    """Create test in-memory database seeded with sample commercial ports."""
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
        # Seed test ports
        ports = [
            Port(
                unlocode="NLRTM",
                port_name="Port of Rotterdam",
                country_code="NL",
                subdivision_code="NL-ZH",
                latitude=51.9244,
                longitude=4.4777,
                channel_depth_m=11.0,
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
                channel_depth_m=12.5,
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
            Port(
                unlocode="BEANR",
                port_name="Port of Antwerp-Bruges",
                country_code="BE",
                subdivision_code="BE-VAN",
                latitude=51.22,
                longitude=4.40,
                channel_depth_m=11.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
            Port(
                unlocode="FRLEH",
                port_name="Port du Havre",
                country_code="FR",
                subdivision_code="FR-76",
                latitude=49.49,
                longitude=0.11,
                channel_depth_m=15.5,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
        ]
        session.add_all(ports)
        await session.commit()

    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_default_ports(ports_test_db):
    """Verify GET /api/v1/ports/default returns benchmark ports with OpenAPI schema compliance."""
    async def override_get_db():
        async with ports_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/api/v1/ports/default")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 2

        locodes = {p["locode"] for p in data}
        assert "NLRTM" in locodes
        assert "SGSIN" in locodes

        for port in data:
            assert "id" in port
            assert "name" in port
            assert "locode" in port
            assert "country" in port
            assert "lat" in port
            assert "lon" in port
            assert -90.0 <= port["lat"] <= 90.0
            assert -180.0 <= port["lon"] <= 180.0
            assert port["isDefault"] is True
            assert port["addedByUserId"] is None
            assert 1.0 <= port["geofenceRadiusNm"] <= 50.0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_ports_success_and_casing(ports_test_db):
    """Verify search by port name, UN/LOCODE, and country with case insensitivity."""
    async def override_get_db():
        async with ports_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Search by lowercase name
        res1 = await client.get("/api/v1/ports/search?q=rotterdam")
        assert res1.status_code == 200
        items1 = res1.json()
        assert len(items1) >= 1
        assert any(p["locode"] == "NLRTM" for p in items1)

        # Search by uppercase UN/LOCODE
        res2 = await client.get("/api/v1/ports/search?q=NLRTM")
        assert res2.status_code == 200
        assert any(p["locode"] == "NLRTM" for p in res2.json())

        # Search by lowercase UN/LOCODE
        res3 = await client.get("/api/v1/ports/search?q=nlrtm")
        assert res3.status_code == 200
        assert any(p["locode"] == "NLRTM" for p in res3.json())

        # Search by country name
        res4 = await client.get("/api/v1/ports/search?q=netherlands")
        assert res4.status_code == 200
        assert any(p["locode"] == "NLRTM" for p in res4.json())

        # Search by ISO country code
        res5 = await client.get("/api/v1/ports/search?q=NL")
        assert res5.status_code == 200
        assert any(p["locode"] == "NLRTM" for p in res5.json())

        # Search non-existent port
        res_empty = await client.get("/api/v1/ports/search?q=nonexistentportquery123")
        assert res_empty.status_code == 200
        assert res_empty.json() == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_ports_validation_errors(ports_test_db):
    """Verify HTTP 400 Bad Request on missing, empty, or whitespace search queries."""
    async def override_get_db():
        async with ports_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Missing q
        res_missing = await client.get("/api/v1/ports/search")
        assert res_missing.status_code == 400
        err = res_missing.json()
        assert err["error"] == "Bad Request"
        assert err["statusCode"] == 400

        # Empty q=
        res_empty = await client.get("/api/v1/ports/search?q=")
        assert res_empty.status_code == 400
        assert res_empty.json()["statusCode"] == 400

        # Whitespace q
        res_spaces = await client.get("/api/v1/ports/search?q=%20%20")
        assert res_spaces.status_code == 400
        assert res_spaces.json()["statusCode"] == 400

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_port_by_id(ports_test_db):
    """Verify GET /api/v1/ports/{portId} by UN/LOCODE, port ID, and HTTP 404 for missing ports."""
    async def override_get_db():
        async with ports_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Lookup by uppercase UN/LOCODE
        res1 = await client.get("/api/v1/ports/NLRTM")
        assert res1.status_code == 200
        assert res1.json()["locode"] == "NLRTM"

        # Lookup by lowercase UN/LOCODE
        res2 = await client.get("/api/v1/ports/nlrtm")
        assert res2.status_code == 200
        assert res2.json()["locode"] == "NLRTM"

        # Lookup by designated port ID string
        res3 = await client.get("/api/v1/ports/port-rotterdam")
        assert res3.status_code == 200
        assert res3.json()["id"] == "port-rotterdam"

        # Unknown port ID -> 404
        res_404 = await client.get("/api/v1/ports/INVALID-PORT-999")
        assert res_404.status_code == 404
        err = res_404.json()
        assert err["error"] == "Not Found"
        assert err["statusCode"] == 404

        # URL-encoded special characters -> 404 safely
        res_special = await client.get("/api/v1/ports/%20%20")
        assert res_special.status_code == 404
        assert res_special.json()["statusCode"] == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_port_by_id_user_watchlist():
    """Verify GET /api/v1/ports/{portId} resolves custom watchlist ID port-user-<uuid>."""
    import uuid
    from backend.models import User, UserWatchlist

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_id = uuid.uuid4()
    watchlist_id = uuid.uuid4()

    async with session_factory() as session:
        from backend.taxonomy.seed import seed_vessel_classes
        await seed_vessel_classes(session)

        port = Port(
            unlocode="CAVAN",
            port_name="Vancouver",
            country_code="CA",
            subdivision_code="CA-BC",
            latitude=49.3,
            longitude=-123.1,
            channel_depth_m=10.7,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        user = User(
            id=test_user_id,
            email="vancouver_operator@test.com",
            hashed_password="pw",
            name="Vancouver Operator",
        )
        session.add(user)
        uw = UserWatchlist(
            watchlist_id=watchlist_id,
            user_id=test_user_id,
            unlocode="CAVAN",
            vessel_class_id="panamax",
        )
        session.add(uw)
        await session.commit()

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(f"/api/v1/ports/port-user-{watchlist_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == f"port-user-{watchlist_id}"
        assert data["name"] == "Vancouver"
        assert data["locode"] == "CAVAN"
        assert data["country"] == "Canada"
        assert data["vesselClass"] == "panamax"

        # Search Canadian ports
        res_van = await client.get("/api/v1/ports/search?q=Vancouver")
        assert res_van.status_code == 200
        assert len(res_van.json()) == 1
        assert res_van.json()[0]["locode"] == "CAVAN"

    app.dependency_overrides.clear()
    await engine.dispose()
