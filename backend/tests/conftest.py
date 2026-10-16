"""Pytest test fixtures and configuration."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.port_service import PortService, port_service
from app.services.notification_service import NotificationService, notification_service
from app.services.risk_service import RiskService, risk_service


@pytest.fixture(autouse=True)
def reset_services():
    """Reset service in-memory stores before each test to maintain test isolation."""
    # Reset user ports
    port_service._user_ports.clear()
    # Reset notifications
    notification_service._user_notifications.clear()
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
