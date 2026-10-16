"""Risk evaluation service implementing multi-factor scoring and the weakest-link composite rule."""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
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
    "feeder": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 0.5, "ukcMediumM": 1.5},
    "panamax": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 0.8, "ukcMediumM": 2.0},
    "neoPanamax": {"windHighKnots": 35, "windMediumKnots": 25, "ukcHighM": 1.0, "ukcMediumM": 2.5},
    "ulcv": {"windHighKnots": 28, "windMediumKnots": 20, "ukcHighM": 1.5, "ukcMediumM": 3.0},
    "mrTanker": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 0.5, "ukcMediumM": 1.5},
    "aframax": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 1.0, "ukcMediumM": 2.0},
    "suezmax": {"windHighKnots": 38, "windMediumKnots": 25, "ukcHighM": 1.2, "ukcMediumM": 2.5},
    "vlcc": {"windHighKnots": 35, "windMediumKnots": 22, "ukcHighM": 1.8, "ukcMediumM": 3.5},
    "handysize": {"windHighKnots": 45, "windMediumKnots": 30, "ukcHighM": 0.5, "ukcMediumM": 1.5},
    "panamaxBulk": {"windHighKnots": 40, "windMediumKnots": 28, "ukcHighM": 1.0, "ukcMediumM": 2.0},
    "capesize": {"windHighKnots": 35, "windMediumKnots": 25, "ukcHighM": 1.5, "ukcMediumM": 3.0},
    "pctc": {"windHighKnots": 25, "windMediumKnots": 18, "ukcHighM": 1.0, "ukcMediumM": 2.0},
    "lng": {"windHighKnots": 30, "windMediumKnots": 22, "ukcHighM": 1.2, "ukcMediumM": 2.5},
}

TIER_SCORES: Dict[RiskTier, float] = {"low": 25.0, "medium": 60.0, "high": 90.0}


class RiskService:
    """Service for computing and aggregating port-call risk across live traffic, weather, and NGA WPI hydrography."""

    def __init__(
        self,
        weather_client: Optional[MarineWeatherClient] = None,
        ais_client: Optional[AISClient] = None,
        port_svc: Optional[PortService] = None,
    ):
        self.weather_client = weather_client or MarineWeatherClient()
        self.ais_client = ais_client or AISClient()
        self.port_service = port_svc or default_port_service
        self._assessment_cache: Dict[str, Tuple[float, RiskAssessment]] = {}
        self._trend_cache: Dict[str, Tuple[float, List[RiskAssessment]]] = {}
        self.cache_ttl_seconds: float = 300.0  # 5 minutes TTL

    def _assess_congestion(self, metrics: PortMetrics) -> SubRiskResult:
        c = metrics.congestion
        factors: List[str] = []

        queue_ratio = (
            c.anchorageQueueCount / c.rolling30dAvgQueue
            if c.rolling30dAvgQueue > 0
            else 1.0
        )

        tier: RiskTier = "low"
        detail = "Normal vessel traffic relative to rolling historical baseline."

        if queue_ratio >= 1.5 or c.anchorageQueueCount >= 25:
            tier = "high"
            detail = "Severe anchorage congestion: stationary/anchored vessel queue significantly above baseline."
        elif queue_ratio >= 1.2 or c.anchorageQueueCount >= 12:
            tier = "medium"
            detail = "Elevated vessel queue above rolling baseline."

        if queue_ratio >= 1.2:
            factors.append(
                f"Anchored/stationary queue {c.anchorageQueueCount} vs {c.rolling30dAvgQueue} avg (ratio {queue_ratio:.2f})"
            )
        if c.anchorageQueueCount >= 12:
            factors.append(f"{c.anchorageQueueCount} stationary/anchored vessels in port geofence")
        if c.activeVesselCount > 0:
            factors.append(f"{c.activeVesselCount} total active vessels ({c.movingVesselCount} underway)")

        return SubRiskResult(
            category="congestion",
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
        detail = "Navigational and NGA WPI depth clearances within safe operating limits."

        high_air_draft_class = vessel_class in ("ulcv", "neoPanamax", "pctc", "lng", "vlcc")
        has_overhead_constraint = n.overheadLimits == "Yes" and high_air_draft_class

        if n.underKeelClearanceM <= th["ukcHighM"] or not n.pilotageAvailable:
            tier = "high"
            detail = "Critical navigational constraint: insufficient under-keel clearance or pilotage unavailable."
        elif (
            n.underKeelClearanceM <= th["ukcMediumM"]
            or has_overhead_constraint
            or not n.tugsAssistance
        ):
            tier = "medium"
            detail = "Navigational clearances or port infrastructure approaching safety margins."

        if n.underKeelClearanceM <= th["ukcMediumM"]:
            factors.append(
                f"UKC {n.underKeelClearanceM}m (Channel {n.channelDepthM}m vs Draft {n.vesselDraftM}m, min margin {th['ukcHighM']}m)"
            )
        if has_overhead_constraint:
            factors.append("Overhead bridge/cable limits reported in NGA World Port Index")
        if not n.pilotageAvailable:
            factors.append("Pilotage unavailable in NGA World Port Index")
        if not n.tugsAssistance:
            factors.append("Tug assistance unavailable in NGA World Port Index")

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
        port_name: Optional[str] = None,
        vessel_class: VesselClass = "neoPanamax",
        user_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> RiskAssessment:
        """Evaluate real-time risk assessment for a port and vessel class with TTL caching."""
        cache_key = f"{port_id}:{vessel_class}"
        now_time = time.time()

        if not force_refresh and cache_key in self._assessment_cache:
            cached_time, cached_assessment = self._assessment_cache[cache_key]
            if now_time - cached_time < self.cache_ttl_seconds:
                return cached_assessment

        port = await self.port_service.get_port_by_id(port_id, user_id=user_id)
        lat = port.lat
        lon = port.lon
        locode = port.locode
        display_name = port_name or port.name
        radius = port.geofenceRadiusNm

        weather = await self.weather_client.get_marine_weather(
            lat, lon, port_id, force_refresh=force_refresh
        )
        congestion, navigational = await self.ais_client.get_port_traffic_metrics(
            port_id,
            locode,
            vessel_class,
            lat=lat,
            lon=lon,
            geofence_radius_nm=radius,
            force_refresh=force_refresh,
        )

        now_str = datetime.now(timezone.utc).isoformat()
        metrics = PortMetrics(
            portId=port_id,
            timestamp=now_str,
            congestion=congestion,
            weather=weather,
            navigational=navigational,
        )

        sub_risks: Dict[SubRiskCategory, SubRiskResult] = {
            "congestion": self._assess_congestion(metrics),
            "weather": self._assess_weather(metrics, vessel_class),
            "navigational": self._assess_navigational(metrics, vessel_class),
        }

        composite_tier, composite_score = self._compute_composite(sub_risks)
        class_info = VESSEL_CLASS_METADATA.get(vessel_class, {"label": vessel_class})

        assessment = RiskAssessment(
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

        self._assessment_cache[cache_key] = (now_time, assessment)
        return assessment

    async def get_bulk_assessments(
        self,
        ports: List[PortRef],
        vessel_class: VesselClass,
        user_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[RiskAssessment]:
        """Evaluate risk across multiple ports with caching."""
        results: List[RiskAssessment] = []
        for p in ports:
            assessment = await self.get_risk_assessment(
                port_id=p.id,
                port_name=p.name,
                vessel_class=vessel_class,
                user_id=user_id,
                force_refresh=force_refresh,
            )
            results.append(assessment)
        return results

    async def get_historical_trend(
        self,
        port_id: str,
        vessel_class: VesselClass,
        days: int = 7,
        user_id: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[RiskAssessment]:
        """Return chronological 6-hour evaluation cycles for trend charts with caching."""
        days = min(max(days, 1), 30)
        cache_key = f"{port_id}:{vessel_class}:{days}"
        now_time = time.time()

        if not force_refresh and cache_key in self._trend_cache:
            cached_time, cached_trend = self._trend_cache[cache_key]
            if now_time - cached_time < self.cache_ttl_seconds:
                return cached_trend

        points = min(days * 4, 40)  # 4 cycles per day, max 40 points

        port = await self.port_service.get_port_by_id(port_id, user_id=user_id)
        port_name = port.name
        lat = port.lat
        lon = port.lon
        locode = port.locode
        radius = port.geofenceRadiusNm

        base_weather = await self.weather_client.get_marine_weather(
            lat, lon, port_id, force_refresh=force_refresh
        )
        base_congestion, base_navigational = (
            await self.ais_client.get_port_traffic_metrics(
                port_id,
                locode,
                vessel_class,
                lat=lat,
                lon=lon,
                geofence_radius_nm=radius,
                force_refresh=force_refresh,
            )
        )

        assessments: List[RiskAssessment] = []
        now = datetime.now(timezone.utc)
        class_info = VESSEL_CLASS_METADATA.get(vessel_class, {"label": vessel_class})

        for i in range(points - 1, -1, -1):
            ts = now - timedelta(hours=i * 6)
            ts_str = ts.isoformat()

            metrics = PortMetrics(
                portId=port_id,
                timestamp=ts_str,
                congestion=base_congestion,
                weather=base_weather,
                navigational=base_navigational,
            )

            sub_risks: Dict[SubRiskCategory, SubRiskResult] = {
                "congestion": self._assess_congestion(metrics),
                "weather": self._assess_weather(metrics, vessel_class),
                "navigational": self._assess_navigational(metrics, vessel_class),
            }

            composite_tier, composite_score = self._compute_composite(sub_risks)

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

        self._trend_cache[cache_key] = (now_time, assessments)
        return assessments


def time_seed_now() -> int:
    import time
    return int(time.time())


risk_service = RiskService()

