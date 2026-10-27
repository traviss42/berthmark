"""Unit tests for Navigational Metrics, dynamic UKC with tides, and air draft."""

import pytest
from backend.services.navigational import (
    UNRESTRICTED_AIR_DRAFT_LIMIT,
    calculate_navigational_metrics,
)


def test_dynamic_ukc_with_tides_and_swells():
    """Verify UKC calculations across calm swell, heavy swell, and tidal offsets."""
    # Panamax: draft = 12.0m
    # Calm swell (Hs=1.0m <= 2.0m): req = 1.10 * 12.0 = 13.20m
    # Depth = 14.0m, Tide = +1.5m -> Total = 15.5m -> UKC = 15.5 - 13.20 = +2.30m -> LOW
    metrics_calm, subrisk_calm = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=14.0,
        wave_height_m=1.0,
        tide_height_m=1.5,
    )
    assert metrics_calm.underKeelClearanceM == 2.30
    assert metrics_calm.channelDepthM == 14.0
    assert metrics_calm.tideHeightM == 1.5
    assert subrisk_calm.tier == "low"

    # Heavy swell (Hs=3.0m > 2.0m): req = 1.30 * 12.0 = 15.60m
    # Depth = 14.0m, Tide = 0.0m -> Total = 14.0m -> UKC = 14.0 - 15.60 = -1.60m -> HIGH
    metrics_heavy, subrisk_heavy = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=14.0,
        wave_height_m=3.0,
        tide_height_m=0.0,
    )
    assert metrics_heavy.underKeelClearanceM == -1.60
    assert subrisk_heavy.tier == "high"


def test_air_draft_clearance_and_boundaries():
    """Verify air draft clearance and boundary transitions (<0.0m high, 0.0-2.0m med, >=2.0m low)."""
    # Panamax air draft is 45.0m

    # Default overhead limit (None -> 99.0m)
    m_default, sub_default = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=20.0,
        overhead_limit_m=None,
    )
    assert m_default.airDraftClearanceM == round(UNRESTRICTED_AIR_DRAFT_LIMIT - 45.0, 1)  # 54.0m
    assert sub_default.tier == "low"

    # Safe clearance: 50.0m limit - 45.0m draft = 5.0m clearance >= 2.0m -> LOW
    m_safe, sub_safe = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=20.0,
        overhead_limit_m=50.0,
    )
    assert m_safe.airDraftClearanceM == 5.0
    assert sub_safe.tier == "low"

    # Marginal clearance: 46.5m limit - 45.0m draft = 1.5m clearance (< 2.0m) -> MEDIUM
    m_med, sub_med = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=20.0,
        overhead_limit_m=46.5,
    )
    assert m_med.airDraftClearanceM == 1.5
    assert sub_med.tier == "medium"

    # Collision hazard: 44.0m limit - 45.0m draft = -1.0m clearance (< 0.0m) -> HIGH
    m_high, sub_high = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=20.0,
        overhead_limit_m=44.0,
    )
    assert m_high.airDraftClearanceM == -1.0
    assert sub_high.tier == "high"


def test_pilotage_suspension_under_adverse_weather():
    """Verify pilotage is suspended when wind > 30 kts or wave > 2.5 m, elevating tier to medium."""
    # High wind (35.0 kts > 30.0 kts) -> pilotage suspended
    m_wind, sub_wind = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=20.0,
        wind_speed_knots=35.0,
        wave_height_m=1.0,
    )
    assert m_wind.pilotageAvailable is False
    assert sub_wind.tier == "medium"

    # High wave (3.0m > 2.5m) with safe depth -> pilotage suspended
    m_wave, sub_wave = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=30.0,
        wind_speed_knots=15.0,
        wave_height_m=3.0,
    )
    assert m_wave.pilotageAvailable is False
    assert sub_wave.tier in ("medium", "high")


def test_missing_controlling_depth():
    """Verify missing channel depth (None or 0.0) defaults safely without false HIGH alarm."""
    m, sub = calculate_navigational_metrics(
        vessel_class="panamax",
        channel_depth_m=0.0,
        wave_height_m=1.0,
    )
    assert m.underKeelClearanceM == 0.0
    assert m.channelDepthM == 0.0
    assert sub.tier == "low"
    assert any("unverified or missing" in f for f in sub.factors)
