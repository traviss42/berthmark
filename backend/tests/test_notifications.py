"""Unit and integration tests for notification endpoints."""

from fastapi.testclient import TestClient


def test_get_notifications_unauthorized(client: TestClient):
    """GET /api/v1/notifications requires Bearer token."""
    resp = client.get("/api/v1/notifications")
    assert resp.status_code == 401


def test_create_and_manage_notifications(client: TestClient, auth_headers: dict):
    """Create alert, list, mark as read, and mark all as read."""
    # Initially empty
    list_resp = client.get("/api/v1/notifications", headers=auth_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0

    # Create alert 1
    alert_payload_1 = {
        "portId": "port-rotterdam",
        "portName": "Port of Rotterdam",
        "newTier": "high",
        "previousTier": "medium",
    }
    create_resp_1 = client.post(
        "/api/v1/notifications/alerts", json=alert_payload_1, headers=auth_headers
    )
    assert create_resp_1.status_code == 201
    notif_1 = create_resp_1.json()
    assert notif_1["tier"] == "high"
    assert notif_1["previousTier"] == "medium"
    assert notif_1["read"] is False
    assert "High" in notif_1["title"]

    # Create alert 2
    alert_payload_2 = {
        "portId": "port-singapore",
        "portName": "Port of Singapore",
        "newTier": "medium",
        "previousTier": "low",
    }
    create_resp_2 = client.post(
        "/api/v1/notifications/alerts", json=alert_payload_2, headers=auth_headers
    )
    assert create_resp_2.status_code == 201
    notif_2 = create_resp_2.json()

    # List notifications (should have 2, newest first)
    list_resp = client.get("/api/v1/notifications", headers=auth_headers)
    assert list_resp.status_code == 200
    notifs = list_resp.json()
    assert len(notifs) == 2
    assert notifs[0]["id"] == notif_2["id"]

    # Mark first notification as read
    patch_resp = client.patch(
        f"/api/v1/notifications/{notif_2['id']}/read", headers=auth_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["read"] is True

    # Filter unread only (should have 1)
    unread_resp = client.get("/api/v1/notifications?unreadOnly=true", headers=auth_headers)
    assert unread_resp.status_code == 200
    assert len(unread_resp.json()) == 1
    assert unread_resp.json()[0]["id"] == notif_1["id"]

    # Mark all as read
    mark_all_resp = client.post(
        "/api/v1/notifications/mark-all-read", headers=auth_headers
    )
    assert mark_all_resp.status_code == 204

    # Verify none unread
    after_unread = client.get("/api/v1/notifications?unreadOnly=true", headers=auth_headers)
    assert len(after_unread.json()) == 0


def test_notification_multi_tenant_isolation(
    client: TestClient, auth_headers: dict, user2_auth_headers: dict
):
    """User 2 should not see notifications created for User 1."""
    alert_payload = {
        "portId": "port-rotterdam",
        "portName": "Port of Rotterdam",
        "newTier": "high",
        "previousTier": None,
    }
    client.post("/api/v1/notifications/alerts", json=alert_payload, headers=auth_headers)

    # User 2 notifications list is empty
    resp_user2 = client.get("/api/v1/notifications", headers=user2_auth_headers)
    assert resp_user2.status_code == 200
    assert len(resp_user2.json()) == 0
