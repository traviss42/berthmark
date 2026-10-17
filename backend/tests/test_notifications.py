"""Unit and integration tests for notification endpoints."""

import pytest
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


def test_notification_sent_to_login_email_and_opt_out_respected(client: TestClient):
    """Verify notification recipientEmail is the login email when opted in, and None when opted out."""
    email_headers = {"Authorization": "Bearer portmanager@shippingcorp.com"}

    # 1. Add port (opted in by default)
    add_resp = client.post(
        "/api/v1/ports",
        json={"name": "Alert Port", "locode": "XXALT", "country": "Test", "lat": 1.0, "lon": 1.0},
        headers=email_headers,
    )
    assert add_resp.status_code == 201
    port_id = add_resp.json()["id"]

    # 2. Trigger alert for this port -> recipientEmail should be the login email
    alert_1 = {
        "portId": port_id,
        "portName": "Alert Port",
        "newTier": "high",
        "previousTier": "low",
    }
    notif_resp_1 = client.post("/api/v1/notifications/alerts", json=alert_1, headers=email_headers)
    assert notif_resp_1.status_code == 201
    assert notif_resp_1.json()["recipientEmail"] == "portmanager@shippingcorp.com"

    # 3. Opt out of notifications for this port
    opt_out_resp = client.patch(
        f"/api/v1/ports/{port_id}/notifications",
        json={"notificationsEnabled": False},
        headers=email_headers,
    )
    assert opt_out_resp.status_code == 200

    # 4. Trigger another alert -> recipientEmail should be None (email alerts opted out)
    alert_2 = {
        "portId": port_id,
        "portName": "Alert Port",
        "newTier": "medium",
        "previousTier": "high",
    }
    notif_resp_2 = client.post("/api/v1/notifications/alerts", json=alert_2, headers=email_headers)
    assert notif_resp_2.status_code == 201
    assert notif_resp_2.json()["recipientEmail"] is None


def test_immediate_subscription_baseline_email_sent(client: TestClient):
    """Adding a monitored port immediately dispatches a baseline welcome email and creates a notification."""
    from app.services.email_service import email_service
    email_service._sent_emails.clear()

    captain_headers = {"Authorization": "Bearer captain@rotterdam-logistics.nl"}

    # Add port (defaults to notificationsEnabled=True)
    resp = client.post(
        "/api/v1/ports",
        json={
            "name": "Port of Rotterdam",
            "locode": "NLRTM",
            "country": "Netherlands",
            "lat": 51.9,
            "lon": 4.4,
            "geofenceRadiusNm": 8.0,
        },
        headers=captain_headers,
    )
    assert resp.status_code == 201

    # Fetch notifications for this user
    notif_resp = client.get("/api/v1/notifications", headers=captain_headers)
    assert notif_resp.status_code == 200
    notifs = notif_resp.json()
    assert len(notifs) >= 1

    baseline_notif = notifs[0]
    assert "Subscribed (Baseline Risk:" in baseline_notif["title"]
    assert baseline_notif["recipientEmail"] == "captain@rotterdam-logistics.nl"
    assert "baseline risk" in baseline_notif["message"].lower()

    # Verify outbound email was recorded by email_service
    matching_emails = [
        e for e in email_service._sent_emails if e["to"] == "captain@rotterdam-logistics.nl"
    ]
    assert len(matching_emails) >= 1
    assert "[Berthmark Alert] Subscribed to Port of Rotterdam" in matching_emails[0]["subject"]
    assert "CURRENT LIVE BASELINE CONDITIONS" in matching_emails[0]["body"]
    # Verify flagged as demo account and real SMTP was suppressed
    assert matching_emails[0]["is_demo"] is True
    assert matching_emails[0]["smtp_dispatched"] is False


@pytest.mark.asyncio
async def test_demo_account_suppresses_smtp_delivery_and_prevents_bounces(monkeypatch):
    """Verify email_service skips SMTP delivery for demo accounts and dispatches for real accounts."""
    import smtplib
    from app.services.email_service import email_service, is_demo_account

    smtp_attempts = []

    class MockSMTP:
        def __init__(self, host, port, timeout=10):
            smtp_attempts.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def send_message(self, msg):
            pass

    monkeypatch.setattr(smtplib, "SMTP", MockSMTP)

    # 1. Test helper function
    assert is_demo_account("operations@pacific-shipping.com") is True
    assert is_demo_account("captain@rotterdam-logistics.nl") is True
    assert is_demo_account("risk-desk@globalmaritime.org") is True
    assert is_demo_account("test@example.com") is True
    assert is_demo_account("analyst@maritime.com") is True
    assert is_demo_account("harbormaster@portauthority.gov") is False

    # 2. Configure mock SMTP host
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mock-mail.com")

    # 3. Send email to demo account: SMTP should NOT be called
    res_demo = await email_service.send_email(
        to_email="operations@pacific-shipping.com",
        subject="Test Demo",
        plain_text="Demo Alert",
    )
    assert res_demo is True
    assert len(smtp_attempts) == 0  # No SMTP connection made!

    # 4. Send email to real operator account: SMTP SHOULD be called
    res_real = await email_service.send_email(
        to_email="harbormaster@portauthority.gov",
        subject="Real Operational Alert",
        plain_text="Critical Weather Alert",
    )
    assert res_real is True
    assert len(smtp_attempts) == 1  # SMTP connected!
    assert smtp_attempts[0] == ("smtp.mock-mail.com", 587)


def test_subscription_baseline_email_initiates_30_minute_cooldown(client: TestClient):
    """Subscription sends baseline email immediately, but suppresses subsequent warning emails for 30 minutes."""
    import time
    from app.services.email_service import email_service
    from app.services.notification_service import notification_service

    email_service._sent_emails.clear()
    user_headers = {"Authorization": "Bearer fleet-ops@shippingcorp.com"}

    # 1. User subscribes to a port
    add_resp = client.post(
        "/api/v1/ports",
        json={
            "name": "Port of Antwerp",
            "locode": "BEANR",
            "country": "Belgium",
            "lat": 51.26,
            "lon": 4.38,
            "geofenceRadiusNm": 8.0,
        },
        headers=user_headers,
    )
    assert add_resp.status_code == 201
    port_id = add_resp.json()["id"]

    # Verify baseline welcome email was dispatched immediately
    user_emails = [e for e in email_service._sent_emails if e["to"] == "fleet-ops@shippingcorp.com"]
    assert len(user_emails) == 1
    assert "Subscribed to Port of Antwerp" in user_emails[0]["subject"]

    # 2. Trigger a state-change alert shortly after subscription (within 30-minute window)
    alert_1 = {
        "portId": port_id,
        "portName": "Port of Antwerp",
        "newTier": "high",
        "previousTier": "low",
    }
    resp_alert_1 = client.post("/api/v1/notifications/alerts", json=alert_1, headers=user_headers)
    assert resp_alert_1.status_code == 201
    notif_1 = resp_alert_1.json()
    assert notif_1["tier"] == "high"
    # In-app notification was created, but email dispatch was throttled
    assert notif_1["emailDispatched"] is False

    # Outbound email list should still only contain the 1 baseline email
    user_emails_after_alert_1 = [
        e for e in email_service._sent_emails if e["to"] == "fleet-ops@shippingcorp.com"
    ]
    assert len(user_emails_after_alert_1) == 1

    # 3. Simulate passage of 30 minutes (advance cooldown timestamp by 1801 seconds)
    notification_service._last_email_sent[("fleet-ops@shippingcorp.com", port_id.lower())] = (
        time.time() - 1801.0
    )
    notification_service._last_email_sent[("fleet-ops@shippingcorp.com", "beanr")] = (
        time.time() - 1801.0
    )

    # Trigger second alert -> Cooldown has expired, so email MUST be dispatched
    alert_2 = {
        "portId": port_id,
        "portName": "Port of Antwerp",
        "newTier": "medium",
        "previousTier": "high",
    }
    resp_alert_2 = client.post("/api/v1/notifications/alerts", json=alert_2, headers=user_headers)
    assert resp_alert_2.status_code == 201
    notif_2 = resp_alert_2.json()
    assert notif_2["emailDispatched"] is True

    # Outbound email list should now contain 2 emails
    user_emails_after_alert_2 = [
        e for e in email_service._sent_emails if e["to"] == "fleet-ops@shippingcorp.com"
    ]
    assert len(user_emails_after_alert_2) == 2
    assert "Risk shifted to Medium" in user_emails_after_alert_2[1]["subject"]

    # 4. Immediate subsequent alert is again throttled under the newly reset 30-minute cooldown
    alert_3 = {
        "portId": port_id,
        "portName": "Port of Antwerp",
        "newTier": "high",
        "previousTier": "medium",
    }
    resp_alert_3 = client.post("/api/v1/notifications/alerts", json=alert_3, headers=user_headers)
    assert resp_alert_3.status_code == 201
    notif_3 = resp_alert_3.json()
    assert notif_3["emailDispatched"] is False

    user_emails_after_alert_3 = [
        e for e in email_service._sent_emails if e["to"] == "fleet-ops@shippingcorp.com"
    ]
    assert len(user_emails_after_alert_3) == 2


def test_stream_warmup_suppresses_warning_emails(client: TestClient):
    """Warning emails are suppressed during stream warm-up initialization to prevent noisy cold-start alarms."""
    import time
    from app.clients.ais_stream_manager import get_stream_manager
    from app.services.email_service import email_service
    from app.services.notification_service import notification_service

    email_service._sent_emails.clear()
    notification_service.clear_cooldown()

    headers = {"Authorization": "Bearer harbor-ops@ports.org"}
    stream_mgr = get_stream_manager()

    # Simulate active warm-up state
    stream_mgr._is_warming_up = True
    stream_mgr._warmup_start_time = time.time()
    stream_mgr._warmup_duration_sec = 20.0
    assert stream_mgr.is_warming_up is True

    # Trigger alert during warm-up
    alert = {
        "portId": "port-warmup-test",
        "portName": "Warmup Harbor",
        "newTier": "high",
        "previousTier": "low",
    }
    resp = client.post("/api/v1/notifications/alerts", json=alert, headers=headers)
    assert resp.status_code == 201
    notif = resp.json()
    assert notif["emailDispatched"] is False

    # Outbound email was suppressed
    matching_emails = [e for e in email_service._sent_emails if e["to"] == "harbor-ops@ports.org"]
    assert len(matching_emails) == 0

    # End warm-up
    stream_mgr._is_warming_up = False
    assert stream_mgr.is_warming_up is False

    # Trigger alert after warm-up finishes
    resp_after = client.post("/api/v1/notifications/alerts", json=alert, headers=headers)
    assert resp_after.status_code == 201
    notif_after = resp_after.json()
    assert notif_after["emailDispatched"] is True

    matching_emails_after = [
        e for e in email_service._sent_emails if e["to"] == "harbor-ops@ports.org"
    ]
    assert len(matching_emails_after) == 1
    assert "Risk shifted to High" in matching_emails_after[0]["subject"]




