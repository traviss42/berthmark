"""Unit and integration tests for Port Traffic Baselines and Congestion Risk Module."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, Port, PortRiskSnapshot, PortTrafficBaseline, VesselClass
from backend.services.congestion import (
    assess_congestion_risk,
    calculate_queue_variance,
    get_baseline_slot,
    get_port_traffic_baseline,
    get_rolling_congestion_baseline,
    update_port_traffic_baseline_from_observation,
)


@pytest_asyncio.fixture
async def baseline_test_db():
    """Create in-memory SQLite database seeded with sample port."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        port = Port(
            unlocode="NLRTM",
            port_name="Port of Rotterdam",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.9244,
            longitude=4.4777,
            channel_depth_m=11.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        vc = VesselClass(
            class_id="panamax",
            class_name="Panamax",
            draft_m=12.0,
            beam_m=32.2,
            loa_m=225.0,
        )
        session.add(port)
        session.add(vc)
        await session.commit()

    yield session_factory
    await engine.dispose()


# ─── 1. Unit Tests: Queue Variance Calculation ──────────────────────────────────

def test_queue_variance_calculation_formula():
    """Verify calculate_queue_variance accurately calculates positive, negative, and zero variances."""
    # Equal -> 0.0%
    assert calculate_queue_variance(10, 10.0) == 0.0

    # Positive variance: 15 vs 10.0 -> +50.0%
    assert calculate_queue_variance(15, 10.0) == 50.0

    # Negative variance: 5 vs 10.0 -> -50.0%
    assert calculate_queue_variance(5, 10.0) == -50.0

    # Slight variance rounded to 2 decimals: 13 vs 12.0 -> +8.33%
    assert calculate_queue_variance(13, 12.0) == 8.33


def test_queue_variance_zero_division():
    """Verify zero-division handling when baseline is 0.0."""
    # Baseline 0.0 and queue 0 -> 0.0%
    assert calculate_queue_variance(0, 0.0) == 0.0

    # Baseline 0.0 and queue > 0 -> capped at +100.0%
    assert calculate_queue_variance(4, 0.0) == 100.0
    assert calculate_queue_variance(1, 0.0) == 100.0


# ─── 2. Unit Tests: Congestion Risk Categorization & Boundaries ─────────────────

def test_congestion_risk_count_boundaries():
    """Verify LOW/MEDIUM (5 vs 6) and MEDIUM/HIGH (15 vs 16) count thresholds."""
    # Low/Medium boundary with neutral variance
    res_5 = assess_congestion_risk(anchored_count=5, hist_avg_anchored=4.17)  # ΔQ = +20%
    assert res_5.tier == "low"
    assert res_5.score == 25.0

    res_6 = assess_congestion_risk(anchored_count=6, hist_avg_anchored=5.0)   # ΔQ = +20%
    assert res_6.tier == "medium"
    assert res_6.score == 60.0

    # Medium/High boundary with neutral variance
    res_15 = assess_congestion_risk(anchored_count=15, hist_avg_anchored=12.5) # ΔQ = +20%
    assert res_15.tier == "medium"
    assert res_15.score == 60.0

    res_16 = assess_congestion_risk(anchored_count=16, hist_avg_anchored=13.3) # ΔQ = +20%
    assert res_16.tier == "high"
    assert res_16.score == 90.0


def test_congestion_risk_variance_boundaries():
    """Verify LOW/MEDIUM (+29% vs +30%) and MEDIUM/HIGH (+75% vs +76%) variance thresholds."""
    # N = 4 (in 0-5 low count range)
    # ΔQ = +29.0% -> LOW
    res_29 = assess_congestion_risk(anchored_count=4, hist_avg_anchored=3.10)  # ~+29%
    assert res_29.tier == "low"

    # ΔQ = +30.0% -> MEDIUM
    res_30 = assess_congestion_risk(anchored_count=4, hist_avg_anchored=3.0769) # +30.0%
    assert res_30.tier == "medium"

    # ΔQ = +75.0% -> MEDIUM
    res_75 = assess_congestion_risk(anchored_count=4, hist_avg_anchored=2.2857) # +75.0%
    assert res_75.tier == "medium"

    # ΔQ = +76.0% -> HIGH
    res_76 = assess_congestion_risk(anchored_count=4, hist_avg_anchored=2.2727) # +76.0%
    assert res_76.tier == "high"


def test_hierarchical_conflicting_signals():
    """Verify high hazard signals dominate conflicting signals."""
    # Low count (3) but severe variance (+85%) -> HIGH
    res_surge = assess_congestion_risk(anchored_count=3, hist_avg_anchored=1.62)
    assert res_surge.tier == "high"
    assert res_surge.score == 90.0

    # High count (19) but negative variance (-25%) -> HIGH
    res_drop = assess_congestion_risk(anchored_count=19, hist_avg_anchored=25.33)
    assert res_drop.tier == "high"
    assert res_drop.score == 90.0

    # Medium count (10) but negative variance (-40%) -> MEDIUM
    res_med_drop = assess_congestion_risk(anchored_count=10, hist_avg_anchored=16.67)
    assert res_med_drop.tier == "medium"
    assert res_med_drop.score == 60.0


# ─── 3. Unit Tests: Cold-Start & Missing Baseline Fallbacks ────────────────────

def test_cold_start_handling():
    """Verify fallback solely to ship count thresholds when historical baseline is absent."""
    # Low count in cold-start (0-5 -> LOW)
    res_low = assess_congestion_risk(anchored_count=3, hist_avg_anchored=None)
    assert res_low.is_cold_start is True
    assert res_low.tier == "low"
    assert res_low.score == 25.0
    assert res_low.queue_variance_pct is None
    assert "baseline collecting" in res_low.detail

    # Medium count in cold-start (6-15 -> MEDIUM)
    res_med = assess_congestion_risk(anchored_count=10, hist_avg_anchored=None)
    assert res_med.is_cold_start is True
    assert res_med.tier == "medium"
    assert res_med.score == 60.0
    assert res_med.queue_variance_pct is None

    # High count in cold-start (>15 -> HIGH)
    res_high = assess_congestion_risk(anchored_count=18, hist_avg_anchored=None)
    assert res_high.is_cold_start is True
    assert res_high.tier == "high"
    assert res_high.score == 90.0
    assert res_high.queue_variance_pct is None


def test_uninitialized_live_count():
    """Verify safe default when live anchored count is None (prior to AIS aggregation)."""
    res = assess_congestion_risk(anchored_count=None, hist_avg_anchored=10.0)
    assert res.tier == "low"
    assert res.score == 25.0
    assert res.queue_variance_pct is None
    assert "Initializing live traffic" in res.detail


# ─── 4. Unit Tests: OpenAPI Output Schema Helpers ──────────────────────────────

def test_openapi_output_schema_helpers():
    """Verify to_subrisk_result() and to_congestion_metrics() conform to OpenAPI schemas."""
    res = assess_congestion_risk(anchored_count=18, hist_avg_anchored=11.6, underway_count=6)

    # SubRiskResult
    subrisk = res.to_subrisk_result()
    assert subrisk["category"] == "congestion"
    assert subrisk["tier"] == "high"
    assert subrisk["score"] == 90.0
    assert isinstance(subrisk["detail"], str)
    assert len(subrisk["factors"]) >= 2

    # CongestionMetrics with baseline present
    metrics = res.to_congestion_metrics()
    assert metrics["anchorageQueueCount"] == 18
    assert metrics["rolling30dAvgQueue"] == 11.6
    assert metrics["avgWaitingTimeHours"] > 0
    assert 0 <= metrics["berthOccupancyPct"] <= 100

    # CongestionMetrics without baseline -> rolling30dAvgQueue is None
    cold_res = assess_congestion_risk(anchored_count=4, hist_avg_anchored=None)
    cold_metrics = cold_res.to_congestion_metrics()
    assert cold_metrics["rolling30dAvgQueue"] is None


# ─── 5. Integration Tests: True Rolling Average Accumulation ───────────────────

@pytest.mark.asyncio
async def test_baseline_repository_crud_and_rolling_updates(baseline_test_db):
    """Verify get_baseline_slot and update_port_traffic_baseline_from_observation."""
    session_factory = baseline_test_db

    async with session_factory() as session:
        # 1. Non-existent slot returns None
        rec = await get_baseline_slot(session, "NLRTM", day_of_week=1, hour_of_day=14)
        assert rec is None

        # 2. First real observation creates slot using observed real numbers
        ts = datetime(2026, 10, 26, 14, 30, tzinfo=timezone.utc)  # Monday=1, 14:00
        created = await update_port_traffic_baseline_from_observation(
            session,
            unlocode="NLRTM",
            anchored_count=15,
            underway_count=8,
            total_count=23,
            timestamp=ts,
        )
        assert created.unlocode == "NLRTM"
        assert created.day_of_week == 1
        assert created.hour_of_day == 14
        assert created.avg_anchored_count == 15.0
        assert created.avg_underway_count == 8.0
        assert created.avg_total_active == 23.0

        # 3. Retrieve using timestamp lookup
        current = await get_port_traffic_baseline(session, "NLRTM", timestamp=ts)
        assert current is not None
        assert current.avg_anchored_count == 15.0

        # 4. Second real observation updates rolling average using EMA (alpha=0.1)
        # new_avg = (1 - 0.1) * 15.0 + 0.1 * 25 = 13.5 + 2.5 = 16.0
        updated = await update_port_traffic_baseline_from_observation(
            session,
            unlocode="NLRTM",
            anchored_count=25,
            underway_count=18,
            total_count=43,
            timestamp=ts,
            alpha=0.1,
        )
        assert updated.baseline_id == created.baseline_id
        assert updated.avg_anchored_count == 16.0
        assert updated.avg_underway_count == 9.0
        assert updated.avg_total_active == 25.0

        # 5. Invalid day/hour raises ValueError
        with pytest.raises(ValueError):
            await get_baseline_slot(session, "NLRTM", -1, 10)
        with pytest.raises(ValueError):
            await get_baseline_slot(session, "NLRTM", 1, 24)


@pytest.mark.asyncio
async def test_no_synthetic_data_in_fresh_database(baseline_test_db):
    """Verify that a fresh port has zero baseline rows and evaluates cleanly to None variance."""
    session_factory = baseline_test_db

    async with session_factory() as session:
        # Check no baselines exist for Rotterdam
        stmt = select(PortTrafficBaseline).where(PortTrafficBaseline.unlocode == "NLRTM")
        rows = (await session.execute(stmt)).scalars().all()
        assert len(rows) == 0

        # Lookup returns None
        baseline = await get_port_traffic_baseline(session, "NLRTM")
        assert baseline is None

        # Assessment produces None variance and falls back to count threshold
        assessment = assess_congestion_risk(anchored_count=4, hist_avg_anchored=None)
        assert assessment.queue_variance_pct is None
        assert assessment.tier == "low"
        assert assessment.score == 25.0


@pytest.mark.asyncio
async def test_get_rolling_congestion_baseline_refinement(baseline_test_db):
    """Verify empirical baseline refines dynamically as days go on up to 30 days."""
    session_factory = baseline_test_db
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        # 1. Day 1: Single observation
        snap1 = PortRiskSnapshot(
            snapshot_id=uuid.uuid4(),
            unlocode="NLRTM",
            vessel_class_id="panamax",
            anchored_vessel_count=10,
            underway_vessel_count=5,
            total_active_geofence_count=15,
            historical_avg_queue=0.0,
            queue_variance_pct=0.0,
            congestion_risk_level="LOW",
            updated_at=now - timedelta(days=20),
        )
        session.add(snap1)
        await session.commit()

        avg_queue, days_collected = await get_rolling_congestion_baseline(
            session, "NLRTM", timestamp=now, max_days=30
        )
        assert avg_queue == 10.0
        assert days_collected == 1

        # 2. Add Day 2 observation (14 anchored)
        snap2 = PortRiskSnapshot(
            snapshot_id=uuid.uuid4(),
            unlocode="NLRTM",
            vessel_class_id="panamax",
            anchored_vessel_count=14,
            underway_vessel_count=6,
            total_active_geofence_count=20,
            historical_avg_queue=10.0,
            queue_variance_pct=0.0,
            congestion_risk_level="LOW",
            updated_at=now - timedelta(days=10),
        )
        session.add(snap2)
        await session.commit()

        avg_queue, days_collected = await get_rolling_congestion_baseline(
            session, "NLRTM", timestamp=now, max_days=30
        )
        # Average: (10 + 14) / 2 = 12.0 over 2 distinct days
        assert avg_queue == 12.0
        assert days_collected == 2

        # 3. Add Day 3 observation (18 anchored)
        snap3 = PortRiskSnapshot(
            snapshot_id=uuid.uuid4(),
            unlocode="NLRTM",
            vessel_class_id="panamax",
            anchored_vessel_count=18,
            underway_vessel_count=7,
            total_active_geofence_count=25,
            historical_avg_queue=12.0,
            queue_variance_pct=0.0,
            congestion_risk_level="MEDIUM",
            updated_at=now - timedelta(days=1),
        )
        session.add(snap3)
        await session.commit()

        avg_queue, days_collected = await get_rolling_congestion_baseline(
            session, "NLRTM", timestamp=now, max_days=30
        )
        # Average: (10 + 14 + 18) / 3 = 14.0 over 3 distinct days
        assert avg_queue == 14.0
        assert days_collected == 3

        # 4. Observation older than 30 days is excluded
        snap_old = PortRiskSnapshot(
            snapshot_id=uuid.uuid4(),
            unlocode="NLRTM",
            vessel_class_id="panamax",
            anchored_vessel_count=100,
            underway_vessel_count=50,
            total_active_geofence_count=150,
            historical_avg_queue=0.0,
            queue_variance_pct=0.0,
            congestion_risk_level="HIGH",
            updated_at=now - timedelta(days=45),  # Beyond 30-day cutoff
        )
        session.add(snap_old)
        await session.commit()

        avg_queue, days_collected = await get_rolling_congestion_baseline(
            session, "NLRTM", timestamp=now, max_days=30
        )
        # Excludes 100 from day 45; average remains 14.0 over 3 days
        assert avg_queue == 14.0
        assert days_collected == 3


def test_cold_start_initialization_window_and_transition():
    """Verify 10-15 minute initial count window and transition to live traffic counts."""
    # 1. During 15-minute ping collection window (cold-start)
    init_res = assess_congestion_risk(
        anchored_count=None,
        hist_avg_anchored=None,
        is_initializing=True,
    )
    assert init_res.is_initializing is True
    assert init_res.is_cold_start is True
    assert init_res.tier == "low"
    assert init_res.score == 25.0
    assert "Initializing live traffic" in init_res.detail

    init_metrics = init_res.to_congestion_metrics()
    assert init_metrics["isInitializing"] is True
    assert init_metrics["isColdStart"] is True
    assert init_metrics["rolling30dAvgQueue"] is None
    assert init_metrics["anchorageQueueCount"] == 0

    # 2. Transition after 15 minutes: live counts recorded (14 Anchored, 6 Underway)
    live_res = assess_congestion_risk(
        anchored_count=14,
        hist_avg_anchored=11.2,
        underway_count=6,
        is_initializing=False,
        baseline_days_collected=5,
    )
    assert live_res.is_initializing is False
    assert live_res.is_cold_start is True  # 5 days < 30 days: refining baseline
    assert live_res.baseline_days_collected == 5
    assert live_res.anchored_count == 14
    assert live_res.underway_count == 6

    live_metrics = live_res.to_congestion_metrics()
    assert live_metrics["isInitializing"] is False
    assert live_metrics["isColdStart"] is True
    assert live_metrics["anchorageQueueCount"] == 14
    assert live_metrics["underwayCount"] == 6
    assert live_metrics["baselineDaysCollected"] == 5
    assert live_metrics["rolling30dAvgQueue"] == 11.2
