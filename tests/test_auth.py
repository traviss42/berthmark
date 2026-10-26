"""Unit and integration tests for User Authentication and Profile Endpoints."""

import uuid
from datetime import timedelta
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth.dependencies import get_current_user
from backend.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from backend.auth.seed import (
    DEFAULT_OPERATOR_EMAIL,
    DEFAULT_OPERATOR_NAME,
    DEFAULT_OPERATOR_PASSWORD,
    seed_default_user,
)
from backend.database import get_db_session
from backend.main import app
from backend.models import Base, User


@pytest_asyncio.fixture
async def auth_test_db():
    """Create an isolated test engine and session factory with schema loaded."""
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

    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_password_hashing_and_verification():
    """Verify password hashing with salt and constant-time verification."""
    password = "MySecurePassword123!"
    hashed = hash_password(password)

    # Must be hashed and not plain text
    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    # Positive and negative verification
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


@pytest.mark.asyncio
async def test_jwt_token_generation_and_decoding():
    """Verify signed JWT token claims: sub, email, iat, exp."""
    user_id = str(uuid.uuid4())
    email = "user@test.com"

    token, expires_in = create_access_token(
        {"sub": user_id, "email": email}, expires_delta=timedelta(hours=2)
    )

    assert isinstance(token, str)
    assert expires_in == 7200

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["email"] == email
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] > payload["iat"]


@pytest.mark.asyncio
async def test_seed_default_user_and_idempotency(auth_test_db):
    """Verify seeding the default operator user and idempotent re-execution."""
    async with auth_test_db() as session:
        user1 = await seed_default_user(session)
        assert user1.email == DEFAULT_OPERATOR_EMAIL
        assert user1.name == DEFAULT_OPERATOR_NAME
        assert verify_password(DEFAULT_OPERATOR_PASSWORD, user1.hashed_password) is True

        # Second execution: idempotent without error or duplicates
        user2 = await seed_default_user(session)
        assert user2.id == user1.id
        assert user2.email == DEFAULT_OPERATOR_EMAIL

        # Exactly 1 user in DB
        result = await session.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1


@pytest.mark.asyncio
async def test_login_success(auth_test_db):
    """Verify POST /api/v1/auth/login returns HTTP 200 with camelCase AuthResponse."""
    async with auth_test_db() as session:
        await seed_default_user(session)

    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Standard login
        payload = {
            "email": DEFAULT_OPERATOR_EMAIL,
            "password": DEFAULT_OPERATOR_PASSWORD,
        }
        res = await client.post("/api/v1/auth/login", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert "accessToken" in data
        assert data["tokenType"] == "Bearer"
        assert isinstance(data["expiresIn"], int)
        assert "user" in data

        user_info = data["user"]
        assert user_info["email"] == DEFAULT_OPERATOR_EMAIL
        assert user_info["name"] == DEFAULT_OPERATOR_NAME
        assert "id" in user_info
        assert "createdAt" in user_info

        # Case-insensitive email test
        payload_upper = {
            "email": DEFAULT_OPERATOR_EMAIL.upper(),
            "password": DEFAULT_OPERATOR_PASSWORD,
        }
        res_upper = await client.post("/api/v1/auth/login", json=payload_upper)
        assert res_upper.status_code == 200

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_invalid_credentials_and_sql_injection(auth_test_db):
    """Verify login failure handling, identical 401 error payloads, and SQL injection safety."""
    async with auth_test_db() as session:
        await seed_default_user(session)

    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Unregistered email
        res1 = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@maritimerisk.com", "password": "any"},
        )
        assert res1.status_code == 401
        assert res1.json() == {
            "error": "Unauthorized",
            "message": "Invalid credentials.",
            "statusCode": 401,
        }

        # 2. Incorrect password
        res2 = await client.post(
            "/api/v1/auth/login",
            json={"email": DEFAULT_OPERATOR_EMAIL, "password": "WrongPassword123!"},
        )
        assert res2.status_code == 401
        assert res2.json() == {
            "error": "Unauthorized",
            "message": "Invalid credentials.",
            "statusCode": 401,
        }

        # 3. SQL injection payload in password
        res3 = await client.post(
            "/api/v1/auth/login",
            json={"email": DEFAULT_OPERATOR_EMAIL, "password": "' OR '1'='1"},
        )
        assert res3.status_code == 401
        assert res3.json()["statusCode"] == 401

        # 4. Invalid email format -> 422
        res4 = await client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "somepassword"},
        )
        assert res4.status_code == 422

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_current_user_profile(auth_test_db):
    """Verify GET /api/v1/auth/me returns authenticated user details and handles token edge cases."""
    user = None
    async with auth_test_db() as session:
        user = await seed_default_user(session)

    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Valid token
        token, _ = create_access_token({"sub": str(user.id), "email": user.email})
        res = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(user.id)
        assert data["email"] == user.email
        assert data["name"] == user.name
        assert "createdAt" in data

        # Missing Authorization header -> 401
        res_no_auth = await client.get("/api/v1/auth/me")
        assert res_no_auth.status_code == 401
        assert res_no_auth.json()["statusCode"] == 401

        # Expired token -> 401
        expired_token, _ = create_access_token(
            {"sub": str(user.id), "email": user.email},
            expires_delta=timedelta(seconds=-10),
        )
        res_expired = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert res_expired.status_code == 401
        assert res_expired.json()["statusCode"] == 401

        # Malformed header -> 401
        res_malformed = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Token abc"}
        )
        assert res_malformed.status_code == 401

        # Tampered token -> 401
        res_tampered = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token[:-5]}abcde"}
        )
        assert res_tampered.status_code == 401

        # Non-existent user ID in token -> 401
        orphan_token, _ = create_access_token(
            {"sub": str(uuid.uuid4()), "email": "orphan@test.com"}
        )
        res_orphan = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {orphan_token}"}
        )
        assert res_orphan.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_user_success(auth_test_db):
    """Verify POST /api/auth/register securely creates user, hashes password, and returns AuthResponse."""
    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register new user via POST /api/auth/register
        reg_payload = {
            "name": "Jane Navigator",
            "email": "jane.navigator@maritime.org",
            "password": "SecurePassword123!",
        }
        res = await client.post("/api/auth/register", json=reg_payload)
        assert res.status_code == 201

        data = res.json()
        assert "accessToken" in data
        assert data["tokenType"] == "Bearer"
        assert isinstance(data["expiresIn"], int)
        assert data["user"]["email"] == "jane.navigator@maritime.org"
        assert data["user"]["name"] == "Jane Navigator"
        assert "createdAt" in data["user"]
        assert "id" in data["user"]

        token = data["accessToken"]

        # Verify access token works with /auth/me
        res_me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me.status_code == 200
        assert res_me.json()["email"] == "jane.navigator@maritime.org"

        # Verify password in DB is bcrypt-hashed and not plain text
        async with auth_test_db() as session:
            db_user = await session.scalar(
                select(User).where(User.email == "jane.navigator@maritime.org")
            )
            assert db_user is not None
            assert db_user.hashed_password != "SecurePassword123!"
            assert verify_password("SecurePassword123!", db_user.hashed_password) is True

        # Verify user can log in with registered credentials
        login_res = await client.post(
            "/api/auth/login",
            json={"email": "jane.navigator@maritime.org", "password": "SecurePassword123!"},
        )
        assert login_res.status_code == 200
        assert login_res.json()["user"]["email"] == "jane.navigator@maritime.org"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_duplicate_email_conflict(auth_test_db):
    """Verify POST /api/auth/register returns 409 Conflict when email is already registered."""
    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial registration
        await client.post(
            "/api/auth/register",
            json={"name": "First User", "email": "captain@fleet.com", "password": "SecretPassword123!"},
        )

        # Duplicate registration with same email (case-insensitive)
        dup_res = await client.post(
            "/api/auth/register",
            json={"name": "Duplicate User", "email": "CAPTAIN@fleet.com", "password": "AnotherPassword456!"},
        )
        assert dup_res.status_code == 409
        dup_data = dup_res.json()
        assert dup_data["error"] == "Conflict"
        assert "already registered" in dup_data["message"]
        assert dup_data["statusCode"] == 409

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_validation_errors(auth_test_db):
    """Verify POST /api/auth/register returns 400/422 for invalid inputs."""
    async def override_get_db():
        async with auth_test_db() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing email
        res1 = await client.post(
            "/api/auth/register",
            json={"name": "Test", "password": "Password123!"},
        )
        assert res1.status_code == 422

        # Invalid email format
        res2 = await client.post(
            "/api/auth/register",
            json={"name": "Test", "email": "invalid-email-format", "password": "Password123!"},
        )
        assert res2.status_code == 422

        # Blank/empty password
        res3 = await client.post(
            "/api/auth/register",
            json={"name": "Test", "email": "valid@email.com", "password": "   "},
        )
        assert res3.status_code == 400

    app.dependency_overrides.clear()

