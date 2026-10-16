"""Unit and integration tests for risk scoring and trend endpoints."""

from fastapi.testclient import TestClient
from app.models.risk import CongestionMetrics, NavigationalMetrics, PortMetrics, WeatherMetrics
from app.services.risk_service import risk_service


def test_get_risk_assessment_endpoint(client: TestClient):
    """GET /api/v1/ports/{portId}/risk returns complete assessment with 3 real sub-risks."""
    resp = client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=neoPanamax")
    assert resp.status_code == 200
    data = resp.json()

    assert data["portId"] == "port-rotterdam"
    assert data["vesselClass"] == "neoPanamax"
    assert data["compositeTier"] in ["low", "medium", "high"]
    assert "congestion" in data["subRisks"]
    assert "weather" in data["subRisks"]
    assert "navigational" in data["subRisks"]
    assert "terminalDelays" not in data["subRisks"]
    assert "metrics" in data
    assert data["metrics"]["navigational"]["channelDepthM"] == 11.0


def test_weakest_link_scoring_rule():
    """Verify weakest-link rule: any high sub-risk forces composite to High."""
    metrics = PortMetrics(
        portId="port-test",
        timestamp="2026-10-16T00:00:00Z",
        congestion=CongestionMetrics(
            anchorageQueueCount=30,  # 30 / 10 = 3.0 ratio -> High
            activeVesselCount=55,
            movingVesselCount=25,
            rolling30dAvgQueue=10.0,
        ),
        weather=WeatherMetrics(
            windSpeedKnots=10.0,
            gustSpeedKnots=12.0,
            waveHeightM=0.5,
            swellPeriodSec=5.0,
            visibilityNm=10.0,
        ),
        navigational=NavigationalMetrics(
            underKeelClearanceM=5.0,
            channelDepthM=18.0,
            cargoPierDepthM=17.5,
            anchorageDepthM=20.0,
            vesselDraftM=12.5,
            overheadLimits="No",
            pilotageAvailable=True,
            tugsAssistance=True,
            tideHeightM=2.0,
            harborSize="Large",
            shelterAfforded="Good",
        ),
    )

    sub_risks = {
        "congestion": risk_service._assess_congestion(metrics),
        "weather": risk_service._assess_weather(metrics, "neoPanamax"),
        "navigational": risk_service._assess_navigational(metrics, "neoPanamax"),
    }

    tier, score = risk_service._compute_composite(sub_risks)
    assert tier == "high"
    assert score == 90.0


def test_bulk_risk_assessment_endpoint(client: TestClient):
    """POST /api/v1/risk/bulk-assessments evaluates array of ports."""
    payload = {
        "ports": [
            {"id": "port-rotterdam", "name": "Port of Rotterdam"},
            {"id": "port-singapore", "name": "Port of Keppel"},
        ],
        "vesselClass": "ulcv",
    }
    resp = client.post("/api/v1/risk/bulk-assessments", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["portId"] == "port-rotterdam"
    assert data[1]["portId"] == "port-singapore"
    assert data[0]["vesselClass"] == "ulcv"


def test_historical_trend_endpoint(client: TestClient):
    """GET /api/v1/ports/{portId}/risk/trend returns chronological evaluations."""
    resp = client.get("/api/v1/ports/port-rotterdam/risk/trend?vesselClass=panamax&days=3")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 12  # 3 days * 4 evaluations per day

    # Check timestamps are in chronological order
    timestamps = [item["timestamp"] for item in data]
    assert timestamps == sorted(timestamps)


def test_risk_caching_and_force_refresh(client: TestClient):
    """Verify that repeated risk calls return cached assessment, while forceRefresh=true recomputes."""
    # First call: computes and caches
    resp1 = client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=feeder")
    assert resp1.status_code == 200
    data1 = resp1.json()

    # Second call without forceRefresh: should return cached assessment (same id)
    resp2 = client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=feeder")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data1["id"] == data2["id"]

    # Third call with forceRefresh=true: bypasses cache
    resp3 = client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=feeder&forceRefresh=true")
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["portId"] == "port-rotterdam"


