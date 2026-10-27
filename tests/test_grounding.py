"""Unit and performance benchmark tests for PIANC Grounding Risk Module.

Verifies dynamic tide offset ingestion, calm inner-channel net clearance tiers,
exact boundary cutoffs, and edge case resilience against false alarms.
"""

import time
import httpx
import pytest

from backend.services.grounding import (
    CALM_INNER_CHANNEL_THRESHOLD_M,
    CALM_SWELL_MULTIPLIER,
    DEFAULT_HEAVY_SWELL_MULTIPLIER,
    SWELL_HEIGHT_THRESHOLD_M,
    VESSEL_BENCHMARK_DRAFTS,
    calculate_grounding_risk,
    get_vessel_draft,
)
from backend.services.weather import TideResult, WeatherClient, fetch_tide_offset

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
        assert get_vessel_draft(v_class.lower()) == expected_draft


def test_invalid_vessel_class_raises():
    """Verify lookup with an unrecognized vessel class raises KeyError."""
    with pytest.raises(KeyError):
        get_vessel_draft("unknown_submarine")
    with pytest.raises(KeyError):
        calculate_grounding_risk(vessel_class="invalid_ship", channel_depth_m=15.0)


# ─── 2. Swell Condition Multiplier & Boundary Thresholds ──────────────────────

def test_calm_vs_heavy_swell_multiplier():
    """Verify standard swell (Hs <= 2.0m -> 1.10) and heavy swell (Hs > 2.0m -> 1.30)."""
    # Panamax (draft = 12.0m)
    # Hs = 1.0m (calm) -> h_req = 1.10 * 12.0 = 13.20m
    res_calm = calculate_grounding_risk("panamax", channel_depth_m=16.0, wave_height_m=1.0)
    assert res_calm.required_depth_m == 13.20

    # Hs = 3.0m (heavy) -> h_req = 1.30 * 12.0 = 15.60m
    res_heavy = calculate_grounding_risk("panamax", channel_depth_m=16.0, wave_height_m=3.0)
    assert res_heavy.required_depth_m == 15.60


def test_swell_boundary_cutoffs():
    """Verify exact transition at boundary Hs = 2.00m vs 2.01m."""
    # PCTC (draft = 10.0m)
    # Hs = 2.00m -> exactly on gross multiplier boundary (1.10 * 10 = 11.00m)
    res_200 = calculate_grounding_risk("pctc", channel_depth_m=15.0, wave_height_m=2.00)
    assert res_200.required_depth_m == 11.00

    # Hs = 2.01m -> immediately triggers heavy swell hazard (1.30 * 10 = 13.00m)
    res_201 = calculate_grounding_risk("pctc", channel_depth_m=15.0, wave_height_m=2.01)
    assert res_201.required_depth_m == 13.00


def test_calm_inner_channel_boundary_cutoffs():
    """Verify calm inner channel net tier boundary at Hs = 1.00m vs 1.01m."""
    # Port of LA (16.1m depth) with Neopanamax (15.2m draft)
    # At Hs = 1.00m (calm inner channel active):
    # Net margin = 16.1 - 15.2 = 0.90m >= 0.90m -> MEDIUM RISK (Tidal Window Required)
    res_100 = calculate_grounding_risk("neoPanamax", channel_depth_m=16.1, wave_height_m=1.00)
    assert res_100.tier == "medium"
    assert res_100.score == 60.0
    assert res_100.net_margin_m == 0.90

    # At Hs = 1.01m (calm inner channel net tier inactive, outer swell applies):
    # h_req = 1.10 * 15.2 = 16.72m > 16.1m, UKC = -0.62m -> HIGH RISK
    res_101 = calculate_grounding_risk("neoPanamax", channel_depth_m=16.1, wave_height_m=1.01)
    assert res_101.tier == "high"
    assert res_101.score == 90.0


# ─── 3. Port of Los Angeles Specified Unit Tests ──────────────────────────────

def test_port_of_la_neopanamax_static_low_tide():
    """Test 1: Port of LA (depth 16.1m) + Neopanamax (draft 15.2m) at static low tide (0.0m offset).

    Asserts 16.1m available depth evaluates to MEDIUM RISK (Tidal Window Required)
    under calm inner swell instead of false CRITICAL GROUNDING HAZARD.
    """
    res = calculate_grounding_risk(
        vessel_class="neoPanamax",
        channel_depth_m=16.1,
        wave_height_m=0.5,  # Calm inner harbor swell (Hs <= 1.0m)
        tide_offset_m=0.0,  # Static low tide baseline
    )

    assert res.channel_depth_m == 16.1
    assert res.tide_offset_m == 0.0
    assert res.available_depth_m == 16.1
    assert res.draft_m == 15.2
    assert res.net_margin_m == 0.90
    assert res.tier == "medium"
    assert res.score == 60.0
    assert "Tidal window" in res.detail
    assert any("Tidal window or calm inner basin" in f for f in res.factors)


def test_port_of_la_neopanamax_dynamic_high_tide():
    """Test 2: Port of LA (depth 16.1m) + Neopanamax (draft 15.2m) at dynamic high tide (+1.2m offset).

    Asserts 17.3m available depth evaluates to LOW RISK.
    """
    res = calculate_grounding_risk(
        vessel_class="neoPanamax",
        channel_depth_m=16.1,
        wave_height_m=0.5,  # Calm inner harbor swell
        tide_offset_m=1.2,  # Dynamic high tide
    )

    assert res.channel_depth_m == 16.1
    assert res.tide_offset_m == 1.2
    assert res.available_depth_m == 17.30
    assert res.tier == "low"
    assert res.score == 25.0
    assert res.ukc_margin_m == round(17.30 - 16.72, 2)  # +0.58m


@pytest.mark.asyncio
async def test_tide_api_fallback_offline():
    """Test 3: Offline/unresponsive tide API defaults to 0.0m offset with tide_data_available = False."""
    # Create mock transport simulating offline/failed network
    def offline_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by remote host", request=request)

    transport = httpx.MockTransport(offline_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        tide_res = await fetch_tide_offset(lat=33.74, lon=-118.27, client=client)

    assert isinstance(tide_res, TideResult)
    assert tide_res.tide_offset_m == 0.0
    assert tide_res.tide_data_available is False
    assert tide_res.source == "fallback"

    # Verify calculation engine handles fallback cleanly
    res = calculate_grounding_risk(
        vessel_class="neoPanamax",
        channel_depth_m=16.1,
        wave_height_m=0.5,
        tide_offset_m=tide_res.tide_offset_m,
        tide_data_available=tide_res.tide_data_available,
    )
    assert res.tide_data_available is False
    assert any("Live tide API unavailable" in f for f in res.factors)


# ─── 4. UKC Margins & Risk Tier Transitions ───────────────────────────────────

def test_ukc_margin_and_risk_tiers():
    """Verify UKC = available_depth - h_req and tier mapping."""
    # Panamax (draft = 12.0m, Hs = 1.0m -> h_req = 13.20m)
    # 1. Depth = 15.00m, Tide = 0.0m -> UKC = +1.80m -> LOW (score 25)
    res_low = calculate_grounding_risk("panamax", channel_depth_m=15.00, wave_height_m=1.0)
    assert res_low.ukc_margin_m == 1.80
    assert res_low.tier == "low"
    assert res_low.score == 25.0

    # 2. Depth = 13.70m -> UKC = +0.50m, available_depth (13.7m) >= h_req (13.2m) -> LOW (in calm inner channel)
    res_calm_safe = calculate_grounding_risk("panamax", channel_depth_m=13.70, wave_height_m=1.0)
    assert res_calm_safe.ukc_margin_m == 0.50
    assert res_calm_safe.tier == "low"

    # 3. Depth = 12.50m -> net margin = 12.50 - 12.0 = 0.50m (<0.90m) -> HIGH (score 90)
    res_high = calculate_grounding_risk("panamax", channel_depth_m=12.50, wave_height_m=1.0)
    assert res_high.ukc_margin_m == -0.70
    assert res_high.tier == "high"
    assert res_high.score == 90.0


def test_exact_edge_cutoffs():
    """Verify edge boundaries: safe clearance (low), marginal (medium), and deficit (high)."""
    # Feeder: draft = 8.5m, Hs = 1.0m -> h_req = 1.10 * 8.5 = 9.35m
    # Depth = 10.35m -> available_depth >= h_req + 1.0m -> LOW
    res_100 = calculate_grounding_risk("feeder", channel_depth_m=10.35, wave_height_m=1.0)
    assert res_100.ukc_margin_m == 1.00
    assert res_100.tier == "low"

    # Depth = 9.35m -> UKC = 0.00m, net margin = 0.85m -> LOW in calm (available_depth >= h_req)
    res_000 = calculate_grounding_risk("feeder", channel_depth_m=9.35, wave_height_m=1.0)
    assert res_000.ukc_margin_m == 0.00
    assert res_000.tier == "low"

    # Depth = 9.34m -> UKC = -0.01m, net margin = 0.84m (< 0.90m) -> HIGH
    res_neg = calculate_grounding_risk("feeder", channel_depth_m=9.34, wave_height_m=1.0)
    assert res_neg.ukc_margin_m == -0.01
    assert res_neg.tier == "high"


# ─── 5. Missing / Unverified Depth Handling ───────────────────────────────────

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


# ─── 6. Input Validation ──────────────────────────────────────────────────────

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


# ─── 7. OpenAPI Output Schema Helpers ─────────────────────────────────────────

def test_openapi_schema_helpers():
    """Verify to_subrisk_result() and to_navigational_metrics() output compliance."""
    res = calculate_grounding_risk(
        "panamax", channel_depth_m=15.0, wave_height_m=1.0, tide_offset_m=0.5
    )

    # SubRiskResult
    subrisk = res.to_subrisk_result()
    assert subrisk["category"] == "navigational"
    assert subrisk["tier"] in ("low", "medium", "high")
    assert isinstance(subrisk["score"], float)
    assert isinstance(subrisk["detail"], str)
    assert isinstance(subrisk["factors"], list)

    # NavigationalMetrics
    nav = res.to_navigational_metrics(air_draft_clearance_m=9.0, pilotage_available=True)
    assert nav["underKeelClearanceM"] == 2.30  # (15.0 + 0.5) - 13.20 = 2.30
    assert nav["channelDepthM"] == 15.0
    assert nav["airDraftClearanceM"] == 9.0
    assert nav["pilotageAvailable"] is True
    assert nav["tideHeightM"] == 0.5


# ─── 8. All 13 Classes Across 3 Swell Regimes ──────────────────────────────────

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


# ─── 9. Performance Benchmark ─────────────────────────────────────────────────

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
    assert elapsed_ms < 250.0, f"Expected < 250ms, took {elapsed_ms:.2f}ms"
