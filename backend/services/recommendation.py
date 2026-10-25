"""Automated Alternative Port Recommendation Engine (Issue 17)."""

import logging
import math
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Port, PortRiskSnapshot
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.schemas.recommendation import AlternativePortRecommendation

logger = logging.getLogger(__name__)

BENCHMARK_VESSEL_DRAFTS: dict[str, float] = {
    "feeder": 8.5,
    "panamax": 12.0,
    "neoPanamax": 15.2,
    "ulcv": 16.0,
    "mrTanker": 11.0,
    "aframax": 14.8,
    "suezmax": 16.0,
    "vlcc": 21.0,
    "handysize": 10.5,
    "panamaxBulk": 14.5,
    "capesize": 18.0,
    "pctc": 10.0,
    "lng": 12.0,
}


def calculate_required_depth_m(vessel_class: str, wave_height_m: float = 0.0) -> float:
    """Calculate required depth h_req based on vessel draft and wave swell.

    Calm swell (Hs <= 2.0m): h_req = 1.10 * T_draft, rounded to 2 decimal places.
    Heavy swell (Hs > 2.0m): h_req = 1.35 * T_draft, rounded to 2 decimal places.
    """
    if vessel_class not in BENCHMARK_VESSEL_DRAFTS:
        raise ValueError(
            f"Invalid vesselClass '{vessel_class}'. Must be one of: {sorted(list(BENCHMARK_VESSEL_DRAFTS.keys()))}"
        )
    draft = BENCHMARK_VESSEL_DRAFTS[vessel_class]
    factor = 1.10 if wave_height_m <= 2.0 else 1.35
    return round(draft * factor, 2)


def calculate_haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two geographic coordinates in Nautical Miles (Earth radius 3440.065 NM)."""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    r_nm = 3440.065
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.asin(math.sqrt(a))
    return round(r_nm * c, 1)


async def recommend_alternative_ports(
    session: AsyncSession,
    primary_port: Port,
    vessel_class: str,
    primary_risk_tier: str,
    wave_height_m: float = 0.0,
) -> list[AlternativePortRecommendation]:
    """Discover, depth-gate at SQL level, rank by Haversine distance, and filter top 3 alternative ports.

    Trigger condition: primary_risk_tier must be HIGH or CRITICAL. Otherwise returns empty list [].
    """
    tier_upper = primary_risk_tier.strip().upper()
    if tier_upper not in ("HIGH", "CRITICAL"):
        return []

    # Step 1 & 2: Calculate h_req and query candidate ports with SQL-level depth gating
    h_req = calculate_required_depth_m(vessel_class, wave_height_m)

    stmt = (
        select(Port)
        .where(
            Port.subdivision_code == primary_port.subdivision_code,
            Port.unlocode != primary_port.unlocode,
            Port.is_depth_available.is_(True),
            Port.channel_depth_m.isnot(None),
            Port.channel_depth_m >= h_req,
        )
    )
    res = await session.execute(stmt)
    candidates = list(res.scalars().all())

    if not candidates:
        return []

    # Step 3 & 4: Fetch latest snapshots for candidates to verify risk status & swell
    candidate_locodes = [c.unlocode for c in candidates]
    snap_stmt = (
        select(PortRiskSnapshot)
        .where(
            PortRiskSnapshot.unlocode.in_(candidate_locodes),
            PortRiskSnapshot.vessel_class_id == vessel_class,
        )
        .order_by(PortRiskSnapshot.updated_at.desc())
    )
    s_res = await session.execute(snap_stmt)
    latest_snaps: dict[str, PortRiskSnapshot] = {}
    for s in s_res.scalars().all():
        if s.unlocode not in latest_snaps:
            latest_snaps[s.unlocode] = s

    eligible: list[AlternativePortRecommendation] = []
    for cand in candidates:
        snap = latest_snaps.get(cand.unlocode)
        cand_risk = (snap.overall_risk_level if snap and snap.overall_risk_level else "LOW").upper()

        # Step 4: Disqualify candidates operating at HIGH or CRITICAL risk
        cand_wave = snap.swell_height_m if snap and snap.swell_height_m is not None else 0.8
        cand_wind = snap.wind_speed_kts if snap and snap.wind_speed_kts is not None else 10.0

        if cand_risk in ("HIGH", "CRITICAL") or cand_wave > 2.5 or cand_wind > 30.0:
            continue

        tier_lower: Literal["low", "medium"] = "medium" if cand_risk == "MEDIUM" else "low"

        # Step 3: Compute distance
        dist_nm = calculate_haversine_distance_nm(
            primary_port.latitude, primary_port.longitude, cand.latitude, cand.longitude
        )

        depth = cand.channel_depth_m or 0.0
        depth_margin = round(depth - h_req, 2)

        anchored = snap.anchored_vessel_count if snap else 2
        underway = snap.underway_vessel_count if snap else 1
        traffic = f"{anchored} anchored / {underway} underway"

        cand_port_id = f"port-{cand.unlocode.lower()}"
        for b_locode, meta in BENCHMARK_PORTS_METADATA.items():
            if b_locode.upper() == cand.unlocode.upper():
                cand_port_id = meta["id"]
                break

        rec = AlternativePortRecommendation(
            portId=cand_port_id,
            unlocode=cand.unlocode,
            portName=cand.port_name,
            country=cand.country_code,
            distanceNm=dist_nm,
            channelDepthM=round(depth, 1),
            depthMarginM=depth_margin,
            swellHeightM=round(cand_wave, 1),
            riskTier=tier_lower,
            trafficStatus=traffic,
        )
        eligible.append(rec)

    # Sort ascending by distance
    eligible.sort(key=lambda r: r.distanceNm)

    # Return top 3
    return eligible[:3]
