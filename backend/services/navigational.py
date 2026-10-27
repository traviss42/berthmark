"""Navigational clearance, dynamic UKC with tides, air draft, and pilotage service."""

from backend.schemas.metrics import NavigationalMetrics, SubRiskResult
from backend.services.grounding import (
    calculate_grounding_risk,
    get_vessel_draft,
)

# Standard baseline air drafts (m) per vessel class (keel/waterline to mast top)
VESSEL_BENCHMARK_AIR_DRAFTS: dict[str, float] = {
    "feeder": 32.0,
    "panamax": 45.0,
    "neoPanamax": 48.0,
    "ulcv": 52.0,
    "mrTanker": 35.0,
    "aframax": 42.0,
    "suezmax": 46.0,
    "vlcc": 55.0,
    "handysize": 34.0,
    "panamaxBulk": 42.0,
    "capesize": 48.0,
    "pctc": 38.0,
    "lng": 45.0,
}

UNRESTRICTED_AIR_DRAFT_LIMIT = 99.0


def calculate_navigational_metrics(
    vessel_class: str,
    channel_depth_m: float | None,
    wave_height_m: float = 0.0,
    wind_speed_knots: float = 0.0,
    tide_height_m: float = 0.0,
    overhead_limit_m: float | None = None,
    custom_draft_m: float | None = None,
) -> tuple[NavigationalMetrics, SubRiskResult]:
    """Calculate dynamic navigational metrics and evaluate composite navigational sub-risk.

    Evaluates:
        1. Dynamic Under-Keel Clearance (UKC) adjusting for tidal elevation, wave swell, and inner basin tiers.
        2. Air draft clearance beneath overhead bridges/cables.
        3. Harbor pilotage service availability under wind/swell conditions.

    Returns:
        Tuple of (NavigationalMetrics, SubRiskResult).
    """
    # 1. Grounding and UKC calculation via PIANC grounding engine
    grounding_res = calculate_grounding_risk(
        vessel_class=vessel_class,
        channel_depth_m=channel_depth_m,
        wave_height_m=wave_height_m,
        tide_offset_m=tide_height_m,
        custom_draft_m=custom_draft_m,
    )
    ukc_tier = grounding_res.tier
    ukc_margin_m = grounding_res.ukc_margin_m if grounding_res.ukc_margin_m is not None else 0.0
    effective_channel_depth = grounding_res.channel_depth_m if grounding_res.channel_depth_m is not None else 0.0

    factors: list[str] = list(grounding_res.factors)

    # 2. Air draft clearance calculation
    overhead_limit = (
        float(overhead_limit_m)
        if overhead_limit_m is not None
        else UNRESTRICTED_AIR_DRAFT_LIMIT
    )
    vessel_air_draft = VESSEL_BENCHMARK_AIR_DRAFTS.get(vessel_class.strip(), 45.0)
    air_draft_clearance = round(overhead_limit - vessel_air_draft, 1)

    factors.append(
        f"Air draft clearance: {air_draft_clearance:+.1f}m (bridge limit {overhead_limit:.1f}m - vessel air draft {vessel_air_draft:.1f}m)"
    )

    if air_draft_clearance < 0.0:
        air_draft_tier = "high"
        factors.append(f"Bridge collision hazard: Vessel exceeds overhead limit by {abs(air_draft_clearance):.1f}m.")
    elif air_draft_clearance < 2.0:
        air_draft_tier = "medium"
        factors.append("Marginal air draft clearance (<2.0m); ballast adjustment required.")
    else:
        air_draft_tier = "low"

    # 3. Harbor pilotage availability
    # Pilot boarding suspended when wind > 30.0 kts or wave > 2.5 m
    if wind_speed_knots > 30.0 or wave_height_m > 2.5:
        pilotage_available = False
        pilotage_tier = "medium"
        factors.append(
            f"Harbor pilotage suspended due to adverse sea state (wind {wind_speed_knots:.1f}kts > 30kts or wave {wave_height_m:.1f}m > 2.5m)."
        )
    else:
        pilotage_available = True
        pilotage_tier = "low"

    # 4. Composite Navigational SubRiskResult
    # Worst-case hazard gating
    tier_ranks = {"low": 1, "medium": 2, "high": 3}
    max_rank = max(tier_ranks[ukc_tier], tier_ranks[air_draft_tier], tier_ranks[pilotage_tier])

    if max_rank == 3:
        overall_tier = "high"
        overall_score = 90.0
        detail = "High navigational hazard: Critical clearance violation detected."
    elif max_rank == 2:
        overall_tier = "medium"
        overall_score = 60.0
        detail = "Moderate navigational risk: Marginal clearance or pilotage service suspension."
    else:
        overall_tier = "low"
        overall_score = 25.0
        detail = f"Safe navigational passage: UKC {ukc_margin_m:+.2f}m and air draft clearance {air_draft_clearance:+.1f}m."

    metrics = NavigationalMetrics(
        underKeelClearanceM=round(ukc_margin_m, 2),
        channelDepthM=round(effective_channel_depth, 2),
        airDraftClearanceM=air_draft_clearance,
        pilotageAvailable=pilotage_available,
        tideHeightM=round(tide_height_m, 2),
    )

    subrisk = SubRiskResult(
        category="navigational",
        tier=overall_tier,
        score=overall_score,
        detail=detail,
        factors=factors,
    )

    return metrics, subrisk
