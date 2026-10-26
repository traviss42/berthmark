"""PIANC Report 121 Under-Keel Clearance (UKC) and Grounding Risk Calculation Module.

Pure calculation engine with zero database, ORM, or network I/O dependencies.
Evaluates controlling port channel depths against vessel draft and dynamic swell conditions.
"""

from dataclasses import dataclass
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
DEFAULT_HEAVY_SWELL_MULTIPLIER = 1.35
SWELL_HEIGHT_THRESHOLD_M = 2.0


def get_vessel_draft(vessel_class: str) -> float:
    """Retrieve standard benchmark draft (m) for a vessel class.

    Raises:
        KeyError: If vessel class is unrecognized.
    """
    cleaned = vessel_class.strip()
    canonical = NORMALIZED_VESSEL_CLASSES.get(cleaned.lower())
    if canonical is None or canonical not in VESSEL_BENCHMARK_DRAFTS:
        raise KeyError(f"Unrecognized vessel class: '{vessel_class}'. Must be one of {list(VESSEL_BENCHMARK_DRAFTS.keys())}")
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
    factors: list[str]

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
        tide_height_m: float = 0.0,
    ) -> dict[str, Any]:
        """Convert assessment into OpenAPI NavigationalMetrics schema object."""
        return {
            "underKeelClearanceM": round(self.ukc_margin_m, 2) if self.ukc_margin_m is not None else 0.0,
            "channelDepthM": round(self.channel_depth_m, 2) if self.channel_depth_m is not None else 0.0,
            "airDraftClearanceM": air_draft_clearance_m,
            "pilotageAvailable": pilotage_available,
            "tideHeightM": tide_height_m,
        }


def calculate_grounding_risk(
    vessel_class: str,
    channel_depth_m: float | None,
    wave_height_m: float = 0.0,
    custom_draft_m: float | None = None,
    swell_multiplier: float = DEFAULT_HEAVY_SWELL_MULTIPLIER,
    is_depth_available: bool = True,
) -> GroundingRiskAssessment:
    """Calculate Under-Keel Clearance (UKC) and PIANC grounding risk.

    Args:
        vessel_class: Vessel classification key (e.g. 'panamax', 'vlcc').
        channel_depth_m: Controlling channel depth in meters (WPI Pub 150).
        wave_height_m: Significant wave height Hs in meters (Open-Meteo).
        custom_draft_m: Optional override for vessel static draft Tdraft.
        swell_multiplier: Multiplier for Hs > 2.0m (default 1.35, range 1.30-1.40).
        is_depth_available: Flag indicating whether controlling depth is verified.

    Returns:
        GroundingRiskAssessment with tier ('low', 'medium', 'high'), numeric score, and details.
    """
    # 1. Input validations
    if wave_height_m < 0.0:
        raise ValueError(f"Wave height must be >= 0.0 meters, got {wave_height_m}")

    if not (1.30 <= swell_multiplier <= 1.40):
        raise ValueError(f"Swell multiplier must be within PIANC standard range [1.30, 1.40], got {swell_multiplier}")

    if custom_draft_m is not None:
        if custom_draft_m <= 0.0:
            raise ValueError(f"Custom vessel draft must be > 0.0 meters, got {custom_draft_m}")
        draft_m = float(custom_draft_m)
        cleaned_class = vessel_class.strip()
    else:
        draft_m = get_vessel_draft(vessel_class)
        cleaned_class = NORMALIZED_VESSEL_CLASSES[vessel_class.strip().lower()]

    # 2. Swell multiplier selection: Hs <= 2.0m -> 1.10, Hs > 2.0m -> swell_multiplier
    if wave_height_m <= SWELL_HEIGHT_THRESHOLD_M:
        applied_multiplier = CALM_SWELL_MULTIPLIER
        swell_condition = "calm/sheltered"
    else:
        applied_multiplier = swell_multiplier
        swell_condition = "outer channel/heavy swell"

    required_depth_m = round(applied_multiplier * draft_m, 2)

    # 3. Missing or unverified controlling depth handling
    depth_valid = (
        is_depth_available
        and channel_depth_m is not None
        and channel_depth_m > 0.0
    )

    if not depth_valid:
        warning_msg = "Controlling channel depth unverified or missing; physical grounding risk cannot be computed."
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
        )

    # 4. Under-Keel Clearance (UKC) calculation
    depth_val = float(channel_depth_m)
    ukc_margin_m = round(depth_val - required_depth_m, 2)

    # 5. Risk tier classification based on UKC margin
    # LOW: UKC >= 1.0m (score 25)
    # MEDIUM: 0.0m <= UKC < 1.0m (score 60)
    # HIGH: UKC < 0.0m (score 90)
    factors: list[str] = [
        f"Controlling channel depth: {depth_val:.1f}m",
        f"Design draft: {draft_m:.1f}m ({cleaned_class})",
        f"Swell conditions: Hs={wave_height_m:.1f}m ({swell_condition}, multiplier {applied_multiplier:.2f})",
        f"Required UKC depth: {required_depth_m:.2f}m",
        f"Calculated clearance margin: {ukc_margin_m:+.2f}m",
    ]

    if ukc_margin_m >= 1.00:
        tier = "low"
        score = 25.0
        detail = f"Adequate clearance margin ({ukc_margin_m:+.2f}m >= 1.00m) satisfying PIANC guidelines."
    elif ukc_margin_m >= 0.00:
        tier = "medium"
        score = 60.0
        detail = f"Marginal clearance ({ukc_margin_m:+.2f}m < 1.00m). Tidal window or speed restrictions recommended."
        factors.append("Clearance margin under 1.0m threshold; high tide arrival required.")
    else:
        tier = "high"
        score = 90.0
        detail = f"Grounding hazard: Depth deficit of {abs(ukc_margin_m):.2f}m below PIANC required clearance."
        factors.append(f"Depth violation: Channel depth {depth_val:.1f}m < required depth {required_depth_m:.2f}m.")

    return GroundingRiskAssessment(
        vessel_class=cleaned_class,
        draft_m=draft_m,
        channel_depth_m=depth_val,
        wave_height_m=wave_height_m,
        is_depth_available=True,
        required_depth_m=required_depth_m,
        ukc_margin_m=ukc_margin_m,
        tier=tier,
        score=score,
        detail=detail,
        factors=factors,
    )
