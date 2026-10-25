"""Unit and integration tests for Port Traffic Baselines and Congestion Risk Module."""

import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, Port, PortTrafficBaseline
from backend.services.baseline import (
    TrafficBaselineRepository,
    seed_traffic_baselines,
)
from backend.services.congestion import (
    assess_congestion_risk,
    calculate_queue_variance,
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
        session.add(port)
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


# ─── 3. Unit Tests: Cold-Start & Uninitialized States ──────────────────────────

def test_cold_start_handling():
    """Verify fallback to ship count thresholds when historical baseline is unavailable."""
    # Low count in cold-start
    res_low = assess_congestion_risk(anchored_count=3, hist_avg_anchored=None)
    assert res_low.is_cold_start is True
    assert res_low.tier == "low"
    assert res_low.score == 25.0
    assert "cold-start" in res_low.detail

    # Medium count in cold-start
    res_med = assess_congestion_risk(anchored_count=10, hist_avg_anchored=None)
    assert res_med.is_cold_start is True
    assert res_med.tier == "medium"
    assert res_med.score == 60.0

    # High count in cold-start
    res_high = assess_congestion_risk(anchored_count=18, hist_avg_anchored=None)
    assert res_high.is_cold_start is True
    assert res_high.tier == "high"
    assert res_high.score == 90.0


def test_uninitialized_live_count():
    """Verify safe default when live anchored count is None (prior to AIS aggregation)."""
    res = assess_congestion_risk(anchored_count=None, hist_avg_anchored=10.0)
    assert res.tier == "low"
    assert res.score == 25.0
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

    # CongestionMetrics
    metrics = res.to_congestion_metrics()
    assert metrics["anchorageQueueCount"] == 18
    assert metrics["rolling30dAvgQueue"] == 11.6
    assert metrics["avgWaitingTimeHours"] > 0
    assert 0 <= metrics["berthOccupancyPct"] <= 100


# ─── 5. Integration Tests: Repository CRUD & Seeding ───────────────────────────

@pytest.mark.asyncio
async def test_baseline_repository_crud(baseline_test_db):
    """Verify TrafficBaselineRepository get, get_current, and upsert operations."""
    session_factory = baseline_test_db

    async with session_factory() as session:
        # 1. Non-existent slot returns None
        rec = await TrafficBaselineRepository.get_baseline(session, "NLRTM", 1, 14)
        assert rec is None

        # 2. Upsert new record (Monday=1, 14:00)
        created = await TrafficBaselineRepository.upsert_baseline(
            session, "NLRTM", day_of_week=1, hour_of_day=14, avg_anchored=15.5, avg_underway=8.0
        )
        assert created.unlocode == "NLRTM"
        assert created.avg_anchored_count == 15.5
        assert created.avg_underway_count == 8.0
        assert created.avg_total_active == 23.5

        # 3. Retrieve using get_baseline
        retrieved = await TrafficBaselineRepository.get_baseline(session, "NLRTM", 1, 14)
        assert retrieved is not None
        assert retrieved.avg_anchored_count == 15.5

        # 4. Upsert update existing slot
        updated = await TrafficBaselineRepository.upsert_baseline(
            session, "NLRTM", day_of_week=1, hour_of_day=14, avg_anchored=18.0, avg_underway=10.0
        )
        assert updated.baseline_id == created.baseline_id
        assert updated.avg_anchored_count == 18.0

        # 5. Timestamp-aware lookup
        # Monday at 14:30 UTC
        ts = datetime(2026, 10, 26, 14, 30, tzinfo=timezone.utc)  # Oct 26 2026 is Monday
        current = await TrafficBaselineRepository.get_current_baseline(session, "NLRTM", timestamp=ts)
        assert current is not None
        assert current.avg_anchored_count == 18.0

        # 6. Invalid day/hour raises ValueError
        with pytest.raises(ValueError):
            await TrafficBaselineRepository.get_baseline(session, "NLRTM", -1, 10)
        with pytest.raises(ValueError):
            await TrafficBaselineRepository.get_baseline(session, "NLRTM", 1, 24)


@pytest.mark.asyncio
async def test_seed_traffic_baselines_idempotency(baseline_test_db):
    """Verify seed_traffic_baselines populates all 168 slots per port and is idempotent."""
    session_factory = baseline_test_db

    async with session_factory() as session:
        # Initial seed
        count1 = await seed_traffic_baselines(session)
        assert count1 == 5 * 168  # 5 benchmark ports * 168 slots

        # Second seed (idempotent update)
        count2 = await seed_traffic_baselines(session)
        assert count2 == 5 * 168

        # Verify Rotterdam slot (Sunday=0, 12:00)
        rtm_slot = await TrafficBaselineRepository.get_baseline(session, "NLRTM", 0, 12)
        assert rtm_slot is not None
        assert rtm_slot.avg_anchored_count > 0.0
        assert rtm_slot.avg_total_active == round(rtm_slot.avg_anchored_count + rtm_slot.avg_underway_count, 1)
