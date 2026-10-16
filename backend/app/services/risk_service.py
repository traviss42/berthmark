"""Risk evaluation service implementing multi-factor scoring and the weakest-link composite rule."""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from app.clients.ais_client import AISClient
from app.clients.weather_client import MarineWeatherClient
from app.models.common import RiskTier, SubRiskCategory, VesselClass
from app.models.risk import (
    PortMetrics,
    PortRef,
    RiskAssessment,
    SubRiskResult,
)
from app.services.port_service import PortService, port_service as default_port_service

# Vessel Taxonomy details matching frontend
VESSEL_CLASS_METADATA: Dict[VesselClass, Dict[str, str]] = {
    "feeder": {"label": "Feeder", "sector": "containerized"},
    "panamax": {"label": "Panamax / Sub-Panamax", "sector": "containerized"},
    "neoPanamax": {"label": "Neo-Panamax", "sector": "containerized"},
    "ulcv": {"label": "ULCV (Ultra Large)", "sector": "containerized"},
    "mrTanker": {"label": "MR / Handysize Tanker", "sector": "liquidBulk"},
    "aframax": {"label": "Aframax", "sector": "liquidBulk"},
    "suezmax": {"label": "Suezmax", "sector": "liquidBulk"},
    "vlcc": {"label": "VLCC / ULCC", "sector": "liquidBulk"},
    "handysize": {"label": "Handysize / Supramax", "sector": "dryBulk"},
    "panamaxBulk": {"label": "Panamax (Bulk)", "sector": "dryBulk"},
    "capesize": {"label": "Capesize", "sector": "dryBulk"},
    "pctc": {"label": "PCC / PCTC (Car Carriers)", "sector": "specialized"},
    "lng": {"label": "LNG / LPG Carriers", "sector": "specialized"},
}

# PIANC Guidelines (Report 121) thresholds
VESSEL_CLASS_THRESHOLDS: Dict[VesselClass, Dict[str, float]] = {
    "feeder": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 1.0, "ukcMediumM": 2.0, "airDraftLowM": 2.0, "airDraftMediumM": 5.0},
    "panamax": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 1.2, "ukcMediumM": 2.5, "airDraftLowM": 3.0, "airDraftMediumM": 6.0},
    "neoPanamax": {"windHighKnots": 35, "windMediumKnots": 25, "ukcHighM": 1.5, "ukcMediumM": 3.0, "airDraftLowM": 4.0, "airDraftMediumM": 8.0},
    "ulcv": {"windHighKnots": 28, "windMediumKnots": 20, "ukcHighM": 2.0, "ukcMediumM": 3.5, "airDraftLowM": 5.0, "airDraftMediumM": 10.0},
    "mrTanker": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 1.0, "ukcMediumM": 2.0, "airDraftLowM": 2.0, "airDraftMediumM": 5.0},
    "aframax": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 1.5, "ukcMediumM": 2.5, "airDraftLowM": 3.0, "airDraftMediumM": 6.0},
    "suezmax": {"windHighKnots": 38, "windMediumKnots": 25, "ukcHighM": 1.8, "ukcMediumM": 3.0, "airDraftLowM": 4.0, "airDraftMediumM": 7.0},
    "vlcc": {"windHighKnots": 35, "windMediumKnots": 22, "ukcHighM": 2.5, "ukcMediumM": 4.0, "airDraftLowM": 5.0, "airDraftMediumM": 10.0},
    "handysize": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 1.0, "ukcMediumM": 2.0, "airDraftLowM": 2.0, "airDraftMediumM": 5.0},
    "panamaxBulk": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 1.5, "ukcMediumM": 2.5, "airDraftLowM": 3.0, "airDraftMediumM": 6.0},
    "capesize": {"windHighKnots": 35, "windMediumKnots": 25, "ukcHighM": 2.0, "ukcMediumM": 3.5, "airDraftLowM": 4.0, "airDraftMediumM": 8.0},
    "pctc": {"windHighKnots": 25, "windMediumKnots": 18, "ukcHighM": 1.5, "ukcMediumM": 2.5, "airDraftLowM": 5.0, "airDraftMediumM": 10.0},
    "lng": {"windHighKnots": 30, "windMediumKnots": 22, "ukcHighM": 2.0, "ukcMediumM": 3.0, "airDraftLowM": 5.0, "airDraftMediumM": 10.0},
}

TIER_SCORES: Dict[RiskTier, float] = {"low": 25.0, "medium": 60.0, "high": 90.0}


class RiskService:
    """Service for computing and aggregating port-call risk."""

    def __init__(
        self,
        weather_client: Optional[MarineWeatherClient] = None,
        ais_client: Optional[AISClient] = None,
        port_svc: Optional[PortService] = None,
    ):
        self.weather_client = weather_client or MarineWeatherClient()
        self.ais_client = ais_client or AISClient()
        self.port_service = port_svc or default_port_service

    def _assess_congestion(self, metrics: PortMetrics) -> SubRiskResult:
        c = metrics.congestion
        factors: List[str] = []

        queue_ratio = (
            c.anchorageQueueCount / c.rolling30dAvgQueue
            if c.rolling30dAvgQueue > 0
            else 1.0
        )
        wait_ratio = (
            c.avgWaitingTimeHours / c.rolling30dAvgWaitHours
            if c.rolling30dAvgWaitHours > 0
            else 1.0
        )

        tier: RiskTier = "low"
        detail = "Normal congestion levels relative to 30-day baseline."

        if queue_ratio >= 1.5 or wait_ratio >= 1.5 or c.berthOccupancyPct >= 90:
            tier = "high"
            detail = "Severe congestion: queue or waiting times significantly above 30-day average."
        elif queue_ratio >= 1.2 or wait_ratio >= 1.2 or c.berthOccupancyPct >= 75:
            tier = "medium"
            detail = "Elevated congestion above rolling baseline."

        if queue_ratio >= 1.2:
            factors.append(
                f"Anchorage queue {c.anchorageQueueCount} vs {c.rolling30dAvgQueue} avg (ratio {queue_ratio:.2f})"
            )
        if wait_ratio >= 1.2:
            factors.append(
                f"Avg wait {c.avgWaitingTimeHours}h vs {c.rolling30dAvgWaitHours}h avg (ratio {wait_ratio:.2f})"
            )
        if c.berthOccupancyPct >= 75:
            factors.append(f"Berth occupancy at {c.berthOccupancyPct}%")

        return SubRiskResult(
            category="congestion",
            tier=tier,
            score=TIER_SCORES[tier],
            detail=detail,
            factors=factors,
        )

    def _assess_terminal_delays(self, metrics: PortMetrics) -> SubRiskResult:
        t = metrics.terminal
        factors: List[str] = []

        turnaround_ratio = (
            t.berthTurnaroundHours / t.rolling30dAvgTurnaround
            if t.rolling30dAvgTurnaround > 0
            else 1.0
        )

        tier: RiskTier = "low"
        detail = "Terminal operations within normal turnaround range."

        if (
            turnaround_ratio >= 1.5
            or t.berthToAnchorageWaitRatio >= 0.7
            or t.dwellTimeAnomalyScore >= 70
        ):
            tier = "high"
            detail = "Significant terminal delays: turnaround or dwell anomalies detected."
        elif (
            turnaround_ratio >= 1.2
            or t.berthToAnchorageWaitRatio >= 0.5
            or t.dwellTimeAnomalyScore >= 40
        ):
            tier = "medium"
            detail = "Terminal delays above baseline trends."

        if turnaround_ratio >= 1.2:
            factors.append(
                f"Turnaround {t.berthTurnaroundHours}h vs {t.rolling30dAvgTurnaround}h avg (ratio {turnaround_ratio:.2f})"
            )
        if t.berthToAnchorageWaitRatio >= 0.5:
            factors.append(f"Berth-to-anchorage wait ratio {t.berthToAnchorageWaitRatio}")
        if t.dwellTimeAnomalyScore >= 40:
            factors.append(f"Dwell anomaly score {t.dwellTimeAnomalyScore}/100")

        return SubRiskResult(
            category="terminalDelays",
            tier=tier,
            score=TIER_SCORES[tier],
            detail=detail,
            factors=factors,
        )

    def _assess_weather(self, metrics: PortMetrics, vessel_class: VesselClass) -> SubRiskResult:
        w = metrics.weather
        th = VESSEL_CLASS_THRESHOLDS.get(vessel_class, VESSEL_CLASS_THRESHOLDS["panamax"])
        factors: List[str] = []

        tier: RiskTier = "low"
        detail = "Weather conditions within safe operating limits."

        effective_wind = max(w.windSpeedKnots, w.gustSpeedKnots * 0.85)

        if (
            effective_wind >= th["windHighKnots"]
            or w.waveHeightM >= 4.0
            or w.visibilityNm <= 0.5
        ):
            tier = "high"
            detail = "Severe weather exceeding PIANC safety limits for this vessel class."
        elif (
            effective_wind >= th["windMediumKnots"]
            or w.waveHeightM >= 2.5
            or w.visibilityNm <= 2.0
        ):
            tier = "medium"
            detail = "Adverse weather approaching operational thresholds."

        if effective_wind >= th["windMediumKnots"]:
            factors.append(
                f"Wind {w.windSpeedKnots}kn, gusts {w.gustSpeedKnots}kn (limit {th['windHighKnots']}kn)"
            )
        if w.waveHeightM >= 2.5:
            factors.append(f"Wave height {w.waveHeightM}m")
        if w.visibilityNm <= 2.0:
            factors.append(f"Visibility {w.visibilityNm}Nm")

        return SubRiskResult(
            category="weather",
            tier=tier,
            score=TIER_SCORES[tier],
            detail=detail,
            factors=factors,
        )

    def _assess_navigational(self, metrics: PortMetrics, vessel_class: VesselClass) -> SubRiskResult:
        n = metrics.navigational
        th = VESSEL_CLASS_THRESHOLDS.get(vessel_class, VESSEL_CLASS_THRESHOLDS["panamax"])
        factors: List[str] = []

        tier: RiskTier = "low"
        detail = "Navigational conditions within safe clearance limits."

        if (
            n.underKeelClearanceM <= th["ukcHighM"]
            or n.airDraftClearanceM <= th["airDraftLowM"]
            or not n.pilotageAvailable
        ):
            tier = "high"
            detail = "Critical navigational constraint: insufficient clearance or pilotage unavailable."
        elif (
            n.underKeelClearanceM <= th["ukcMediumM"]
            or n.airDraftClearanceM <= th["airDraftMediumM"]
        ):
            tier = "medium"
            detail = "Navigational clearances approaching minimum safety margins."

        if n.underKeelClearanceM <= th["ukcMediumM"]:
            factors.append(
                f"UKC {n.underKeelClearanceM}m (minimum {th['ukcHighM']}m)"
            )
        if n.airDraftClearanceM <= th["airDraftMediumM"]:
            factors.append(f"Air draft clearance {n.airDraftClearanceM}m")
        if not n.pilotageAvailable:
            factors.append("Pilotage currently unavailable")

        return SubRiskResult(
            category="navigational",
            tier=tier,
            score=TIER_SCORES[tier],
            detail=detail,
            factors=factors,
        )

    def _compute_composite(self, sub_risks: Dict[SubRiskCategory, SubRiskResult]) -> tuple[RiskTier, float]:
        """Weakest-link rule: highest severity sub-risk dictates composite tier."""
        tiers = [r.tier for r in sub_risks.values()]
        if "high" in tiers:
            return "high", 90.0
        if "medium" in tiers:
            return "medium", 60.0
        return "low", 25.0

    async def get_risk_assessment(
        self,
        port_id: str,
        port_name: Optional[str],
        vessel_class: VesselClass,
        user_id: Optional[str] = None,
    ) -> RiskAssessment:
        """Evaluate real-time risk assessment for a port and vessel class."""
        # Find port to extract lat/lon/locode
        port = None
        try:
            port = await self.port_service.get_port_by_id(port_id, user_id=user_id)
        except Exception:
            pass

        lat = port.lat if port else 51.9
        lon = port.lon if port else 4.4
        locode = port.locode if port else "NLRTM"
        display_name = port_name or (port.name if port else port_id)

        # Call external clients (with their fallback mechanisms)
        weather = await self.weather_client.get_marine_weather(lat, lon, port_id)
        congestion, terminal, navigational = await self.ais_client.get_port_traffic_metrics(
            port_id, locode, vessel_class
        )

        now_str = datetime.now(timezone.utc).isoformat()
        metrics = PortMetrics(
            portId=port_id,
            timestamp=now_str,
            congestion=congestion,
            terminal=terminal,
            weather=weather,
            navigational=navigational,
        )

        sub_risks: Dict[SubRiskCategory, SubRiskResult] = {
            "congestion": self._assess_congestion(metrics),
            "terminalDelays": self._assess_terminal_delays(metrics),
            "weather": self._assess_weather(metrics, vessel_class),
            "navigational": self._assess_navigational(metrics, vessel_class),
        }

        composite_tier, composite_score = self._compute_composite(sub_risks)
        class_info = VESSEL_CLASS_METADATA.get(vessel_class, {"label": vessel_class})

        return RiskAssessment(
            id=f"risk-{port_id}-{vessel_class}-{int(time_seed_now())}",
            portId=port_id,
            portName=display_name,
            vesselClass=vessel_class,
            vesselClassLabel=class_info["label"],
            timestamp=now_str,
            compositeTier=composite_tier,
            compositeScore=composite_score,
            subRisks=sub_risks,
            metrics=metrics,
        )

    async def get_bulk_assessments(
        self, ports: List[PortRef], vessel_class: VesselClass, user_id: Optional[str] = None
    ) -> List[RiskAssessment]:
        """Evaluate risk across multiple ports for dashboard overview."""
        results: List[RiskAssessment] = []
        for p in ports:
            assessment = await self.get_risk_assessment(
                port_id=p.id,
                port_name=p.name,
                vessel_class=vessel_class,
                user_id=user_id,
            )
            results.append(assessment)
        return results

    async def get_historical_trend(
        self,
        port_id: str,
        vessel_class: VesselClass,
        days: int = 7,
        user_id: Optional[str] = None,
    ) -> List[RiskAssessment]:
        """Return chronological 6-hour evaluation cycles for trend charts."""
        days = min(max(days, 1), 30)
        points = min(days * 4, 40)  # 4 cycles per day, max 40 points

        port = None
        try:
            port = await self.port_service.get_port_by_id(port_id, user_id=user_id)
        except Exception:
            pass
        port_name = port.name if port else port_id

        assessments: List[RiskAssessment] = []
        now = datetime.now(timezone.utc)

        for i in range(points - 1, -1, -1):
            ts = now - timedelta(hours=i * 6)
            ts_str = ts.isoformat()
            shifted_port_id = f"{port_id}-{i}"

            weather = await self.weather_client.get_marine_weather(
                port.lat if port else 50.0, port.lon if port else 0.0, shifted_port_id
            )
            congestion, terminal, navigational = await self.ais_client.get_port_traffic_metrics(
                shifted_port_id, port.locode if port else "NLRTM", vessel_class
            )

            metrics = PortMetrics(
                portId=port_id,
                timestamp=ts_str,
                congestion=congestion,
                terminal=terminal,
                weather=weather,
                navigational=navigational,
            )

            sub_risks: Dict[SubRiskCategory, SubRiskResult] = {
                "congestion": self._assess_congestion(metrics),
                "terminalDelays": self._assess_terminal_delays(metrics),
                "weather": self._assess_weather(metrics, vessel_class),
                "navigational": self._assess_navigational(metrics, vessel_class),
            }

            composite_tier, composite_score = self._compute_composite(sub_risks)
            class_info = VESSEL_CLASS_METADATA.get(vessel_class, {"label": vessel_class})

            assessments.append(
                RiskAssessment(
                    id=f"risk-{port_id}-{vessel_class}-{int(ts.timestamp())}",
                    portId=port_id,
                    portName=port_name,
                    vesselClass=vessel_class,
                    vesselClassLabel=class_info["label"],
                    timestamp=ts_str,
                    compositeTier=composite_tier,
                    compositeScore=composite_score,
                    subRisks=sub_risks,
                    metrics=metrics,
                )
            )

        return assessments


def time_seed_now() -> int:
    import time
    return int(time.time())


risk_service = RiskService()
