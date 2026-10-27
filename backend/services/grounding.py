"""PIANC Report 121 Under-Keel Clearance (UKC) and Grounding Risk Calculation Module.

Pure calculation engine with zero database, ORM, or network I/O dependencies.
Evaluates controlling port channel depths against vessel draft, dynamic tide offsets,
and wave swell conditions across standard commercial vessel classes.
"""

from dataclasses import dataclass, field
from typing import Any

# Standard 13 commercial vessel classes and baseline design drafts in meters
VESSEL_BENCHMARK_DRAFTS: dict[str, float] = {
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

# Normalization alias map for vessel class lookup
NORMALIZED_VESSEL_CLASSES: dict[str, str] = {
    "feeder": "feeder",
    "panamax": "panamax",
    "neopanamax": "neoPanamax",
    "neo_panamax": "neoPanamax",
    "newpanamax": "neoPanamax",
    "new_panamax": "neoPanamax",
    "ulcv": "ulcv",
    "ulcs": "ulcv",
    "mrtanker": "mrTanker",
    "mr_tanker": "mrTanker",
    "aframax": "aframax",
    "suezmax": "suezmax",
    "vlcc": "vlcc",
    "handysize": "handysize",
    "handymax": "handysize",
    "supramax": "handysize",
    "panamaxbulk": "panamaxBulk",
    "panamax_bulk": "panamaxBulk",
    "capesize": "capesize",
    "pctc": "pctc",
    "lng": "lng",
}

CALM_SWELL_MULTIPLIER = 1.10
DEFAULT_HEAVY_SWELL_MULTIPLIER = 1.30
SWELL_HEIGHT_THRESHOLD_M = 2.0
CALM_INNER_CHANNEL_THRESHOLD_M = 1.0


def get_vessel_draft(vessel_class: str) -> float:
    """Retrieve standard benchmark draft (m) for a vessel class.

    Raises:
        KeyError: If vessel class is unrecognized.
    """
    cleaned = vessel_class.strip()
    canonical = NORMALIZED_VESSEL_CLASSES.get(cleaned.lower())
    if canonical is None or canonical not in VESSEL_BENCHMARK_DRAFTS:
        raise KeyError(
            f"Unrecognized vessel class: '{vessel_class}'. Must be one of {list(VESSEL_BENCHMARK_DRAFTS.keys())}"
        )
    return VESSEL_BENCHMARK_DRAFTS[canonical]


@dataclass(frozen=True, slots=True)
class GroundingRiskAssessment:
    """Immutable evaluation result for channel Under-Keel Clearance and grounding risk."""

    vessel_class: str
    draft_m: float
    channel_depth_m: float | None
    wave_height_m: float
    is_depth_available: bool
    required_depth_m: float
    ukc_margin_m: float | None
    tier: str  # "low", "medium", "high"
    score: float  # 25.0, 60.0, 90.0
    detail: str
    factors: list[str] = field(default_factory=list)
    tide_offset_m: float = 0.0
    available_depth_m: float | None = None
    net_margin_m: float | None = None
    tide_data_available: bool = True

    def to_subrisk_result(self) -> dict[str, Any]:
        """Convert assessment into OpenAPI SubRiskResult schema object."""
        return {
            "category": "navigational",
            "tier": self.tier,
            "score": self.score,
            "detail": self.detail,
            "factors": list(self.factors),
        }

    def to_navigational_metrics(
        self,
        air_draft_clearance_m: float = 8.5,
        pilotage_available: bool = True,
        tide_height_m: float | None = None,
    ) -> dict[str, Any]:
        """Convert assessment into OpenAPI NavigationalMetrics schema object."""
        tide_val = tide_height_m if tide_height_m is not None else self.tide_offset_m
        return {
            "underKeelClearanceM": (
                round(self.ukc_margin_m, 2) if self.ukc_margin_m is not None else 0.0
            ),
            "channelDepthM": (
                round(self.channel_depth_m, 2) if self.channel_depth_m is not None else 0.0
            ),
            "airDraftClearanceM": air_draft_clearance_m,
            "pilotageAvailable": pilotage_available,
            "tideHeightM": round(tide_val, 2),
        }


def calculate_grounding_risk(
    vessel_class: str,
    channel_depth_m: float | None,
    wave_height_m: float = 0.0,
    tide_offset_m: float = 0.0,
    custom_draft_m: float | None = None,
    swell_multiplier: float = DEFAULT_HEAVY_SWELL_MULTIPLIER,
    is_depth_available: bool = True,
    tide_data_available: bool = True,
) -> GroundingRiskAssessment:
    """Calculate Under-Keel Clearance (UKC) and PIANC grounding risk.

    Incorporates dynamic tide offset ingestion and calm inner-channel net clearance tiers.

    Args:
        vessel_class: Vessel classification key (e.g. 'panamax', 'vlcc', 'neoPanamax').
        channel_depth_m: Controlling channel depth in meters (WPI Pub 150).
        wave_height_m: Significant wave height Hs in meters (Open-Meteo).
        tide_offset_m: Dynamic tide water elevation above chart datum/MLLW in meters.
        custom_draft_m: Optional override for vessel static draft Tdraft.
        swell_multiplier: Multiplier for Hs > 2.0m (default 1.30, range 1.30-1.40).
        is_depth_available: Flag indicating whether controlling depth is verified.
        tide_data_available: Flag indicating whether live tide data was retrieved.

    Returns:
        GroundingRiskAssessment with tier ('low', 'medium', 'high'), numeric score, and details.
    """
    # 1. Input validations
    if wave_height_m < 0.0:
        raise ValueError(f"Wave height must be >= 0.0 meters, got {wave_height_m}")

    if not (1.30 <= swell_multiplier <= 1.40):
        raise ValueError(
            f"Swell multiplier must be within PIANC standard range [1.30, 1.40], got {swell_multiplier}"
        )

    if custom_draft_m is not None:
        if custom_draft_m <= 0.0:
            raise ValueError(f"Custom vessel draft must be > 0.0 meters, got {custom_draft_m}")
        draft_m = float(custom_draft_m)
        cleaned_class = vessel_class.strip()
    else:
        draft_m = get_vessel_draft(vessel_class)
        cleaned_class = NORMALIZED_VESSEL_CLASSES[vessel_class.strip().lower()]

    # 2. Swell multiplier selection:
    # Outer / Swell Hazard Rule: Hs > 2.0m -> swell_multiplier (1.30)
    # Standard Gross Multiplier: Hs <= 2.0m -> 1.10
    if wave_height_m > SWELL_HEIGHT_THRESHOLD_M:
        applied_multiplier = swell_multiplier
        swell_condition = "outer channel/heavy swell"
    else:
        applied_multiplier = CALM_SWELL_MULTIPLIER
        swell_condition = (
            "standard swell"
            if wave_height_m > CALM_INNER_CHANNEL_THRESHOLD_M
            else "calm inner channel"
        )

    required_depth_m = round(applied_multiplier * draft_m, 2)

    # 3. Missing or unverified controlling depth handling
    depth_valid = (
        is_depth_available
        and channel_depth_m is not None
        and channel_depth_m > 0.0
    )

    if not depth_valid:
        warning_msg = (
            "Controlling channel depth unverified or missing; physical grounding risk cannot be computed."
        )
        return GroundingRiskAssessment(
            vessel_class=cleaned_class,
            draft_m=draft_m,
            channel_depth_m=channel_depth_m,
            wave_height_m=wave_height_m,
            is_depth_available=False,
            required_depth_m=required_depth_m,
            ukc_margin_m=None,
            tier="low",
            score=25.0,
            detail="Controlling depth data not available. Defaulting to safe tier to avoid false alarms.",
            factors=[warning_msg],
            tide_offset_m=tide_offset_m,
            available_depth_m=None,
            net_margin_m=None,
            tide_data_available=tide_data_available,
        )

    # 4. Available Depth & Clearance calculations
    base_channel_depth = float(channel_depth_m)
    available_depth_m = round(base_channel_depth + tide_offset_m, 2)
    ukc_margin_m = round(available_depth_m - required_depth_m, 2)
    net_margin_m = round(available_depth_m - draft_m, 2)

    # 5. Calm Inner Channel Net Tier: Hs <= 1.0m
    is_calm = wave_height_m <= CALM_INNER_CHANNEL_THRESHOLD_M

    factors: list[str] = [
        f"Controlling channel depth: {base_channel_depth:.1f}m (WPI baseline)",
        f"Dynamic tide offset: {tide_offset_m:+.2f}m (Available depth: {available_depth_m:.2f}m)",
        f"Design draft: {draft_m:.1f}m ({cleaned_class})",
        f"Swell conditions: Hs={wave_height_m:.2f}m ({swell_condition}, multiplier {applied_multiplier:.2f})",
        f"Required UKC depth: {required_depth_m:.2f}m",
        f"Calculated UKC margin: {ukc_margin_m:+.2f}m",
    ]

    if is_calm:
        factors.append(f"Calm inner channel net clearance margin: {net_margin_m:+.2f}m")

    if not tide_data_available:
        factors.append("Live tide API unavailable; defaulted to static 0.0m MLLW baseline.")

    # 6. Risk Categorization Rules:
    # LOW RISK: Available Depth >= h_req + 1.0m (safe clearance margin),
    #           or under calm swell (Hs <= 1.0m) when available_depth >= h_req.
    if available_depth_m >= required_depth_m + 1.0:
        tier = "low"
        score = 25.0
        detail = f"Safe clearance margin ({ukc_margin_m:+.2f}m >= 1.00m) satisfying PIANC guidelines."
    elif is_calm and available_depth_m >= required_depth_m:
        tier = "low"
        score = 25.0
        detail = f"Adequate clearance margin ({ukc_margin_m:+.2f}m) in calm inner channel satisfying PIANC guidelines."

    # MEDIUM RISK (Tidal Window Required / Calm Basin Net Clearance):
    # Available Depth at low tide (0.0m offset) < h_req, but Available Depth at high tide >= h_req
    # OR Net Margin >= 0.9m under calm swell (Hs <= 1.0m).
    elif (is_calm and net_margin_m >= 0.90) or (available_depth_m >= required_depth_m):
        tier = "medium"
        score = 60.0
        detail = (
            f"Tidal window required: Marginal clearance (Net margin {net_margin_m:+.2f}m, "
            f"UKC {ukc_margin_m:+.2f}m). High tide transit required."
        )
        factors.append("Tidal window or calm inner basin net clearance required for safe transit.")

    # HIGH / CRITICAL RISK:
    # Available Depth at high tide < h_req AND Net Margin < 0.9m (grounding hazard).
    else:
        tier = "high"
        score = 90.0
        detail = f"Grounding hazard: Depth deficit of {abs(ukc_margin_m):.2f}m below PIANC required clearance."
        factors.append(
            f"Depth violation: Available depth {available_depth_m:.1f}m < required depth {required_depth_m:.2f}m."
        )

    return GroundingRiskAssessment(
        vessel_class=cleaned_class,
        draft_m=draft_m,
        channel_depth_m=base_channel_depth,
        wave_height_m=wave_height_m,
        is_depth_available=True,
        required_depth_m=required_depth_m,
        ukc_margin_m=ukc_margin_m,
        tier=tier,
        score=score,
        detail=detail,
        factors=factors,
        tide_offset_m=tide_offset_m,
        available_depth_m=available_depth_m,
        net_margin_m=net_margin_m,
        tide_data_available=tide_data_available,
    )
