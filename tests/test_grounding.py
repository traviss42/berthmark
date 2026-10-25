"""Unit and performance benchmark tests for PIANC Grounding Risk Module."""

import time
import pytest

from backend.services.grounding import (
    CALM_SWELL_MULTIPLIER,
    DEFAULT_HEAVY_SWELL_MULTIPLIER,
    VESSEL_BENCHMARK_DRAFTS,
    calculate_grounding_risk,
    get_vessel_draft,
)

EXPECTED_BENCHMARK_DRAFTS = {
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


# ─── 1. Vessel Benchmark Draft Lookups ──────────────────────────────────────────

def test_vessel_benchmark_drafts_all_13_classes():
    """Verify standard benchmark drafts for all 13 commercial vessel classes."""
    assert len(VESSEL_BENCHMARK_DRAFTS) == 13
    for v_class, expected_draft in EXPECTED_BENCHMARK_DRAFTS.items():
        assert get_vessel_draft(v_class) == expected_draft
        # Test case-insensitive lookup
        assert get_vessel_draft(v_class.lower()) == expected_draft


def test_invalid_vessel_class_raises():
    """Verify lookup with an unrecognized vessel class raises KeyError."""
    with pytest.raises(KeyError):
        get_vessel_draft("unknown_submarine")
    with pytest.raises(KeyError):
        calculate_grounding_risk(vessel_class="invalid_ship", channel_depth_m=15.0)


# ─── 2. Swell Condition Multiplier & Boundary Thresholds ──────────────────────

def test_calm_vs_heavy_swell_multiplier():
    """Verify calm swell (Hs <= 2.0m -> 1.10) and heavy swell (Hs > 2.0m -> 1.35)."""
    draft = 12.0  # Panamax

    # Hs = 1.0m (calm) -> h_req = 1.10 * 12.0 = 13.20m
    res_calm = calculate_grounding_risk("panamax", channel_depth_m=16.0, wave_height_m=1.0)
    assert res_calm.required_depth_m == 13.20

    # Hs = 3.0m (heavy) -> h_req = 1.35 * 12.0 = 16.20m
    res_heavy = calculate_grounding_risk("panamax", channel_depth_m=16.0, wave_height_m=3.0)
    assert res_heavy.required_depth_m == 16.20


def test_swell_boundary_cutoffs():
    """Verify exact transition at boundary Hs = 2.00m vs 2.01m."""
    draft = 10.0  # PCTC
    # Hs = 2.00m -> exactly on calm boundary (1.10 * 10 = 11.00m)
    res_200 = calculate_grounding_risk("pctc", channel_depth_m=15.0, wave_height_m=2.00)
    assert res_200.required_depth_m == 11.00

    # Hs = 2.01m -> immediately triggers heavy swell (1.35 * 10 = 13.50m)
    res_201 = calculate_grounding_risk("pctc", channel_depth_m=15.0, wave_height_m=2.01)
    assert res_201.required_depth_m == 13.50


# ─── 3. UKC Margins & Risk Tier Transitions ───────────────────────────────────

def test_ukc_margin_and_risk_tiers():
    """Verify UKC = channel_depth - h_req and tier mapping (low >= 1.0m, medium [0, 1.0m), high < 0m)."""
    # Panamax (draft = 12.0m, Hs = 1.0m -> h_req = 13.20m)

    # 1. Depth = 15.00m -> UKC = +1.80m -> LOW (score 25)
    res_low = calculate_grounding_risk("panamax", channel_depth_m=15.00, wave_height_m=1.0)
    assert res_low.ukc_margin_m == 1.80
    assert res_low.tier == "low"
    assert res_low.score == 25.0

    # 2. Depth = 13.70m -> UKC = +0.50m -> MEDIUM (score 60)
    res_med = calculate_grounding_risk("panamax", channel_depth_m=13.70, wave_height_m=1.0)
    assert res_med.ukc_margin_m == 0.50
    assert res_med.tier == "medium"
    assert res_med.score == 60.0

    # 3. Depth = 12.50m -> UKC = -0.70m -> HIGH (score 90)
    res_high = calculate_grounding_risk("panamax", channel_depth_m=12.50, wave_height_m=1.0)
    assert res_high.ukc_margin_m == -0.70
    assert res_high.tier == "high"
    assert res_high.score == 90.0


def test_exact_edge_cutoffs():
    """Verify edge boundaries: UKC = 1.00m (low) vs 0.99m (medium), and 0.00m (medium) vs -0.01m (high)."""
    # Feeder: draft = 8.5m, Hs = 1.0m -> h_req = 1.10 * 8.5 = 9.35m

    # Depth = 10.35m -> UKC = 1.00m -> LOW
    res_100 = calculate_grounding_risk("feeder", channel_depth_m=10.35, wave_height_m=1.0)
    assert res_100.ukc_margin_m == 1.00
    assert res_100.tier == "low"

    # Depth = 10.34m -> UKC = 0.99m -> MEDIUM
    res_099 = calculate_grounding_risk("feeder", channel_depth_m=10.34, wave_height_m=1.0)
    assert res_099.ukc_margin_m == 0.99
    assert res_099.tier == "medium"

    # Depth = 9.35m -> UKC = 0.00m -> MEDIUM
    res_000 = calculate_grounding_risk("feeder", channel_depth_m=9.35, wave_height_m=1.0)
    assert res_000.ukc_margin_m == 0.00
    assert res_000.tier == "medium"

    # Depth = 9.34m -> UKC = -0.01m -> HIGH
    res_neg = calculate_grounding_risk("feeder", channel_depth_m=9.34, wave_height_m=1.0)
    assert res_neg.ukc_margin_m == -0.01
    assert res_neg.tier == "high"


# ─── 4. Missing / Unverified Depth Handling ───────────────────────────────────

def test_missing_depth_handling():
    """Verify missing, null, or zero depth does not escalate to false HIGH risk."""
    for depth in [None, 0.0, -5.0]:
        res = calculate_grounding_risk("vlcc", channel_depth_m=depth, wave_height_m=1.5)
        assert res.is_depth_available is False
        assert res.ukc_margin_m is None
        assert res.tier == "low"
        assert res.score == 25.0
        assert any("unverified or missing" in f for f in res.factors)

    # Flag is_depth_available=False explicitly
    res_unavail = calculate_grounding_risk(
        "vlcc", channel_depth_m=25.0, wave_height_m=1.5, is_depth_available=False
    )
    assert res_unavail.is_depth_available is False
    assert res_unavail.ukc_margin_m is None
    assert res_unavail.tier == "low"


# ─── 5. Input Validation ──────────────────────────────────────────────────────

def test_input_validations():
    """Verify input validation catches negative wave heights and zero/negative drafts."""
    # Negative wave height
    with pytest.raises(ValueError):
        calculate_grounding_risk("panamax", channel_depth_m=15.0, wave_height_m=-0.5)

    # Custom draft <= 0.0
    with pytest.raises(ValueError):
        calculate_grounding_risk("panamax", channel_depth_m=15.0, custom_draft_m=0.0)
    with pytest.raises(ValueError):
        calculate_grounding_risk("panamax", channel_depth_m=15.0, custom_draft_m=-10.0)

    # Swell multiplier outside [1.30, 1.40]
    with pytest.raises(ValueError):
        calculate_grounding_risk("panamax", channel_depth_m=15.0, swell_multiplier=1.25)
    with pytest.raises(ValueError):
        calculate_grounding_risk("panamax", channel_depth_m=15.0, swell_multiplier=1.45)


# ─── 6. OpenAPI Output Schema Helpers ─────────────────────────────────────────

def test_openapi_schema_helpers():
    """Verify to_subrisk_result() and to_navigational_metrics() output compliance."""
    res = calculate_grounding_risk("panamax", channel_depth_m=15.0, wave_height_m=1.0)

    # SubRiskResult
    subrisk = res.to_subrisk_result()
    assert subrisk["category"] == "navigational"
    assert subrisk["tier"] in ("low", "medium", "high")
    assert isinstance(subrisk["score"], float)
    assert isinstance(subrisk["detail"], str)
    assert isinstance(subrisk["factors"], list)

    # NavigationalMetrics
    nav = res.to_navigational_metrics(air_draft_clearance_m=9.0, pilotage_available=True)
    assert nav["underKeelClearanceM"] == 1.80
    assert nav["channelDepthM"] == 15.0
    assert nav["airDraftClearanceM"] == 9.0
    assert nav["pilotageAvailable"] is True
    assert nav["tideHeightM"] == 0.0


# ─── 7. All 13 Classes Across 3 Swell Regimes ──────────────────────────────────

def test_all_13_classes_across_swell_regimes():
    """Verify calculations for all 13 vessel classes under calm, moderate, and severe swells."""
    swell_regimes = [0.5, 2.5, 4.0]

    for v_class in EXPECTED_BENCHMARK_DRAFTS:
        for hs in swell_regimes:
            res = calculate_grounding_risk(v_class, channel_depth_m=25.0, wave_height_m=hs)
            assert res.is_depth_available is True
            assert res.draft_m == EXPECTED_BENCHMARK_DRAFTS[v_class]
            assert res.wave_height_m == hs
            assert res.ukc_margin_m is not None
            assert res.tier in ("low", "medium", "high")


# ─── 8. Performance Benchmark ─────────────────────────────────────────────────

def test_performance_benchmark():
    """Verify 10,000 pure calculation evaluations complete in under 100 milliseconds."""
    classes = list(EXPECTED_BENCHMARK_DRAFTS.keys())
    depths = [12.0, 14.5, 16.0, 18.0, 22.0]
    waves = [0.8, 1.5, 2.0, 2.5, 3.8]

    start_time = time.perf_counter()

    for i in range(10000):
        v_class = classes[i % 13]
        depth = depths[i % 5]
        wave = waves[i % 5]
        calculate_grounding_risk(v_class, channel_depth_m=depth, wave_height_m=wave)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    print(f"\n10,000 calculations completed in {elapsed_ms:.2f} ms")
    assert elapsed_ms < 100.0, f"Expected < 100ms, took {elapsed_ms:.2f}ms"
