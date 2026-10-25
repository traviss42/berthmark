"""Unit and integration tests for Notification Service and State-Change Alert API (Issue 18)."""

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth.security import create_access_token, hash_password
from backend.database import get_db_session
from backend.main import app
from backend.models import AlertLog, Base, Port, User
from backend.schemas.notification import Notification, NotificationCreate
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def notif_test_db():
    """Create in-memory SQLite database seeded with vessel taxonomy, users, and alert logs."""
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

    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    async with session_factory() as session:
        await seed_vessel_classes(session)

        # Seed users
        user_a = User(
            id=user_a_id,
            email="usera@maritimerisk.com",
            hashed_password=hash_password("Pass123!"),
            name="User Alpha",
        )
        user_b = User(
            id=user_b_id,
            email="userb@maritimerisk.com",
            hashed_password=hash_password("Pass123!"),
            name="User Beta",
        )
        # Seed port
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
        session.add_all([user_a, user_b, port])
        await session.commit()

        # Seed alert logs for User A (3 alerts: 2 unread, 1 read)
        alert1 = AlertLog(
            alert_id=uuid.uuid4(),
            user_id=user_a_id,
            unlocode="NLRTM",
            vessel_class_id="neoPanamax",
            type="stateChange",
            title="Port of Rotterdam: Risk tier changed to High",
            message="Port of Rotterdam risk status shifted from Medium to High.",
            previous_risk_level="MEDIUM",
            new_risk_level="HIGH",
            trigger_reason="Queue threshold exceeded.",
            is_read=False,
            created_at=datetime(2026, 10, 19, 3, 0, 0, tzinfo=timezone.utc),
        )
        alert2 = AlertLog(
            alert_id=uuid.uuid4(),
            user_id=user_a_id,
            unlocode="NLRTM",
            vessel_class_id="neoPanamax",
            type="stateChange",
            title="Port of Rotterdam: Risk tier changed to Medium",
            message="Port of Rotterdam risk status shifted from Low to Medium.",
            previous_risk_level="LOW",
            new_risk_level="MEDIUM",
            trigger_reason="Swell height increased.",
            is_read=False,
            created_at=datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        alert3 = AlertLog(
            alert_id=uuid.uuid4(),
            user_id=user_a_id,
            unlocode="NLRTM",
            vessel_class_id="neoPanamax",
            type="stateChange",
            title="Port of Rotterdam: Risk tier changed to Low",
            message="Port of Rotterdam risk status shifted from None to Low.",
            previous_risk_level=None,
            new_risk_level="LOW",
            trigger_reason="Initial port evaluation.",
            is_read=True,
            created_at=datetime(2026, 10, 17, 6, 0, 0, tzinfo=timezone.utc),
        )
        # Seed 1 alert for User B
        alert_b = AlertLog(
            alert_id=uuid.uuid4(),
            user_id=user_b_id,
            unlocode="NLRTM",
            vessel_class_id="neoPanamax",
            type="stateChange",
            title="User B Alert",
            message="Secret notification for User B only.",
            previous_risk_level="LOW",
            new_risk_level="HIGH",
            trigger_reason="Traffic surge.",
            is_read=False,
            created_at=datetime(2026, 10, 19, 4, 0, 0, tzinfo=timezone.utc),
        )

        session.add_all([alert1, alert2, alert3, alert_b])
        await session.commit()

    token_a, _ = create_access_token({"sub": str(user_a_id)})
    token_b, _ = create_access_token({"sub": str(user_b_id)})

    yield engine, session_factory, user_a_id, user_b_id, token_a, token_b
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_notifications_feed_and_filtering(notif_test_db):
    """Verify GET /api/v1/notifications returns reverse-chronological items and unreadOnly filtering."""
    engine, session_factory, user_a_id, user_b_id, token_a, token_b = notif_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Fetch all notifications for User A
        res = await client.get("/api/v1/notifications", headers=headers_a)
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 3

        # Reverse chronological ordering check
        timestamps = [item["timestamp"] for item in data]
        assert timestamps == sorted(timestamps, reverse=True)

        # Verify schema conformity
        first = data[0]
        assert first["id"].startswith("notif-")
        assert first["type"] == "stateChange"
        assert first["portId"] == "port-rotterdam"
        assert first["portName"] == "Port of Rotterdam"
        assert first["tier"] == "high"
        assert first["previousTier"] == "medium"
        assert first["read"] is False

        # 2. Fetch unreadOnly for User A
        res_unread = await client.get("/api/v1/notifications?unreadOnly=true", headers=headers_a)
        assert res_unread.status_code == 200
        data_unread = res_unread.json()
        assert len(data_unread) == 2
        for item in data_unread:
            assert item["read"] is False

        # 3. Test limit capping
        res_lim = await client.get("/api/v1/notifications?limit=1", headers=headers_a)
        assert res_lim.status_code == 200
        assert len(res_lim.json()) == 1

        # 4. Root route /notifications
        res_root = await client.get("/notifications", headers=headers_a)
        assert res_root.status_code == 200
        assert len(res_root.json()) == 3

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_read_notifications(notif_test_db):
    """Verify POST /api/v1/notifications and PATCH /api/v1/notifications/{id}/read."""
    engine, session_factory, user_a_id, user_b_id, token_a, token_b = notif_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. POST /api/v1/notifications
        create_payload = {
            "type": "stateChange",
            "portId": "port-rotterdam",
            "portName": "Port of Rotterdam",
            "newTier": "high",
            "previousTier": "low",
        }
        res_create = await client.post("/api/v1/notifications", json=create_payload, headers=headers_a)
        assert res_create.status_code == 201
        created = res_create.json()
        assert created["tier"] == "high"
        assert created["previousTier"] == "low"
        assert created["read"] is False
        notif_id = created["id"]

        # 2. PATCH /api/v1/notifications/{id}/read
        res_patch = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers_a)
        assert res_patch.status_code == 200
        updated = res_patch.json()
        assert updated["read"] is True

        # 3. Idempotent patch call returns 200
        res_patch_again = await client.patch(f"/api/v1/notifications/{notif_id}/read", headers=headers_a)
        assert res_patch_again.status_code == 200
        assert res_patch_again.json()["read"] is True

        # 4. Invalid notification ID returns 404
        res_404 = await client.patch("/api/v1/notifications/nonexistent-id/read", headers=headers_a)
        assert res_404.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mark_all_read(notif_test_db):
    """Verify POST /api/v1/notifications/mark-all-read updates all unread notifications to read."""
    engine, session_factory, user_a_id, user_b_id, token_a, token_b = notif_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    headers_a = {"Authorization": f"Bearer {token_a}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Mark all read
        res = await client.post("/api/v1/notifications/mark-all-read", headers=headers_a)
        assert res.status_code == 204

        # Subsequent unreadOnly returns empty array []
        res_unread = await client.get("/api/v1/notifications?unreadOnly=true", headers=headers_a)
        assert res_unread.status_code == 200
        assert res_unread.json() == []

        # Calling again when 0 unread succeeds idempotently
        res_again = await client.post("/api/v1/notifications/mark-all-read", headers=headers_a)
        assert res_again.status_code == 204

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_multi_tenant_isolation(notif_test_db):
    """Verify strict multi-tenant isolation between User A and User B."""
    engine, session_factory, user_a_id, user_b_id, token_a, token_b = notif_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # User B feed only contains User B's alert
        res_b = await client.get("/api/v1/notifications", headers=headers_b)
        assert res_b.status_code == 200
        data_b = res_b.json()
        assert len(data_b) == 1
        assert data_b[0]["title"] == "User B Alert"
        notif_b_id = data_b[0]["id"]

        # User A cannot read User B's notification -> 404
        res_a_hack = await client.patch(f"/api/v1/notifications/{notif_b_id}/read", headers=headers_a)
        assert res_a_hack.status_code == 404

        # User A mark-all-read does NOT mark User B's alert as read
        await client.post("/api/v1/notifications/mark-all-read", headers=headers_a)

        res_b_check = await client.get("/api/v1/notifications?unreadOnly=true", headers=headers_b)
        assert res_b_check.status_code == 200
        assert len(res_b_check.json()) == 1  # Still unread for User B!

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_and_param_validation_errors(notif_test_db):
    """Verify 401 Unauthorized on missing/bad token and 400 Bad Request on invalid limit."""
    engine, session_factory, user_a_id, user_b_id, token_a, token_b = notif_test_db

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Missing Authorization header -> 401
        res_no_auth = await client.get("/api/v1/notifications")
        assert res_no_auth.status_code == 401

        # 2. Invalid Bearer token -> 401
        res_bad_auth = await client.get(
            "/api/v1/notifications", headers={"Authorization": "Bearer bad_token"}
        )
        assert res_bad_auth.status_code == 401

        # 3. limit < 1 -> 400
        headers_a = {"Authorization": f"Bearer {token_a}"}
        res_zero_lim = await client.get("/api/v1/notifications?limit=0", headers=headers_a)
        assert res_zero_lim.status_code == 400
        assert res_zero_lim.json()["statusCode"] == 400

        # 4. limit > 100 -> 400
        res_high_lim = await client.get("/api/v1/notifications?limit=101", headers=headers_a)
        assert res_high_lim.status_code == 400
        assert res_high_lim.json()["statusCode"] == 400

    app.dependency_overrides.clear()
