"""Unit and integration tests for User Watchlist Management API."""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth.security import create_access_token, hash_password
from backend.database import get_db_session
from backend.main import app
from backend.models import Base, Port, User, UserWatchlist, VesselClass
from backend.ports.schemas import PortCreate, PortResponse
from backend.ports.service import BENCHMARK_PORTS_METADATA, get_user_monitored_ports
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def watchlist_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy, default ports, and users."""
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
        # Seed vessel classes
        await seed_vessel_classes(session)

        # Seed default benchmark ports
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
                unlocode="CNSHA",
                port_name="Port of Shanghai",
                country_code="CN",
                subdivision_code="CN-SH",
                latitude=31.23,
                longitude=121.47,
                channel_depth_m=15.0,
                is_depth_available=True,
                reconciliation_method="EXACT_UNLOCODE",
            ),
        ]
        session.add_all(ports)

        # Seed two distinct test users
        user_a = User(
            id=uuid.uuid4(),
            email="user_a@maritimerisk.com",
            name="User Alpha",
            hashed_password=hash_password("Password123!"),
        )
        user_b = User(
            id=uuid.uuid4(),
            email="user_b@maritimerisk.com",
            name="User Beta",
            hashed_password=hash_password("Password123!"),
        )
        session.add_all([user_a, user_b])
        await session.commit()

        user_a_id = user_a.id
        user_b_id = user_b.id

    yield session_factory, user_a_id, user_b_id
    await engine.dispose()


# ─── 1. Unit Tests: Pydantic Validation ─────────────────────────────────────────

def test_pydantic_port_create_validation():
    """Verify PortCreate schema boundary and regex validation."""
    # Valid schema
    valid = PortCreate(
        name="Port of Valencia",
        locode="ESVLC",
        country="Spain",
        lat=39.46,
        lon=-0.37,
        geofenceRadiusNm=10.0,
    )
    assert valid.name == "Port of Valencia"
    assert valid.locode == "ESVLC"

    # Malformed LOCODE (lower case, wrong length, special chars)
    with pytest.raises(ValidationError):
        PortCreate(
            name="Valencia",
            locode="esvlc",
            country="Spain",
            lat=39.46,
            lon=-0.37,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="Valencia",
            locode="ESVLC1",
            country="Spain",
            lat=39.46,
            lon=-0.37,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="Valencia",
            locode="E-VLC",
            country="Spain",
            lat=39.46,
            lon=-0.37,
        )

    # Latitude bounds [-90, 90]
    with pytest.raises(ValidationError):
        PortCreate(
            name="North Pole Plus",
            locode="ZZNPP",
            country="Nowhere",
            lat=90.1,
            lon=0.0,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="South Pole Minus",
            locode="ZZSPM",
            country="Nowhere",
            lat=-90.1,
            lon=0.0,
        )

    # Longitude bounds [-180, 180]
    with pytest.raises(ValidationError):
        PortCreate(
            name="East Bound",
            locode="ZZEST",
            country="Nowhere",
            lat=0.0,
            lon=180.1,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="West Bound",
            locode="ZZWST",
            country="Nowhere",
            lat=0.0,
            lon=-180.1,
        )

    # Geofence radius bounds [1.0, 50.0]
    with pytest.raises(ValidationError):
        PortCreate(
            name="Too Small",
            locode="ZZSML",
            country="Nowhere",
            lat=0.0,
            lon=0.0,
            geofenceRadiusNm=0.5,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="Too Big",
            locode="ZZBIG",
            country="Nowhere",
            lat=0.0,
            lon=0.0,
            geofenceRadiusNm=50.5,
        )

    # Whitespace or empty string rejection
    with pytest.raises(ValidationError):
        PortCreate(
            name="   ",
            locode="ZZWHT",
            country="Nowhere",
            lat=0.0,
            lon=0.0,
        )
    with pytest.raises(ValidationError):
        PortCreate(
            name="Empty Country",
            locode="ZZEMP",
            country="",
            lat=0.0,
            lon=0.0,
        )


# ─── 2. Integration Tests: Unauthenticated & Invalid Token ────────────────────

@pytest.mark.asyncio
async def test_unauthenticated_requests(watchlist_test_db):
    """Verify 401 Unauthorized for requests lacking Authorization header."""
    session_factory, _, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # GET /api/v1/ports without auth
            res_get = await client.get("/api/v1/ports")
            assert res_get.status_code == 401
            data = res_get.json()
            assert data["error"] == "Unauthorized"
            assert data["statusCode"] == 401

            # POST /api/v1/ports without auth
            res_post = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Valencia",
                    "locode": "ESVLC",
                    "country": "Spain",
                    "lat": 39.46,
                    "lon": -0.37,
                    "geofenceRadiusNm": 8.0,
                },
            )
            assert res_post.status_code == 401
            assert res_post.json()["error"] == "Unauthorized"

            # DELETE /api/v1/ports/{portId} without auth
            res_del = await client.delete("/api/v1/ports/port-user-12345")
            assert res_del.status_code == 401
            assert res_del.json()["error"] == "Unauthorized"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_invalid_token_requests(watchlist_test_db):
    """Verify 401 Unauthorized for requests with malformed, fake, or invalid Bearer tokens."""
    session_factory, _, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid_headers = [
                {"Authorization": "Bearer not-a-valid-token"},
                {"Authorization": "InvalidScheme token123"},
                {"Authorization": "Bearer "},
            ]

            for headers in invalid_headers:
                res = await client.get("/api/v1/ports", headers=headers)
                assert res.status_code == 401
                assert res.json()["error"] == "Unauthorized"
                assert res.json()["statusCode"] == 401
    finally:
        app.dependency_overrides.clear()


# ─── 3. Integration Tests: Watchlist CRUD & Defaults ──────────────────────────

@pytest.mark.asyncio
async def test_get_ports_empty_watchlist(watchlist_test_db):
    """Verify authenticated user with no custom ports receives an empty watchlist."""
    session_factory, user_a_id, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token, _ = create_access_token({"sub": str(user_a_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/ports", headers=headers)
            assert res.status_code == 200
            ports = res.json()
            assert len(ports) == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_custom_port_and_duplicate_conflict(watchlist_test_db):
    """Verify adding a custom port (201) and rejecting duplicate LOCODE for same user (409)."""
    session_factory, user_a_id, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token, _ = create_access_token({"sub": str(user_a_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Add custom port
            payload = {
                "name": "Port of Valencia",
                "locode": "ESVLC",
                "country": "Spain",
                "lat": 39.46,
                "lon": -0.37,
                "geofenceRadiusNm": 8.0,
            }
            res_add = await client.post("/api/v1/ports", json=payload, headers=headers)
            assert res_add.status_code == 201
            created = res_add.json()
            assert created["name"] == "Port of Valencia"
            assert created["locode"] == "ESVLC"
            assert created["country"] == "Spain"
            assert created["lat"] == 39.46
            assert created["lon"] == -0.37
            assert created["isDefault"] is False
            assert created["addedByUserId"] == str(user_a_id)
            assert created["id"].startswith("port-user-")

            # 2. Verify GET /api/v1/ports returns 1 port (0 defaults + 1 custom)
            res_list = await client.get("/api/v1/ports", headers=headers)
            assert res_list.status_code == 200
            ports = res_list.json()
            assert len(ports) == 1
            custom = next(p for p in ports if p["locode"] == "ESVLC")
            assert custom["isDefault"] is False
            assert custom["addedByUserId"] == str(user_a_id)
            assert custom["id"] == created["id"]

            # 3. Attempt duplicate addition for same user -> 409 Conflict
            res_dup = await client.post("/api/v1/ports", json=payload, headers=headers)
            assert res_dup.status_code == 409
            dup_data = res_dup.json()
            assert dup_data["error"] == "Conflict"
            assert dup_data["statusCode"] == 409
            assert "Port with LOCODE 'ESVLC' is already in your watchlist." in dup_data["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_add_custom_port_validation_errors(watchlist_test_db):
    """Verify POST /api/v1/ports returns 400 Bad Request with ErrorResponse on validation failure."""
    session_factory, user_a_id, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token, _ = create_access_token({"sub": str(user_a_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            invalid_payloads = [
                # Malformed LOCODE
                ({"name": "Test", "locode": "bad_code", "country": "X", "lat": 10.0, "lon": 10.0, "geofenceRadiusNm": 8.0}),
                # Latitude out of bounds
                ({"name": "Test", "locode": "XXTST", "country": "X", "lat": 95.0, "lon": 10.0, "geofenceRadiusNm": 8.0}),
                # Longitude out of bounds
                ({"name": "Test", "locode": "XXTST", "country": "X", "lat": 10.0, "lon": 190.0, "geofenceRadiusNm": 8.0}),
                # Geofence radius < 1.0
                ({"name": "Test", "locode": "XXTST", "country": "X", "lat": 10.0, "lon": 10.0, "geofenceRadiusNm": 0.5}),
                # Geofence radius > 50.0
                ({"name": "Test", "locode": "XXTST", "country": "X", "lat": 10.0, "lon": 10.0, "geofenceRadiusNm": 60.0}),
                # Blank / whitespace name
                ({"name": "   ", "locode": "XXTST", "country": "X", "lat": 10.0, "lon": 10.0, "geofenceRadiusNm": 8.0}),
                # Missing country
                ({"name": "Test", "locode": "XXTST", "lat": 10.0, "lon": 10.0, "geofenceRadiusNm": 8.0}),
            ]

            for payload in invalid_payloads:
                res = await client.post("/api/v1/ports", json=payload, headers=headers)
                assert res.status_code == 400
                data = res.json()
                assert data["error"] == "Bad Request"
                assert data["statusCode"] == 400
                assert "message" in data
    finally:
        app.dependency_overrides.clear()


# ─── 4. Integration Tests: Multi-Tenant Data Isolation ────────────────────────

@pytest.mark.asyncio
async def test_multi_tenant_isolation(watchlist_test_db):
    """Verify User A and User B have complete isolation of custom ports and deletion permissions."""
    session_factory, user_a_id, user_b_id = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token_a, _ = create_access_token({"sub": str(user_a_id)})
    token_b, _ = create_access_token({"sub": str(user_b_id)})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. User A adds port ESVLC
            res_a = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Valencia",
                    "locode": "ESVLC",
                    "country": "Spain",
                    "lat": 39.46,
                    "lon": -0.37,
                    "geofenceRadiusNm": 8.0,
                },
                headers=headers_a,
            )
            assert res_a.status_code == 201
            port_a = res_a.json()

            # 2. User B can also add port ESVLC without conflict
            res_b = await client.post(
                "/api/v1/ports",
                json={
                    "name": "Port of Valencia",
                    "locode": "ESVLC",
                    "country": "Spain",
                    "lat": 39.46,
                    "lon": -0.37,
                    "geofenceRadiusNm": 12.0,
                },
                headers=headers_b,
            )
            assert res_b.status_code == 201
            port_b = res_b.json()

            # Distinct IDs and user associations
            assert port_a["id"] != port_b["id"]
            assert port_a["addedByUserId"] == str(user_a_id)
            assert port_b["addedByUserId"] == str(user_b_id)

            # 3. User A only sees their custom port, not User B's
            list_a = (await client.get("/api/v1/ports", headers=headers_a)).json()
            assert len(list_a) == 1
            assert any(p["id"] == port_a["id"] for p in list_a)
            assert not any(p["id"] == port_b["id"] for p in list_a)

            # 4. User B only sees their custom port, not User A's
            list_b = (await client.get("/api/v1/ports", headers=headers_b)).json()
            assert len(list_b) == 1
            assert any(p["id"] == port_b["id"] for p in list_b)
            assert not any(p["id"] == port_a["id"] for p in list_b)

            # 5. User A attempts to delete User B's port -> 403 Forbidden
            del_forbidden = await client.delete(f"/api/v1/ports/{port_b['id']}", headers=headers_a)
            assert del_forbidden.status_code == 403
            err_data = del_forbidden.json()
            assert err_data["error"] == "Forbidden"
            assert err_data["statusCode"] == 403
            assert "You do not have permission to delete this port." in err_data["message"]

            # User B's port is still intact
            list_b_check = (await client.get("/api/v1/ports", headers=headers_b)).json()
            assert any(p["id"] == port_b["id"] for p in list_b_check)

            # 6. User B deletes their own port -> 204 No Content
            del_ok = await client.delete(f"/api/v1/ports/{port_b['id']}", headers=headers_b)
            assert del_ok.status_code == 204
            assert del_ok.content == b""

            # Subsequent list confirms port_b is removed (watchlist is now empty)
            list_b_post_del = (await client.get("/api/v1/ports", headers=headers_b)).json()
            assert len(list_b_post_del) == 0
            assert not any(p["id"] == port_b["id"] for p in list_b_post_del)

            # User A's port is unaffected
            list_a_check = (await client.get("/api/v1/ports", headers=headers_a)).json()
            assert any(p["id"] == port_a["id"] for p in list_a_check)
    finally:
        app.dependency_overrides.clear()


# ─── 5. Integration Tests: Deletion Constraints & Edge Cases ──────────────────

@pytest.mark.asyncio
async def test_delete_default_port_rejection(watchlist_test_db):
    """Verify attempting to delete a default benchmark port returns 400 Bad Request."""
    session_factory, user_a_id, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token, _ = create_access_token({"sub": str(user_a_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test default port ID and LOCODE formats
            for default_id in ["port-rotterdam", "NLRTM", "port-singapore", "SGSIN"]:
                res = await client.delete(f"/api/v1/ports/{default_id}", headers=headers)
                assert res.status_code == 400
                data = res.json()
                assert data["error"] == "Bad Request"
                assert data["statusCode"] == 400
                assert "System default ports cannot be removed." in data["message"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_nonexistent_port(watchlist_test_db):
    """Verify attempting to delete a non-existent port returns 404 Not Found."""
    session_factory, user_a_id, _ = watchlist_test_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    token, _ = create_access_token({"sub": str(user_a_id)})
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_uuid = str(uuid.uuid4())
            res = await client.delete(f"/api/v1/ports/port-user-{fake_uuid}", headers=headers)
            assert res.status_code == 404
            data = res.json()
            assert data["error"] == "Not Found"
            assert data["statusCode"] == 404
    finally:
        app.dependency_overrides.clear()


# ─── 6. Performance & Architecture: Eager Loading Verification ────────────────

@pytest.mark.asyncio
async def test_selectinload_eager_loading(watchlist_test_db):
    """Verify get_user_monitored_ports loads custom ports and port entities without lazy query overhead."""
    session_factory, user_a_id, _ = watchlist_test_db

    async with session_factory() as session:
        # Create a custom port and watchlist entry
        port = Port(
            unlocode="FRLEH",
            port_name="Port du Havre",
            country_code="FR",
            subdivision_code="FR-76",
            latitude=49.49,
            longitude=0.11,
            channel_depth_m=15.5,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        await session.flush()

        wl = UserWatchlist(
            watchlist_id=uuid.uuid4(),
            user_id=user_a_id,
            unlocode="FRLEH",
            vessel_class_id="panamax",
            geofence_radius_nm=8.0,
        )
        session.add(wl)
        await session.commit()

        # Query user monitored ports
        ports = await get_user_monitored_ports(session, user_a_id)
        assert len(ports) == 1
        leh = next(p for p in ports if p.locode == "FRLEH")
        assert leh.name == "Port du Havre"
        assert leh.isDefault is False
        assert leh.addedByUserId == str(user_a_id)
