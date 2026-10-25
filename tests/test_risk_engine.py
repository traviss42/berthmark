"""Unit tests for Weakest-Link Overall Risk Engine and transaction guarantees."""

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import AlertLog, Base, Port, PortRiskSnapshot, User, UserWatchlist
from backend.schemas.metrics import (
    CongestionMetrics,
    NavigationalMetrics,
    PortMetrics,
    SubRiskResult,
    TerminalMetrics,
    WeatherMetrics,
)
from backend.schemas.risk import SubRisksDict
from backend.services.risk_engine import (
    VALID_VESSEL_CLASSES,
    VESSEL_CLASS_LABELS,
    assemble_risk_assessment,
    determine_composite_tier,
    evaluate_weather_risk,
    persist_risk_assessment,
)
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def test_db_session():
    """Create in-memory SQLite database session with schemas and vessel classes seeded."""
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
        await seed_vessel_classes(session)
        yield session

    await engine.dispose()


def make_subrisk(category: str, tier: str, score: float) -> SubRiskResult:
    """Helper to generate a valid SubRiskResult."""
    return SubRiskResult(
        category=category,  # type: ignore[arg-type]
        tier=tier,  # type: ignore[arg-type]
        score=score,
        detail=f"{category} assessment at {tier} tier.",
        factors=[f"Factor for {category} {tier}"],
    )


def test_weakest_link_escalation_rules():
    """Verify weakest-link escalation: any HIGH elevates composite to HIGH, etc."""
    # 1. Congestion HIGH, others LOW -> HIGH
    sr_cong_high = SubRisksDict(
        congestion=make_subrisk("congestion", "high", 90.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    tier, score = determine_composite_tier(sr_cong_high)
    assert tier == "high"
    assert score == 90.0

    # 2. Weather HIGH, others LOW -> HIGH
    sr_wx_high = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 25.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "high", 90.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    tier, score = determine_composite_tier(sr_wx_high)
    assert tier == "high"
    assert score == 90.0

    # 3. Navigational HIGH, others LOW -> HIGH
    sr_nav_high = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 25.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "high", 95.0),
    )
    tier, score = determine_composite_tier(sr_nav_high)
    assert tier == "high"
    assert score == 95.0

    # 4. Terminal HIGH, others LOW -> HIGH
    sr_term_high = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 25.0),
        terminalDelays=make_subrisk("terminalDelays", "high", 88.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    tier, score = determine_composite_tier(sr_term_high)
    assert tier == "high"
    assert score == 88.0

    # 5. All LOW -> LOW
    sr_all_low = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 20.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 15.0),
        navigational=make_subrisk("navigational", "low", 22.0),
    )
    tier, score = determine_composite_tier(sr_all_low)
    assert tier == "low"
    assert score == 25.0

    # 6. One MEDIUM with others LOW -> MEDIUM
    sr_one_med = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 25.0),
        terminalDelays=make_subrisk("terminalDelays", "medium", 60.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    tier, score = determine_composite_tier(sr_one_med)
    assert tier == "medium"
    assert score == 60.0

    # 7. Multiple HIGH hazards -> HIGH, max score preserved
    sr_multi_high = SubRisksDict(
        congestion=make_subrisk("congestion", "high", 85.0),
        terminalDelays=make_subrisk("terminalDelays", "medium", 60.0),
        weather=make_subrisk("weather", "high", 92.5),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    tier, score = determine_composite_tier(sr_multi_high)
    assert tier == "high"
    assert score == 92.5


def test_vessel_labels_and_assessment_assembly():
    """Verify human-readable labels, assessment id format, and schema validation."""
    for vc in VALID_VESSEL_CLASSES:
        assert vc in VESSEL_CLASS_LABELS
        assert len(VESSEL_CLASS_LABELS[vc]) > 0

    assert VESSEL_CLASS_LABELS["neoPanamax"] == "Neo-Panamax"
    assert VESSEL_CLASS_LABELS["vlcc"] == "VLCC"
    assert VESSEL_CLASS_LABELS["mrTanker"] == "MR Tanker"

    sub_risks = SubRisksDict(
        congestion=make_subrisk("congestion", "medium", 60.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )

    port_metrics = PortMetrics(
        portId="port-rotterdam",
        timestamp=datetime(2026, 10, 19, 3, 0, 0, tzinfo=timezone.utc),
        congestion=CongestionMetrics(
            anchorageQueueCount=8,
            avgWaitingTimeHours=14.0,
            berthOccupancyPct=75.0,
            rolling30dAvgQueue=7.0,
            rolling30dAvgWaitHours=12.0,
        ),
        terminal=TerminalMetrics(
            berthTurnaroundHours=25.0,
            berthToAnchorageWaitRatio=1.79,
            dwellTimeAnomalyScore=38.6,
            rolling30dAvgTurnaround=22.0,
        ),
        weather=WeatherMetrics(
            windSpeedKnots=15.0,
            waveHeightM=1.2,
            swellPeriodSec=7.0,
            visibilityNm=8.0,
            gustSpeedKnots=20.0,
        ),
        navigational=NavigationalMetrics(
            underKeelClearanceM=2.5,
            channelDepthM=16.5,
            airDraftClearanceM=8.0,
            pilotageAvailable=True,
            tideHeightM=0.5,
        ),
    )

    ts = datetime(2026, 10, 19, 3, 0, 0, tzinfo=timezone.utc)
    assessment = assemble_risk_assessment(
        port_id="port-rotterdam",
        port_name="Port of Rotterdam",
        vessel_class="neoPanamax",
        sub_risks=sub_risks,
        metrics=port_metrics,
        timestamp=ts,
    )

    assert assessment.id == "risk-port-rotterdam-neoPanamax-2026-10-19T03:00:00Z"
    assert assessment.portId == "port-rotterdam"
    assert assessment.portName == "Port of Rotterdam"
    assert assessment.vesselClass == "neoPanamax"
    assert assessment.vesselClassLabel == "Neo-Panamax"
    assert assessment.compositeTier == "medium"
    assert assessment.compositeScore == 60.0


def test_evaluate_weather_risk_thresholds():
    """Verify weather sub-risk evaluation across low, medium, and high thresholds."""
    # Low weather
    wx_low = WeatherMetrics(
        windSpeedKnots=10.0,
        waveHeightM=1.0,
        swellPeriodSec=6.0,
        visibilityNm=10.0,
        gustSpeedKnots=15.0,
    )
    sr_low = evaluate_weather_risk(wx_low)
    assert sr_low.tier == "low"
    assert sr_low.score == 25.0

    # Medium weather (wave >= 1.5m)
    wx_med = WeatherMetrics(
        windSpeedKnots=12.0,
        waveHeightM=1.8,
        swellPeriodSec=8.0,
        visibilityNm=9.0,
        gustSpeedKnots=18.0,
    )
    sr_med = evaluate_weather_risk(wx_med)
    assert sr_med.tier == "medium"
    assert sr_med.score == 60.0

    # High weather (wind > 30 kts)
    wx_high = WeatherMetrics(
        windSpeedKnots=34.0,
        waveHeightM=1.2,
        swellPeriodSec=7.0,
        visibilityNm=5.0,
        gustSpeedKnots=45.0,
    )
    sr_high = evaluate_weather_risk(wx_high)
    assert sr_high.tier == "high"
    assert sr_high.score == 90.0


@pytest.mark.asyncio
async def test_atomic_persistence_and_alert_transition(test_db_session: AsyncSession):
    """Verify atomic transaction persistence, uppercase database mapping, and alert generation."""
    # Create test port
    port = Port(
        unlocode="TESTA",
        port_name="Test Alpha Port",
        country_code="US",
        subdivision_code="US-TX",
        latitude=29.5,
        longitude=-95.0,
        channel_depth_m=15.0,
    )
    test_db_session.add(port)
    await test_db_session.flush()

    # Create test user & watchlist entry
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="operator_test@berthmark.com",
        hashed_password="hashed_pw",
        name="Test Operator",
    )
    test_db_session.add(user)
    await test_db_session.flush()

    watchlist = UserWatchlist(
        user_id=user_id,
        unlocode="TESTA",
        vessel_class_id="neoPanamax",
    )
    test_db_session.add(watchlist)
    await test_db_session.flush()

    sub_risks_low = SubRisksDict(
        congestion=make_subrisk("congestion", "low", 25.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )

    port_metrics = PortMetrics(
        portId="port-testa",
        timestamp=datetime.now(timezone.utc),
        congestion=CongestionMetrics(
            anchorageQueueCount=2,
            avgWaitingTimeHours=4.0,
            berthOccupancyPct=40.0,
            rolling30dAvgQueue=3.0,
            rolling30dAvgWaitHours=5.0,
        ),
        terminal=TerminalMetrics(
            berthTurnaroundHours=20.0,
            berthToAnchorageWaitRatio=5.0,
            dwellTimeAnomalyScore=20.0,
            rolling30dAvgTurnaround=22.0,
        ),
        weather=WeatherMetrics(
            windSpeedKnots=10.0,
            waveHeightM=0.8,
            swellPeriodSec=6.0,
            visibilityNm=10.0,
            gustSpeedKnots=14.0,
        ),
        navigational=NavigationalMetrics(
            underKeelClearanceM=3.0,
            channelDepthM=15.0,
            airDraftClearanceM=10.0,
            pilotageAvailable=True,
            tideHeightM=0.0,
        ),
    )

    # 1. Initial evaluation: creates snapshot and initial alert log
    snap1, alerts1 = await persist_risk_assessment(
        session=test_db_session,
        port=port,
        vessel_class="neoPanamax",
        composite_tier="low",
        sub_risks=sub_risks_low,
        metrics=port_metrics,
        user_id=user_id,
    )
    assert snap1.overall_risk_level == "LOW"
    assert len(alerts1) == 1
    assert alerts1[0].new_risk_level == "LOW"
    assert alerts1[0].previous_risk_level is None

    # 2. Re-evaluating with same LOW tier does NOT create redundant alert log
    snap2, alerts2 = await persist_risk_assessment(
        session=test_db_session,
        port=port,
        vessel_class="neoPanamax",
        composite_tier="low",
        sub_risks=sub_risks_low,
        metrics=port_metrics,
        user_id=user_id,
    )
    assert snap2.overall_risk_level == "LOW"
    assert len(alerts2) == 0

    # 3. Transition to HIGH creates alert log with previous=LOW, new=HIGH
    sub_risks_high = SubRisksDict(
        congestion=make_subrisk("congestion", "high", 90.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    snap3, alerts3 = await persist_risk_assessment(
        session=test_db_session,
        port=port,
        vessel_class="neoPanamax",
        composite_tier="high",
        sub_risks=sub_risks_high,
        metrics=port_metrics,
        user_id=user_id,
    )
    assert snap3.overall_risk_level == "HIGH"
    assert len(alerts3) == 1
    assert alerts3[0].previous_risk_level == "LOW"
    assert alerts3[0].new_risk_level == "HIGH"


@pytest.mark.asyncio
async def test_atomic_rollback_on_persistence_error(test_db_session: AsyncSession):
    """Verify that a database error during alert creation cleanly rolls back snapshot changes."""
    port = Port(
        unlocode="TESTB",
        port_name="Test Bravo Port",
        country_code="US",
        subdivision_code="US-LA",
        latitude=29.9,
        longitude=-90.0,
        channel_depth_m=14.0,
    )
    test_db_session.add(port)
    await test_db_session.flush()

    sub_risks = SubRisksDict(
        congestion=make_subrisk("congestion", "high", 90.0),
        terminalDelays=make_subrisk("terminalDelays", "low", 25.0),
        weather=make_subrisk("weather", "low", 25.0),
        navigational=make_subrisk("navigational", "low", 25.0),
    )
    port_metrics = PortMetrics(
        portId="port-testb",
        timestamp=datetime.now(timezone.utc),
        congestion=CongestionMetrics(
            anchorageQueueCount=18,
            avgWaitingTimeHours=30.0,
            berthOccupancyPct=95.0,
            rolling30dAvgQueue=10.0,
            rolling30dAvgWaitHours=15.0,
        ),
        terminal=TerminalMetrics(
            berthTurnaroundHours=45.0,
            berthToAnchorageWaitRatio=1.5,
            dwellTimeAnomalyScore=60.0,
            rolling30dAvgTurnaround=22.0,
        ),
        weather=WeatherMetrics(
            windSpeedKnots=12.0,
            waveHeightM=0.8,
            swellPeriodSec=6.0,
            visibilityNm=10.0,
            gustSpeedKnots=15.0,
        ),
        navigational=NavigationalMetrics(
            underKeelClearanceM=1.5,
            channelDepthM=14.0,
            airDraftClearanceM=6.0,
            pilotageAvailable=True,
            tideHeightM=0.0,
        ),
    )

    # Force an integrity failure by creating an AlertLog with invalid FK or error
    # We will test that if an error occurs within the atomic block, snapshot is rolled back
    try:
        async with test_db_session.begin_nested():
            snapshot = PortRiskSnapshot(
                snapshot_id=uuid.uuid4(),
                unlocode="TESTB",
                vessel_class_id="neoPanamax",
                grounding_risk_level="LOW",
                anchored_vessel_count=18,
                underway_vessel_count=2,
                total_active_geofence_count=20,
                historical_avg_queue=10.0,
                queue_variance_pct=80.0,
                congestion_risk_level="HIGH",
                weather_risk_level="LOW",
                overall_risk_level="HIGH",
                swell_height_m=0.8,
                wind_speed_kts=12.0,
            )
            test_db_session.add(snapshot)
            # Simulated failure: invalid trigger reason or FK
            bad_alert = AlertLog(
                alert_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                unlocode="NONEXISTENT_PORT",  # Violates foreign key
                vessel_class_id="neoPanamax",
                previous_risk_level=None,
                new_risk_level="HIGH",
                trigger_reason="Simulated failure",
            )
            test_db_session.add(bad_alert)
            await test_db_session.flush()
    except Exception:
        # Expected rollback
        pass

    # Verify snapshot for TESTB was NOT persisted due to rollback
    check_stmt = select(PortRiskSnapshot).where(PortRiskSnapshot.unlocode == "TESTB")
    check_res = await test_db_session.execute(check_stmt)
    assert check_res.scalar_one_or_none() is None
