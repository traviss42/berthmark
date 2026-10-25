"""Weakest-Link Composite Risk Engine and Assessment Service."""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AlertLog, Port, PortRiskSnapshot, UserWatchlist
from backend.schemas.metrics import (
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    SubRiskResult,
    TerminalMetrics,
    WeatherMetrics,
)
from backend.schemas.risk import RiskAssessment, RiskTier, SubRisksDict
from backend.services.baseline import TrafficBaselineRepository
from backend.services.congestion import assess_congestion_risk, calculate_queue_variance
from backend.services.navigational import calculate_navigational_metrics
from backend.services.port_metrics import assemble_port_metrics
from backend.services.terminal import calculate_terminal_metrics, evaluate_terminal_delays
from backend.services.weather import compute_weather_risk

logger = logging.getLogger(__name__)

VALID_VESSEL_CLASSES: set[str] = {
    "feeder",
    "panamax",
    "neoPanamax",
    "ulcv",
    "mrTanker",
    "aframax",
    "suezmax",
    "vlcc",
    "handysize",
    "panamaxBulk",
    "capesize",
    "pctc",
    "lng",
}

VESSEL_CLASS_LABELS: dict[str, str] = {
    "feeder": "Feeder",
    "panamax": "Panamax / Sub-Panamax",
    "neoPanamax": "Neo-Panamax",
    "ulcv": "ULCV (Ultra Large)",
    "mrTanker": "MR Tanker",
    "aframax": "Aframax",
    "suezmax": "Suezmax",
    "vlcc": "VLCC",
    "handysize": "Handysize",
    "panamaxBulk": "Panamax (Bulk)",
    "capesize": "Capesize",
    "pctc": "PCTC",
    "lng": "LNG Carrier",
}

TIER_ORDER: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

TIER_SCORES: dict[str, float] = {
    "low": 25.0,
    "medium": 60.0,
    "high": 90.0,
}


def determine_composite_tier(
    sub_risks: dict[str, SubRiskResult] | SubRisksDict,
) -> tuple[RiskTier, float]:
    """Calculate the weakest-link composite tier and maximum composite score.

    Weakest-Link rule:
    - If ANY sub-risk is 'high', composite tier is immediately 'high'.
    - Else if ANY sub-risk is 'medium', composite tier is 'medium'.
    - Else composite tier is 'low'.

    compositeScore is the maximum score among all four sub-risks, bounded between 0.0 and 100.0,
    and rounded to 1 decimal place.
    """
    if isinstance(sub_risks, SubRisksDict):
        results = [
            sub_risks.congestion,
            sub_risks.terminalDelays,
            sub_risks.weather,
            sub_risks.navigational,
        ]
    elif isinstance(sub_risks, dict):
        results = list(sub_risks.values())
    else:
        raise ValueError(f"Unsupported sub_risks type: {type(sub_risks)}")

    tiers = [r.tier.lower() for r in results]
    scores = [r.score for r in results]

    if any(t == "high" for t in tiers):
        composite_tier: RiskTier = "high"
    elif any(t == "medium" for t in tiers):
        composite_tier = "medium"
    else:
        composite_tier = "low"

    composite_score = round(min(100.0, max(0.0, max(scores))), 1)
    return composite_tier, composite_score


def evaluate_weather_risk(metrics: WeatherMetrics) -> SubRiskResult:
    """Evaluate atmospheric and marine weather risk into a structured SubRiskResult."""
    raw_tier = compute_weather_risk(metrics).lower()
    score = TIER_SCORES.get(raw_tier, 25.0)

    factors: list[str] = []
    if metrics.waveHeightM > 2.5:
        factors.append(f"Significant wave height {metrics.waveHeightM:.1f}m exceeds severe threshold (2.5m)")
    elif metrics.waveHeightM >= 1.5:
        factors.append(f"Significant wave height {metrics.waveHeightM:.1f}m exceeds moderate threshold (1.5m)")

    if metrics.windSpeedKnots > 30.0:
        factors.append(f"Sustained wind speed {metrics.windSpeedKnots:.1f} kts exceeds severe threshold (30 kts)")
    elif metrics.windSpeedKnots > 20.0:
        factors.append(f"Sustained wind speed {metrics.windSpeedKnots:.1f} kts exceeds moderate threshold (20 kts)")

    if metrics.gustSpeedKnots > 40.0:
        factors.append(f"Peak wind gusts {metrics.gustSpeedKnots:.1f} kts exceed severe threshold (40 kts)")
    elif metrics.gustSpeedKnots > 28.0:
        factors.append(f"Peak wind gusts {metrics.gustSpeedKnots:.1f} kts exceed moderate threshold (28 kts)")

    if not factors:
        factors.append("Atmospheric and marine swell conditions within safe operational margins.")

    if raw_tier == "high":
        detail = (
            f"Severe marine weather: wave height {metrics.waveHeightM:.1f}m, "
            f"wind {metrics.windSpeedKnots:.1f} kts, gusts {metrics.gustSpeedKnots:.1f} kts."
        )
    elif raw_tier == "medium":
        detail = (
            f"Moderate marine weather: wave height {metrics.waveHeightM:.1f}m, "
            f"wind {metrics.windSpeedKnots:.1f} kts."
        )
    else:
        detail = (
            f"Favorable weather conditions: wave height {metrics.waveHeightM:.1f}m, "
            f"wind {metrics.windSpeedKnots:.1f} kts."
        )

    return SubRiskResult(
        category="weather",
        tier=raw_tier,  # type: ignore[arg-type]
        score=score,
        detail=detail,
        factors=factors,
    )


def assemble_risk_assessment(
    port_id: str,
    port_name: str,
    vessel_class: str,
    sub_risks: SubRisksDict,
    metrics: PortMetrics,
    timestamp: datetime | None = None,
) -> RiskAssessment:
    """Pure assembly of RiskAssessment payload conforming to OpenAPI schema."""
    if vessel_class not in VALID_VESSEL_CLASSES:
        raise ValueError(f"Invalid vesselClass '{vessel_class}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}")

    ts = timestamp if timestamp is not None else datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assessment_id = f"risk-{port_id}-{vessel_class}-{ts_str}"
    vessel_label = VESSEL_CLASS_LABELS.get(vessel_class, vessel_class)

    composite_tier, composite_score = determine_composite_tier(sub_risks)

    return RiskAssessment(
        id=assessment_id,
        portId=port_id,
        portName=port_name,
        vesselClass=vessel_class,
        vesselClassLabel=vessel_label,
        timestamp=ts,
        compositeTier=composite_tier,
        compositeScore=composite_score,
        subRisks=sub_risks,
        metrics=metrics,
    )


async def persist_risk_assessment(
    session: AsyncSession,
    port: Port,
    vessel_class: str,
    composite_tier: RiskTier,
    sub_risks: SubRisksDict,
    metrics: PortMetrics,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> tuple[PortRiskSnapshot, list[AlertLog]]:
    """Persist port risk snapshot and record state-change alert logs within an atomic transaction block."""
    eval_time = now if now is not None else datetime.now(timezone.utc)
    if eval_time.tzinfo is None:
        eval_time = eval_time.replace(tzinfo=timezone.utc)

    # 1. Retrieve previous snapshot to detect risk level state transition
    prev_stmt = (
        select(PortRiskSnapshot)
        .where(
            PortRiskSnapshot.unlocode == port.unlocode,
            PortRiskSnapshot.vessel_class_id == vessel_class,
        )
        .order_by(PortRiskSnapshot.updated_at.desc())
        .limit(1)
    )
    prev_res = await session.execute(prev_stmt)
    prev_snapshot = prev_res.scalar_one_or_none()
    previous_risk_level = prev_snapshot.overall_risk_level if prev_snapshot else None
    new_risk_level = composite_tier.upper()

    state_changed = previous_risk_level != new_risk_level

    # 2. Build target user list for alert logging if state transitioned
    alerts: list[AlertLog] = []
    if state_changed:
        watch_stmt = select(UserWatchlist.user_id).where(
            UserWatchlist.unlocode == port.unlocode,
            UserWatchlist.vessel_class_id == vessel_class,
        )
        watch_res = await session.execute(watch_stmt)
        target_user_ids = set(watch_res.scalars().all())
        if user_id:
            target_user_ids.add(user_id)

        vessel_label = VESSEL_CLASS_LABELS.get(vessel_class, vessel_class)
        # Collect contributing high/medium factors
        active_factors = []
        for sr in [sub_risks.congestion, sub_risks.terminalDelays, sub_risks.weather, sub_risks.navigational]:
            if sr.tier.upper() == new_risk_level:
                active_factors.extend(sr.factors)

        reason = (
            f"Overall risk tier changed from {previous_risk_level or 'NONE'} to {new_risk_level} "
            f"for {vessel_label}. " + "; ".join(active_factors[:2])
        )

        for uid in target_user_ids:
            alerts.append(
                AlertLog(
                    alert_id=uuid.uuid4(),
                    user_id=uid,
                    unlocode=port.unlocode,
                    vessel_class_id=vessel_class,
                    previous_risk_level=previous_risk_level,
                    new_risk_level=new_risk_level,
                    trigger_reason=reason,
                    created_at=eval_time,
                )
            )

    # 3. Build snapshot record
    underway_count = 0
    anchored_count = metrics.congestion.anchorageQueueCount
    hist_avg = metrics.congestion.rolling30dAvgQueue
    variance_pct = calculate_queue_variance(anchored_count, hist_avg)

    snapshot = PortRiskSnapshot(
        snapshot_id=uuid.uuid4(),
        unlocode=port.unlocode,
        vessel_class_id=vessel_class,
        grounding_risk_level=sub_risks.navigational.tier.upper(),
        anchored_vessel_count=anchored_count,
        underway_vessel_count=underway_count,
        total_active_geofence_count=anchored_count + underway_count,
        historical_avg_queue=hist_avg,
        queue_variance_pct=variance_pct,
        congestion_risk_level=sub_risks.congestion.tier.upper(),
        weather_risk_level=sub_risks.weather.tier.upper(),
        overall_risk_level=new_risk_level,
        swell_height_m=metrics.weather.waveHeightM,
        wind_speed_kts=metrics.weather.windSpeedKnots,
        updated_at=eval_time,
    )

    # 4. Atomic transaction block
    if session.in_transaction():
        async with session.begin_nested():
            session.add(snapshot)
            for alert in alerts:
                session.add(alert)
            await session.flush()
    else:
        async with session.begin():
            session.add(snapshot)
            for alert in alerts:
                session.add(alert)
            await session.flush()

    return snapshot, alerts


async def calculate_port_risk(
    session: AsyncSession,
    port: Port,
    vessel_class: str,
    port_id: str | None = None,
    port_name: str | None = None,
    weather_override: WeatherMetrics | None = None,
    anchored_count_override: int | None = None,
    underway_count_override: int | None = None,
    user_id: uuid.UUID | None = None,
    timestamp: datetime | None = None,
    persist: bool = True,
) -> RiskAssessment:
    """Full end-to-end operational risk assessment pipeline for a single port and vessel class."""
    if vessel_class not in VALID_VESSEL_CLASSES:
        raise ValueError(f"Invalid vesselClass '{vessel_class}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}")

    ts = timestamp if timestamp is not None else datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    canonical_port_id = port_id or f"port-{port.unlocode.lower()}"
    canonical_port_name = port_name or port.port_name

    # 1. Weather domain
    if weather_override is not None:
        weather_metrics = weather_override
    else:
        # Default safe weather metrics for cold start / offline resilience
        weather_metrics = WeatherMetrics(
            windSpeedKnots=12.0,
            waveHeightM=0.8,
            swellPeriodSec=6.0,
            visibilityNm=10.0,
            gustSpeedKnots=15.0,
        )
    weather_subrisk = evaluate_weather_risk(weather_metrics)

    # 2. Congestion domain
    baseline = await TrafficBaselineRepository.get_current_baseline(session, port.unlocode, ts)
    hist_avg = baseline.avg_anchored_count if baseline else None

    # Fetch live counts from override, latest snapshot, or default
    if anchored_count_override is not None:
        anchored_count = anchored_count_override
        underway_count = underway_count_override if underway_count_override is not None else 0
    else:
        snap_stmt = (
            select(PortRiskSnapshot)
            .where(PortRiskSnapshot.unlocode == port.unlocode)
            .order_by(PortRiskSnapshot.updated_at.desc())
            .limit(1)
        )
        snap_res = await session.execute(snap_stmt)
        snap = snap_res.scalar_one_or_none()
        if snap:
            anchored_count = snap.anchored_vessel_count
            underway_count = snap.underway_vessel_count
        else:
            anchored_count = int(hist_avg) if hist_avg is not None else 3
            underway_count = 2

    congestion_assessment = assess_congestion_risk(
        anchored_count=anchored_count,
        hist_avg_anchored=hist_avg,
        underway_count=underway_count,
    )
    congestion_subrisk = SubRiskResult(**congestion_assessment.to_subrisk_result())
    congestion_metrics = CongestionMetrics(**congestion_assessment.to_congestion_metrics())

    # 3. Terminal domain
    # Use standard benchmark values adjusted for congestion
    base_turnaround = 24.0
    rolling_turnaround = 22.0
    if congestion_subrisk.tier == "high":
        base_turnaround = 50.0
    elif congestion_subrisk.tier == "medium":
        base_turnaround = 32.0

    terminal_metrics = calculate_terminal_metrics(
        berth_turnaround_hours=base_turnaround,
        avg_waiting_time_hours=congestion_metrics.avgWaitingTimeHours,
        rolling_30d_avg_turnaround=rolling_turnaround,
    )
    terminal_subrisk = evaluate_terminal_delays(terminal_metrics)

    # 4. Navigational domain
    nav_metrics, nav_subrisk = calculate_navigational_metrics(
        vessel_class=vessel_class,
        channel_depth_m=port.channel_depth_m,
        wave_height_m=weather_metrics.waveHeightM,
        wind_speed_knots=weather_metrics.windSpeedKnots,
    )

    # 5. Assemble unified subrisks & metrics
    sub_risks = SubRisksDict(
        congestion=congestion_subrisk,
        terminalDelays=terminal_subrisk,
        weather=weather_subrisk,
        navigational=nav_subrisk,
    )

    unified_metrics = assemble_port_metrics(
        port_id=canonical_port_id,
        congestion=congestion_metrics,
        terminal=terminal_metrics,
        weather=weather_metrics,
        navigational=nav_metrics,
        timestamp=ts,
    )

    assessment = assemble_risk_assessment(
        port_id=canonical_port_id,
        port_name=canonical_port_name,
        vessel_class=vessel_class,
        sub_risks=sub_risks,
        metrics=unified_metrics,
        timestamp=ts,
    )

    # 6. Atomic persistence of snapshot & alerts
    if persist:
        await persist_risk_assessment(
            session=session,
            port=port,
            vessel_class=vessel_class,
            composite_tier=assessment.compositeTier,
            sub_risks=sub_risks,
            metrics=unified_metrics,
            user_id=user_id,
            now=ts,
        )

    return assessment
