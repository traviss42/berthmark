"""Common types and enums mirroring frontend vessel taxonomy and risk tiers."""

from typing import Literal

RiskTier = Literal["low", "medium", "high"]

SubRiskCategory = Literal[
    "congestion",
    "terminalDelays",
    "weather",
    "navigational",
]

VesselSector = Literal[
    "containerized",
    "liquidBulk",
    "dryBulk",
    "specialized",
]

VesselClass = Literal[
    # Containerized
    "feeder",
    "panamax",
    "neoPanamax",
    "ulcv",
    # Liquid Bulk
    "mrTanker",
    "aframax",
    "suezmax",
    "vlcc",
    # Dry Bulk
    "handysize",
    "panamaxBulk",
    "capesize",
    # Specialized
    "pctc",
    "lng",
]
