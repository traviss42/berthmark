"""Weakest-Link Composite Risk Engine and Assessment Service."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import AlertLog, Port, PortRiskSnapshot, PortTrafficBaseline, UserWatchlist
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.schemas.metrics import (
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    SubRiskResult,
    WeatherMetrics,
)
from backend.schemas.recommendation import AlternativePortRecommendation
from backend.schemas.risk import BulkRiskPortItem, RiskAssessment, RiskTier, SubRisksDict
from backend.services.congestion import (
    assess_congestion_risk,
    calculate_queue_variance,
    get_port_traffic_baseline,
    get_rolling_congestion_baseline,
)
from backend.services.navigational import calculate_navigational_metrics
from backend.services.port_metrics import assemble_port_metrics
from backend.services.recommendation import (
    batch_recommend_alternative_ports,
    recommend_alternative_ports,
)
from backend.services.weather import compute_weather_risk, fetch_tide_offset

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
    "handymax",
    "newPanamax",
    "ulcs",
    "panamaxBulk",
    "capesize",
    "pctc",
    "lng",
}

VESSEL_CLASS_LABELS: dict[str, str] = {
    "feeder": "Feeder",
    "panamax": "Panamax / Sub-Panamax",
    "neoPanamax": "Neo-Panamax",
    "newPanamax": "New Panamax",
    "ulcv": "ULCV (Ultra Large)",
    "ulcs": "ULCS",
    "mrTanker": "MR Tanker",
    "aframax": "Aframax",
    "suezmax": "Suezmax",
    "vlcc": "VLCC",
    "handysize": "Handysize",
    "handymax": "Handymax / Supramax",
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

    compositeScore is the maximum score among all sub-risks, bounded between 0.0 and 100.0,
    and rounded to 1 decimal place.
    """
    if isinstance(sub_risks, SubRisksDict):
        results = [
            sub_risks.congestion,
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
    alternatives: list[AlternativePortRecommendation] | None = None,
    is_cold_start: bool | None = None,
    is_initializing: bool | None = None,
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

    cold_start = is_cold_start if is_cold_start is not None else bool(getattr(metrics.congestion, "isColdStart", False))
    initializing = is_initializing if is_initializing is not None else bool(getattr(metrics.congestion, "isInitializing", False))

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
        isColdStart=cold_start,
        isInitializing=initializing,
        alternatives=alternatives or [],
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
        for sr in [sub_risks.congestion, sub_risks.weather, sub_risks.navigational]:
            if sr.tier.upper() == new_risk_level:
                active_factors.extend(sr.factors)

        reason = (
            f"Overall risk tier changed from {previous_risk_level or 'NONE'} to {new_risk_level} "
            f"for {vessel_label}. " + "; ".join(active_factors[:2])
        )

        title = f"{port.port_name}: Risk tier changed to {new_risk_level.capitalize()}"
        for uid in target_user_ids:
            alerts.append(
                AlertLog(
                    alert_id=uuid.uuid4(),
                    user_id=uid,
                    unlocode=port.unlocode,
                    vessel_class_id=vessel_class,
                    type="stateChange",
                    title=title,
                    message=reason,
                    previous_risk_level=previous_risk_level,
                    new_risk_level=new_risk_level,
                    trigger_reason=reason,
                    is_read=False,
                    created_at=eval_time,
                )
            )

    # 3. Build snapshot record
    underway_count = metrics.congestion.underwayCount or 0
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
        historical_avg_queue=hist_avg if hist_avg is not None else 0.0,
        queue_variance_pct=variance_pct if variance_pct is not None else 0.0,
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
    tide_offset_override: float | None = None,
    tide_data_available_override: bool | None = None,
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
    hist_avg, days_collected = await get_rolling_congestion_baseline(session, port.unlocode, ts)

    # Fetch live counts from override, latest snapshot, or default
    if anchored_count_override is not None:
        anchored_count = anchored_count_override
        underway_count = underway_count_override if underway_count_override is not None else 0
        is_initializing = False
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
            is_initializing = False
        else:
            w_stmt = select(func.min(UserWatchlist.created_at)).where(
                UserWatchlist.unlocode == port.unlocode
            )
            w_res = await session.execute(w_stmt)
            first_watched = w_res.scalar_one_or_none()
            now_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            if first_watched is not None:
                if first_watched.tzinfo is None:
                    first_watched = first_watched.replace(tzinfo=timezone.utc)
                age_minutes = (now_utc - first_watched).total_seconds() / 60.0
            else:
                age_minutes = 999.0

            if age_minutes < 15.0:
                anchored_count = None
                underway_count = 0
                is_initializing = True
            else:
                anchored_count = int(hist_avg) if hist_avg is not None else 0
                underway_count = 0
                is_initializing = False

    if not is_initializing and anchored_count is not None and hist_avg is None:
        hist_avg = float(anchored_count)
        days_collected = 1

    congestion_assessment = assess_congestion_risk(
        anchored_count=anchored_count,
        hist_avg_anchored=hist_avg,
        underway_count=underway_count,
        is_initializing=is_initializing,
        baseline_days_collected=days_collected,
    )
    congestion_subrisk = SubRiskResult(**congestion_assessment.to_subrisk_result())
    congestion_metrics = CongestionMetrics(**congestion_assessment.to_congestion_metrics())

    # 3. Navigational domain (incorporating dynamic tide offset)
    if tide_offset_override is not None:
        tide_offset_m = float(tide_offset_override)
        tide_data_available = (
            tide_data_available_override
            if tide_data_available_override is not None
            else True
        )
    elif port.latitude is not None and port.longitude is not None:
        try:
            tide_res = await fetch_tide_offset(port.latitude, port.longitude)
            tide_offset_m = tide_res.tide_offset_m
            tide_data_available = tide_res.tide_data_available
        except Exception as exc:
            logger.warning(
                "Tide offset fetch failed for port %s (%s, %s): %s; defaulting to 0.0m baseline",
                port.unlocode,
                port.latitude,
                port.longitude,
                exc,
            )
            tide_offset_m = 0.0
            tide_data_available = False
    else:
        tide_offset_m = 0.0
        tide_data_available = False

    nav_metrics, nav_subrisk = calculate_navigational_metrics(
        vessel_class=vessel_class,
        channel_depth_m=port.channel_depth_m,
        wave_height_m=weather_metrics.waveHeightM,
        wind_speed_knots=weather_metrics.windSpeedKnots,
        tide_height_m=tide_offset_m,
        tide_data_available=tide_data_available,
    )

    # 4. Assemble unified subrisks & metrics
    sub_risks = SubRisksDict(
        congestion=congestion_subrisk,
        weather=weather_subrisk,
        navigational=nav_subrisk,
    )

    unified_metrics = assemble_port_metrics(
        port_id=canonical_port_id,
        congestion=congestion_metrics,
        weather=weather_metrics,
        navigational=nav_metrics,
        timestamp=ts,
    )

    # 5. Composite tier & Alternative port recommendations
    composite_tier, composite_score = determine_composite_tier(sub_risks)
    alternatives: list[AlternativePortRecommendation] = []
    if composite_tier in ("high", "critical"):
        try:
            alternatives = await recommend_alternative_ports(
                session=session,
                primary_port=port,
                vessel_class=vessel_class,
                primary_risk_tier=composite_tier.upper(),
                wave_height_m=weather_metrics.waveHeightM,
            )
        except Exception as exc:
            logger.warning("Failed to evaluate alternative ports for %s: %s", port.unlocode, exc)

    assessment = assemble_risk_assessment(
        port_id=canonical_port_id,
        port_name=canonical_port_name,
        vessel_class=vessel_class,
        sub_risks=sub_risks,
        metrics=unified_metrics,
        timestamp=ts,
        alternatives=alternatives,
        is_cold_start=congestion_metrics.isColdStart,
        is_initializing=congestion_metrics.isInitializing,
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


async def calculate_bulk_risk(
    session: AsyncSession,
    items: list[BulkRiskPortItem],
    vessel_class: str,
    timestamp: datetime | None = None,
    include_alternatives: bool = True,
) -> list[RiskAssessment]:
    """Concurrent, high-performance bulk risk evaluation with O(1) batched database queries."""
    if vessel_class not in VALID_VESSEL_CLASSES:
        raise ValueError(f"Invalid vesselClass '{vessel_class}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}")

    if not items:
        return []

    ts = timestamp if timestamp is not None else datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    # 0. Batch-resolve any user watchlist item IDs: port-user-<watchlist_uuid>
    user_watchlist_ids: list[uuid.UUID] = []
    user_id_map: dict[str, uuid.UUID] = {}
    for item in items:
        cid = item.id.strip()
        if cid.lower().startswith("port-user-"):
            try:
                w_uuid = uuid.UUID(cid[10:])
                user_watchlist_ids.append(w_uuid)
                user_id_map[cid] = w_uuid
            except ValueError:
                pass

    user_watchlist_locodes: dict[uuid.UUID, str] = {}
    if user_watchlist_ids:
        uw_stmt = select(UserWatchlist).where(UserWatchlist.watchlist_id.in_(user_watchlist_ids))
        uw_res = await session.execute(uw_stmt)
        for uw in uw_res.scalars().all():
            user_watchlist_locodes[uw.watchlist_id] = uw.unlocode.upper()

    # 1. Deduplicate requested ports by resolved LOCODE / port ID
    unique_items: list[BulkRiskPortItem] = []
    seen_keys: set[str] = set()
    candidate_locodes: dict[str, str] = {}  # clean_id -> locode
    target_locodes_set: set[str] = set()

    for item in items:
        clean_id = item.id.strip()
        locode_match = None
        if clean_id in user_id_map and user_id_map[clean_id] in user_watchlist_locodes:
            locode_match = user_watchlist_locodes[user_id_map[clean_id]]
        else:
            for locode, meta in BENCHMARK_PORTS_METADATA.items():
                if meta["id"].lower() == clean_id.lower() or locode.lower() == clean_id.lower():
                    locode_match = locode.upper()
                    break
            if not locode_match:
                locode_match = clean_id[5:].upper() if clean_id.lower().startswith("port-") else clean_id.upper()

        dedup_key = clean_id if clean_id.lower().startswith("port-user-") else locode_match
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            unique_items.append(item)
            candidate_locodes[clean_id] = locode_match
            if locode_match:
                target_locodes_set.add(locode_match)

    # 3. Query all candidate ports in ONE batched query
    ports_stmt = select(Port).where(func.upper(Port.unlocode).in_([l.upper() for l in target_locodes_set]))
    ports_res = await session.execute(ports_stmt)
    found_ports = list(ports_res.scalars().all())
    ports_by_locode: dict[str, Port] = {p.unlocode.upper(): p for p in found_ports}

    # Auto-seed any missing benchmark ports
    benchmark_added = False
    for item in unique_items:
        clean_id = item.id.strip()
        for locode, meta in BENCHMARK_PORTS_METADATA.items():
            if (meta["id"].lower() == clean_id.lower() or locode.lower() == clean_id.lower()) and locode.upper() not in ports_by_locode:
                p = Port(
                    unlocode=meta["locode"],
                    port_name=meta["name"],
                    country_code=meta["country"],
                    subdivision_code=meta["subdivision"],
                    latitude=meta["lat"],
                    longitude=meta["lon"],
                    wpi_number=meta.get("wpiNumber"),
                    channel_depth_m=meta.get("channelDepthM"),
                    cargo_pier_depth_m=meta.get("pierDepthM"),
                    anchorage_depth_m=meta.get("anchorageDepthM"),
                    is_depth_available=meta.get("channelDepthM") is not None,
                    reconciliation_method="EXACT_UNLOCODE",
                )
                session.add(p)
                found_ports.append(p)
                ports_by_locode[locode.upper()] = p
                benchmark_added = True

    if benchmark_added:
        await session.flush()

    # Match items to resolved Port entities
    resolved_pairs: list[tuple[BulkRiskPortItem, Port]] = []
    for item in unique_items:
        locode = candidate_locodes.get(item.id.strip())
        if locode and locode in ports_by_locode:
            resolved_pairs.append((item, ports_by_locode[locode]))

    if not resolved_pairs:
        return []

    locode_keys = list({p.unlocode.upper() for _, p in resolved_pairs})

    # 4. Query baselines in ONE batched query
    day_of_week = (ts.weekday() + 1) % 7
    hour_of_day = ts.hour
    baseline_stmt = select(PortTrafficBaseline).where(
        PortTrafficBaseline.unlocode.in_(locode_keys),
    )
    b_res = await session.execute(baseline_stmt)
    all_baselines = b_res.scalars().all()
    baselines_by_slot: dict[tuple[str, int, int], PortTrafficBaseline] = {}
    baselines_by_locode: dict[str, PortTrafficBaseline] = {}
    for b in all_baselines:
        loc = b.unlocode.upper()
        baselines_by_slot[(loc, b.day_of_week, b.hour_of_day)] = b
        if loc not in baselines_by_locode:
            baselines_by_locode[loc] = b

    # 5. Query snapshots in ONE batched query using selectinload eager loading
    snap_stmt = (
        select(PortRiskSnapshot)
        .options(
            selectinload(PortRiskSnapshot.port),
            selectinload(PortRiskSnapshot.vessel_class),
        )
        .where(
            PortRiskSnapshot.unlocode.in_(locode_keys),
        )
        .order_by(PortRiskSnapshot.updated_at.desc())
    )
    s_res = await session.execute(snap_stmt)
    snapshots_by_pair: dict[tuple[str, str], PortRiskSnapshot] = {}
    snapshots_by_locode: dict[str, PortRiskSnapshot] = {}
    for s in s_res.scalars().all():
        pair_key = (s.unlocode.upper(), s.vessel_class_id)
        if pair_key not in snapshots_by_pair:
            snapshots_by_pair[pair_key] = s
        if s.unlocode.upper() not in snapshots_by_locode:
            snapshots_by_locode[s.unlocode.upper()] = s

    # 5b. Query subscription dates to determine if ports are past the initial 15-min accumulation window
    watch_dates_stmt = (
        select(
            UserWatchlist.unlocode,
            func.min(UserWatchlist.created_at).label("first_watched"),
        )
        .where(UserWatchlist.unlocode.in_(locode_keys))
        .group_by(UserWatchlist.unlocode)
    )
    wd_res = await session.execute(watch_dates_stmt)
    first_watched_by_locode: dict[str, datetime] = {
        r[0].upper(): r[1] for r in wd_res.all() if r[1] is not None
    }

    # 5c. Query 30-day historical snapshots for rolling baseline refinement in ONE batched query
    cutoff_30d = ts - timedelta(days=30)
    history_stmt = (
        select(
            PortRiskSnapshot.unlocode,
            PortRiskSnapshot.anchored_vessel_count,
            PortRiskSnapshot.updated_at,
        )
        .where(
            PortRiskSnapshot.unlocode.in_(locode_keys),
            PortRiskSnapshot.updated_at >= cutoff_30d,
        )
    )
    h_res = await session.execute(history_stmt)
    history_by_locode: dict[str, list[tuple[int, Any]]] = {}
    for unlocode, count, updated_at in h_res.all():
        history_by_locode.setdefault(unlocode.upper(), []).append((count, updated_at))

    # 6. Concurrently evaluate each resolved port in-memory
    async def evaluate_item(item: BulkRiskPortItem, port: Port) -> RiskAssessment:
        locode = port.unlocode.upper()
        hist_list = history_by_locode.get(locode)
        if hist_list:
            counts = [c for c, _ in hist_list if c is not None]
            dates = {u.date() if hasattr(u, "date") else u for _, u in hist_list if u is not None}
            hist_avg = round(sum(counts) / len(counts), 1) if counts else None
            days_collected = min(30, max(1, len(dates)))
        else:
            baseline = baselines_by_slot.get((locode, day_of_week, hour_of_day)) or baselines_by_locode.get(locode)
            hist_avg = round(baseline.avg_anchored_count, 1) if baseline else None
            days_collected = 30 if baseline else 0

        snap = snapshots_by_pair.get((locode, vessel_class)) or snapshots_by_locode.get(locode)
        if snap:
            anchored_count = snap.anchored_vessel_count
            underway_count = snap.underway_vessel_count
            is_initializing = False
        else:
            first_watched = first_watched_by_locode.get(locode)
            now_utc = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            if first_watched is not None:
                if first_watched.tzinfo is None:
                    first_watched = first_watched.replace(tzinfo=timezone.utc)
                age_minutes = (now_utc - first_watched).total_seconds() / 60.0
            else:
                age_minutes = 999.0

            if age_minutes < 15.0:
                anchored_count = None
                underway_count = 0
                is_initializing = True
            else:
                anchored_count = int(hist_avg) if hist_avg is not None else 0
                underway_count = 0
                is_initializing = False

        if not is_initializing and anchored_count is not None and hist_avg is None:
            hist_avg = float(anchored_count)
            days_collected = 1

        weather_metrics = WeatherMetrics(
            windSpeedKnots=snap.wind_speed_kts if snap and snap.wind_speed_kts is not None else 12.0,
            waveHeightM=snap.swell_height_m if snap and snap.swell_height_m is not None else 0.8,
            swellPeriodSec=6.0,
            visibilityNm=10.0,
            gustSpeedKnots=15.0,
        )
        weather_subrisk = evaluate_weather_risk(weather_metrics)

        congestion_assessment = assess_congestion_risk(
            anchored_count=anchored_count,
            hist_avg_anchored=hist_avg,
            underway_count=underway_count,
            is_initializing=is_initializing,
            baseline_days_collected=days_collected,
        )
        congestion_subrisk = SubRiskResult(**congestion_assessment.to_subrisk_result())
        congestion_metrics = CongestionMetrics(**congestion_assessment.to_congestion_metrics())

        # Determine tide offset
        if port.latitude is not None and port.longitude is not None:
            try:
                tide_res = await fetch_tide_offset(port.latitude, port.longitude)
                tide_offset_m = tide_res.tide_offset_m
                tide_data_available = tide_res.tide_data_available
            except Exception as exc:
                logger.warning(
                    "Tide fetch failed for bulk port %s: %s; defaulting to 0.0m",
                    port.unlocode,
                    exc,
                )
                tide_offset_m = 0.0
                tide_data_available = False
        else:
            tide_offset_m = 0.0
            tide_data_available = False

        nav_metrics, nav_subrisk = calculate_navigational_metrics(
            vessel_class=vessel_class,
            channel_depth_m=port.channel_depth_m,
            wave_height_m=weather_metrics.waveHeightM,
            wind_speed_knots=weather_metrics.windSpeedKnots,
            tide_height_m=tide_offset_m,
            tide_data_available=tide_data_available,
        )

        sub_risks = SubRisksDict(
            congestion=congestion_subrisk,
            weather=weather_subrisk,
            navigational=nav_subrisk,
        )

        canonical_port_id = item.id
        canonical_port_name = item.name or port.port_name

        unified_metrics = assemble_port_metrics(
            port_id=canonical_port_id,
            congestion=congestion_metrics,
            weather=weather_metrics,
            navigational=nav_metrics,
            timestamp=ts,
        )

        return assemble_risk_assessment(
            port_id=canonical_port_id,
            port_name=canonical_port_name,
            vessel_class=vessel_class,
            sub_risks=sub_risks,
            metrics=unified_metrics,
            timestamp=ts,
            alternatives=[],
            is_cold_start=congestion_metrics.isColdStart,
            is_initializing=congestion_metrics.isInitializing,
        )

    tasks = [evaluate_item(item, port) for item, port in resolved_pairs]
    assessments: list[RiskAssessment] = list(await asyncio.gather(*tasks))

    # 6. Batch discover and attach alternative port recommendations in O(1) query complexity
    if include_alternatives:
        high_risk_entries = [
            (port, vessel_class)
            for (_, port), assess in zip(resolved_pairs, assessments)
            if assess.compositeTier in ("high", "critical")
        ]
        all_ports = [port for _, port in resolved_pairs]
        try:
            alt_map = await batch_recommend_alternative_ports(
                session=session,
                all_batch_ports=all_ports,
                high_risk_ports=high_risk_entries,
                vessel_class=vessel_class,
            )
            for (_, port), assess in zip(resolved_pairs, assessments):
                if assess.compositeTier in ("high", "critical"):
                    assess.alternatives = alt_map.get(port.unlocode, [])
        except Exception as exc:
            logger.warning("Failed to evaluate alternative ports in bulk batch: %s", exc)

    return assessments


def snapshot_to_risk_assessment(
    snapshot: PortRiskSnapshot,
    port_id: str,
    port_name: str,
    alternatives: list[AlternativePortRecommendation] | None = None,
) -> RiskAssessment:
    """Convert an existing PortRiskSnapshot record into a schema-compliant RiskAssessment object."""
    ts = snapshot.updated_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    vessel_class = snapshot.vessel_class_id
    vessel_label = VESSEL_CLASS_LABELS.get(vessel_class, vessel_class)

    cong_tier = (snapshot.congestion_risk_level or "LOW").lower()
    nav_tier = (snapshot.grounding_risk_level or "LOW").lower()
    wx_tier = (snapshot.weather_risk_level or "LOW").lower()

    comp_tier: RiskTier = (snapshot.overall_risk_level or "LOW").lower()  # type: ignore[assignment]
    comp_score = TIER_SCORES.get(comp_tier, 25.0)

    congestion_sr = SubRiskResult(
        category="congestion",
        tier=cong_tier,  # type: ignore[arg-type]
        score=TIER_SCORES.get(cong_tier, 25.0),
        detail=f"Historical queue: {snapshot.anchored_vessel_count} anchored ({snapshot.queue_variance_pct:+.1f}% vs baseline).",
        factors=[f"Anchored vessel count {snapshot.anchored_vessel_count}."],
    )
    weather_sr = SubRiskResult(
        category="weather",
        tier=wx_tier,  # type: ignore[arg-type]
        score=TIER_SCORES.get(wx_tier, 25.0),
        detail=f"Historical marine swell {snapshot.swell_height_m or 0.0:.1f}m, wind {snapshot.wind_speed_kts or 0.0:.1f} kts.",
        factors=[f"Wave height {snapshot.swell_height_m or 0.0:.1f}m."],
    )
    navigational_sr = SubRiskResult(
        category="navigational",
        tier=nav_tier,  # type: ignore[arg-type]
        score=TIER_SCORES.get(nav_tier, 25.0),
        detail=f"Historical under-keel clearance at {nav_tier} tier.",
        factors=["Bathymetric channel and swell clearance."],
    )

    sub_risks = SubRisksDict(
        congestion=congestion_sr,
        weather=weather_sr,
        navigational=navigational_sr,
    )

    metrics = PortMetrics(
        portId=port_id,
        timestamp=ts,
        congestion=CongestionMetrics(
            anchorageQueueCount=snapshot.anchored_vessel_count,
            avgWaitingTimeHours=round(max(0.0, snapshot.anchored_vessel_count * 1.5), 1),
            berthOccupancyPct=round(min(100.0, max(20.0, snapshot.anchored_vessel_count * 5.0)), 1),
            rolling30dAvgQueue=snapshot.historical_avg_queue,
            rolling30dAvgWaitHours=12.0,
            underwayCount=snapshot.underway_vessel_count,
            baselineDaysCollected=30 if snapshot.historical_avg_queue > 0 else 0,
            isColdStart=snapshot.historical_avg_queue == 0.0,
            isInitializing=False,
        ),
        weather=WeatherMetrics(
            windSpeedKnots=snapshot.wind_speed_kts or 10.0,
            waveHeightM=snapshot.swell_height_m or 0.8,
            swellPeriodSec=6.0,
            visibilityNm=10.0,
            gustSpeedKnots=(snapshot.wind_speed_kts or 10.0) * 1.3,
        ),
        navigational=NavigationalMetrics(
            underKeelClearanceM=2.5 if nav_tier == "low" else (0.5 if nav_tier == "medium" else -0.5),
            channelDepthM=15.0,
            airDraftClearanceM=8.0,
            pilotageAvailable=True,
            tideHeightM=0.0,
        ),
    )

    assessment_id = f"risk-{port_id}-{vessel_class}-{ts_str}"

    return RiskAssessment(
        id=assessment_id,
        portId=port_id,
        portName=port_name,
        vesselClass=vessel_class,
        vesselClassLabel=vessel_label,
        timestamp=ts,
        compositeTier=comp_tier,
        compositeScore=comp_score,
        subRisks=sub_risks,
        metrics=metrics,
        isColdStart=snapshot.historical_avg_queue == 0.0,
        isInitializing=False,
        alternatives=alternatives or [],
    )


async def get_historical_risk_trend(
    session: AsyncSession,
    port: Port,
    vessel_class: str,
    days: int = 7,
    port_id: str | None = None,
    port_name: str | None = None,
) -> list[RiskAssessment]:
    """Retrieve chronological time-series risk evaluations capped at 40 points in ascending order."""
    if vessel_class not in VALID_VESSEL_CLASSES:
        raise ValueError(f"Invalid vesselClass '{vessel_class}'. Must be one of: {sorted(list(VALID_VESSEL_CLASSES))}")

    if not (1 <= days <= 30):
        raise ValueError(f"Query parameter 'days' must be between 1 and 30, got {days}.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(PortRiskSnapshot)
        .where(
            PortRiskSnapshot.unlocode == port.unlocode,
            PortRiskSnapshot.vessel_class_id == vessel_class,
            PortRiskSnapshot.updated_at >= cutoff,
        )
        .order_by(PortRiskSnapshot.updated_at.asc())
    )
    res = await session.execute(stmt)
    snapshots = list(res.scalars().all())

    if not snapshots:
        return []

    # If > 40 data points, cap to the 40 most recent evaluation points
    if len(snapshots) > 40:
        snapshots = snapshots[-40:]

    canonical_port_id = port_id or f"port-{port.unlocode.lower()}"
    canonical_port_name = port_name or port.port_name

    return [
        snapshot_to_risk_assessment(s, canonical_port_id, canonical_port_name)
        for s in snapshots
    ]


