"""Pytest test fixtures and configuration with database isolation."""

import pytest
from fastapi.testclient import TestClient
from app.db import init_db, get_db_context
from app.db.models import MonitoredPort, NotificationRecord
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure database schema is initialized for testing session."""
    init_db()


@pytest.fixture(autouse=True)
def reset_database():
    """Clear database tables before each test to maintain strict test isolation."""
    with get_db_context() as db:
        db.query(NotificationRecord).delete()
        db.query(MonitoredPort).delete()
        db.commit()
    yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict:
    """Standard Bearer auth headers for mock-user."""
    return {"Authorization": "Bearer mock-user"}


@pytest.fixture
def user2_auth_headers() -> dict:
    """Bearer auth headers for user-2 (for multi-tenant tests)."""
    return {"Authorization": "Bearer user-2"}
