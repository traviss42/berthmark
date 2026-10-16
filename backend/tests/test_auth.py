"""Unit and integration tests for authentication endpoints."""

from fastapi.testclient import TestClient


def test_login_successful(client: TestClient):
    """POST /api/v1/auth/login logs in a user and returns their profile with notification email."""
    resp = client.post("/api/v1/auth/login", json={"email": "captain@maritime.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["accessToken"] == "captain@maritime.com"
    assert data["tokenType"] == "bearer"
    assert data["user"]["email"] == "captain@maritime.com"
    assert data["user"]["name"] == "Captain"


def test_login_invalid_email(client: TestClient):
    """POST /api/v1/auth/login rejects invalid email formats."""
    resp = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_get_current_user_profile(client: TestClient):
    """GET /api/v1/auth/me returns current user identity from Bearer token."""
    headers = {"Authorization": "Bearer operations@globalshipping.com"}
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "operations@globalshipping.com"
    assert data["id"] == "operations@globalshipping.com"


def test_get_current_user_unauthorized(client: TestClient):
    """GET /api/v1/auth/me requires authorization."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_logout(client: TestClient):
    """POST /api/v1/auth/logout succeeds."""
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
