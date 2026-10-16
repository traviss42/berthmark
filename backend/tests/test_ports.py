"""Unit and integration tests for port endpoints."""

from fastapi.testclient import TestClient


def test_get_default_ports(client: TestClient):
    """GET /api/v1/ports/defaults returns standard default global ports with NGA WPI depth data without auth."""
    resp = client.get("/api/v1/ports/defaults")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 6
    locodes = [p["locode"] for p in data]
    assert "NLRTM" in locodes
    assert "SGKEP" in locodes
    assert all(p["isDefault"] is True for p in data)
    assert all(p["channelDepthM"] is not None and p["channelDepthM"] > 0 for p in data)


def test_search_ports(client: TestClient):
    """GET /api/v1/ports/search queries ports by name, locode, or country."""
    # Search by name
    resp = client.get("/api/v1/ports/search?q=Rotterdam")
    assert resp.status_code == 200
    assert any("Rotterdam" in p["name"] for p in resp.json())

    # Search by LOCODE
    resp = client.get("/api/v1/ports/search?q=SGKEP")
    assert resp.status_code == 200
    assert any(p["locode"] == "SGKEP" for p in resp.json())

    # Search by country
    resp = client.get("/api/v1/ports/search?q=Belgium")
    assert resp.status_code == 200
    assert any(p["country"] == "Belgium" for p in resp.json())


def test_get_monitored_ports_unauthorized(client: TestClient):
    """GET /api/v1/ports requires Bearer authentication."""
    resp = client.get("/api/v1/ports")
    assert resp.status_code == 401


def test_get_monitored_ports_authorized(client: TestClient, auth_headers: dict):
    """GET /api/v1/ports returns monitored ports for authenticated user (starts empty, user selects their own)."""
    resp = client.get("/api/v1/ports", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_add_and_remove_custom_port(client: TestClient, auth_headers: dict):
    """POST /api/v1/ports adds a private custom port, DELETE removes it."""
    payload = {
        "name": "Custom Test Port",
        "locode": "XXTST",
        "country": "Testland",
        "lat": 10.5,
        "lon": 20.5,
        "geofenceRadiusNm": 6.5,
    }
    # Add port
    create_resp = client.post("/api/v1/ports", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    created_port = create_resp.json()
    assert created_port["name"] == "Custom Test Port"
    assert created_port["locode"] == "XXTST"
    assert created_port["isDefault"] is False
    assert created_port["addedByUserId"] == "mock-user"
    port_id = created_port["id"]

    # Verify present in list
    list_resp = client.get("/api/v1/ports", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(p["id"] == port_id for p in list_resp.json())

    # Cannot add duplicate locode
    dup_resp = client.post("/api/v1/ports", json=payload, headers=auth_headers)
    assert dup_resp.status_code == 409

    # Remove port
    delete_resp = client.delete(f"/api/v1/ports/{port_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    # Verify removed
    list_after = client.get("/api/v1/ports", headers=auth_headers)
    assert not any(p["id"] == port_id for p in list_after.json())


def test_cannot_delete_non_monitored_port(client: TestClient, auth_headers: dict):
    """DELETE /api/v1/ports/{portId} returns 404 if port is not in user's monitored list."""
    resp = client.delete("/api/v1/ports/port-nonexistent", headers=auth_headers)
    assert resp.status_code == 404


def test_port_notification_opt_in_default_and_opt_out(client: TestClient, auth_headers: dict):
    """Verify that custom ports are opted into notifications by default and can be opted out."""
    payload = {
        "name": "Notify Port",
        "locode": "XXNOT",
        "country": "Alertland",
        "lat": 15.0,
        "lon": 25.0,
    }
    create_resp = client.post("/api/v1/ports", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    port = create_resp.json()
    assert port["notificationsEnabled"] is True  # Default opt-in
    port_id = port["id"]

    # Opt out of notifications for this port
    opt_out_resp = client.patch(
        f"/api/v1/ports/{port_id}/notifications",
        json={"notificationsEnabled": False},
        headers=auth_headers,
    )
    assert opt_out_resp.status_code == 200
    assert opt_out_resp.json()["notificationsEnabled"] is False

    # Check that GET /api/v1/ports reflects this preference
    list_resp = client.get("/api/v1/ports", headers=auth_headers)
    assert list_resp.status_code == 200
    found = next(p for p in list_resp.json() if p["id"] == port_id)
    assert found["notificationsEnabled"] is False

    # Toggle back to opt-in
    opt_in_resp = client.patch(
        f"/api/v1/ports/{port_id}/notifications",
        json={"notificationsEnabled": True},
        headers=auth_headers,
    )
    assert opt_in_resp.status_code == 200
    assert opt_in_resp.json()["notificationsEnabled"] is True



def test_port_privacy_multi_tenant(
    client: TestClient, auth_headers: dict, user2_auth_headers: dict
):
    """User B cannot see or delete User A's custom ports."""
    payload = {
        "name": "Private Port A",
        "locode": "XXPRA",
        "country": "Country A",
        "lat": 12.0,
        "lon": 14.0,
        "geofenceRadiusNm": 8.0,
    }
    create_resp = client.post("/api/v1/ports", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    port_id = create_resp.json()["id"]

    # User 2 list should not contain User 1's port
    user2_list = client.get("/api/v1/ports", headers=user2_auth_headers)
    assert user2_list.status_code == 200
    assert not any(p["id"] == port_id for p in user2_list.json())

    # User 2 cannot delete User 1's port
    del_resp = client.delete(f"/api/v1/ports/{port_id}", headers=user2_auth_headers)
    assert del_resp.status_code == 404


def test_search_japan_and_canadian_ports(client: TestClient, auth_headers: dict):
    """Verify combined UN/LOCODE (Function=1) + NGA WPI (Channel Depth > 0) ports and single-file coordinate rule."""
    # 1. Search Japan by country
    resp_jp = client.get("/api/v1/ports/search?q=Japan")
    assert resp_jp.status_code == 200
    jp_ports = resp_jp.json()
    assert len(jp_ports) >= 5
    assert all(p["country"] == "Japan" and p["channelDepthM"] > 0 for p in jp_ports)

    # 2. Search Japanese ports by LOCODE / name
    for locode, expected_name in [("JPTYO", "Tokyo"), ("JPYOK", "Yokohama"), ("JPOSA", "Osaka"), ("JPUKB", "Kobe")]:
        resp = client.get(f"/api/v1/ports/search?q={locode}")
        assert resp.status_code == 200
        assert any(p["locode"] == locode and expected_name in p["name"] and p["channelDepthM"] > 0 for p in resp.json())

    # 3. Search Canada by country
    resp_ca = client.get("/api/v1/ports/search?q=Canada")
    assert resp_ca.status_code == 200
    ca_ports = resp_ca.json()
    assert len(ca_ports) >= 5
    assert all(p["country"] == "Canada" and p["channelDepthM"] > 0 for p in ca_ports)

    # 4. Search Canadian ports: CAVIC (coords in both) and CAMTR (coords taken from NGA WPI when blank in UN/LOCODE)
    for locode, expected_name in [("CAVIC", "Victoria"), ("CAVAN", "Vancouver"), ("CAMTR", "Montreal")]:
        resp = client.get(f"/api/v1/ports/search?q={locode}")
        assert resp.status_code == 200
        assert any(p["locode"] == locode and expected_name in p["name"] and p["channelDepthM"] > 0 for p in resp.json())

    # 5. Access risk evaluation directly by UN/LOCODE and verify real NGA WPI depth is used
    risk_resp = client.get("/api/v1/ports/JPTYO/risk?vesselClass=panamax")
    assert risk_resp.status_code == 200
    risk_data = risk_resp.json()
    assert risk_data["portId"] == "JPTYO"
    assert "weather" in risk_data["subRisks"]
    assert "congestion" in risk_data["subRisks"]
    assert "navigational" in risk_data["subRisks"]
    assert "terminalDelays" not in risk_data["subRisks"]
    assert risk_data["metrics"]["navigational"]["channelDepthM"] == 15.5


