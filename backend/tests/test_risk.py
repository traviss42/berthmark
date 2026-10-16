"""Unit and integration tests for risk scoring and trend endpoints."""

from fastapi.testclient import TestClient
from app.models.risk import CongestionMetrics, NavigationalMetrics, PortMetrics, TerminalMetrics, WeatherMetrics
from app.services.risk_service import risk_service


def test_get_risk_assessment_endpoint(client: TestClient):
    """GET /api/v1/ports/{portId}/risk returns complete assessment."""
    resp = client.get("/api/v1/ports/port-rotterdam/risk?vesselClass=neoPanamax")
    assert resp.status_code == 200
    data = resp.json()

    assert data["portId"] == "port-rotterdam"
    assert data["vesselClass"] == "neoPanamax"
    assert data["compositeTier"] in ["low", "medium", "high"]
    assert "congestion" in data["subRisks"]
    assert "terminalDelays" in data["subRisks"]
    assert "weather" in data["subRisks"]
    assert "navigational" in data["subRisks"]
    assert "metrics" in data


def test_weakest_link_scoring_rule():
    """Verify weakest-link rule: any high sub-risk forces composite to High."""
    metrics = PortMetrics(
        portId="port-test",
        timestamp="2026-10-16T00:00:00Z",
        congestion=CongestionMetrics(
            anchorageQueueCount=30,  # 30 / 10 = 3.0 ratio -> High
            avgWaitingTimeHours=40.0,
            berthOccupancyPct=95.0,
            rolling30dAvgQueue=10.0,
            rolling30dAvgWaitHours=20.0,
        ),
        terminal=TerminalMetrics(
            berthTurnaroundHours=20.0,
            berthToAnchorageWaitRatio=0.2,
            dwellTimeAnomalyScore=20.0,
            rolling30dAvgTurnaround=22.0,
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
            airDraftClearanceM=15.0,
            pilotageAvailable=True,
            tideHeightM=2.0,
        ),
    )

    sub_risks = {
        "congestion": risk_service._assess_congestion(metrics),
        "terminalDelays": risk_service._assess_terminal_delays(metrics),
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
            {"id": "port-singapore", "name": "Port of Singapore"},
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
