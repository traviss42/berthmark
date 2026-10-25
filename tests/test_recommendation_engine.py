"""Unit and integration tests for Automated Alternative Port Recommendation Engine (Issue 17)."""

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, Port, PortRiskSnapshot
from backend.schemas.recommendation import AlternativePortRecommendation
from backend.services.recommendation import (
    BENCHMARK_VESSEL_DRAFTS,
    calculate_haversine_distance_nm,
    calculate_required_depth_m,
    recommend_alternative_ports,
)
from backend.taxonomy.seed import seed_vessel_classes


@pytest_asyncio.fixture
async def rec_test_db():
    """Create in-memory SQLite database seeded with vessel classes and regional port clusters."""
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

        # Primary port: Rotterdam in NL-ZH
        nlrtm = Port(
            unlocode="NLRTM",
            port_name="Port of Rotterdam",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.9244,
            longitude=4.4777,
            channel_depth_m=16.5,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Deep candidate in same subdivision NL-ZH, ~15 NM away
        deep_cand1 = Port(
            unlocode="NLD01",
            port_name="Deep Alternative 1",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.95,
            longitude=4.15,
            channel_depth_m=18.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Medium depth candidate in same subdivision NL-ZH, ~25 NM away
        deep_cand2 = Port(
            unlocode="NLD02",
            port_name="Deep Alternative 2",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=52.10,
            longitude=4.30,
            channel_depth_m=17.5,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Candidate 3 in same subdivision NL-ZH, ~35 NM away
        deep_cand3 = Port(
            unlocode="NLD03",
            port_name="Deep Alternative 3",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=52.20,
            longitude=4.40,
            channel_depth_m=19.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Candidate 4 in same subdivision NL-ZH, ~45 NM away (for top-3 capping check)
        deep_cand4 = Port(
            unlocode="NLD04",
            port_name="Deep Alternative 4",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=52.30,
            longitude=4.50,
            channel_depth_m=20.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Shallow candidate in same subdivision NL-ZH (should be filtered out by SQL depth gate)
        shallow_cand = Port(
            unlocode="NLSHA",
            port_name="Shallow Haven",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.90,
            longitude=4.30,
            channel_depth_m=10.0,  # Insufficient for Neo-Panamax (15.2m * 1.1 = 16.72m)
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Candidate in DIFFERENT subdivision (NL-NH), should be excluded
        diff_subdiv = Port(
            unlocode="NLAMS",
            port_name="Port of Amsterdam",
            country_code="NL",
            subdivision_code="NL-NH",
            latitude=52.37,
            longitude=4.89,
            channel_depth_m=18.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        # Candidate with missing depth
        no_depth = Port(
            unlocode="NLNOD",
            port_name="No Depth Port",
            country_code="NL",
            subdivision_code="NL-ZH",
            latitude=51.91,
            longitude=4.20,
            channel_depth_m=None,
            is_depth_available=False,
            reconciliation_method="EXACT_UNLOCODE",
        )

        session.add_all([
            nlrtm, deep_cand1, deep_cand2, deep_cand3, deep_cand4,
            shallow_cand, diff_subdiv, no_depth,
        ])
        await session.commit()

        # Seed snapshots:
        # NLD01 has LOW risk
        # NLD02 has MEDIUM risk
        # NLD03 has HIGH risk (should be disqualified by operational check)
        # NLD04 has LOW risk
        now = datetime.now(timezone.utc)
        snapshots = [
            PortRiskSnapshot(
                snapshot_id=uuid.uuid4(),
                unlocode="NLD01",
                vessel_class_id="neoPanamax",
                overall_risk_level="LOW",
                anchored_vessel_count=3,
                underway_vessel_count=2,
                swell_height_m=0.9,
                wind_speed_kts=12.0,
                updated_at=now,
            ),
            PortRiskSnapshot(
                snapshot_id=uuid.uuid4(),
                unlocode="NLD02",
                vessel_class_id="neoPanamax",
                overall_risk_level="MEDIUM",
                anchored_vessel_count=8,
                underway_vessel_count=3,
                swell_height_m=1.6,
                wind_speed_kts=22.0,
                updated_at=now,
            ),
            PortRiskSnapshot(
                snapshot_id=uuid.uuid4(),
                unlocode="NLD03",
                vessel_class_id="neoPanamax",
                overall_risk_level="HIGH",  # Severe congestion
                anchored_vessel_count=20,
                underway_vessel_count=5,
                swell_height_m=1.0,
                wind_speed_kts=14.0,
                updated_at=now,
            ),
            PortRiskSnapshot(
                snapshot_id=uuid.uuid4(),
                unlocode="NLD04",
                vessel_class_id="neoPanamax",
                overall_risk_level="LOW",
                anchored_vessel_count=2,
                underway_vessel_count=1,
                swell_height_m=0.8,
                wind_speed_kts=10.0,
                updated_at=now,
            ),
        ]
        session.add_all(snapshots)
        await session.commit()

    yield engine, session_factory
    await engine.dispose()


def test_haversine_distance_calculations():
    """Verify Haversine formula against benchmark port pairs and coordinate boundaries."""
    # 1. Rotterdam (51.9244, 4.4777) to Antwerp (51.22, 4.40) is ~42.5 NM (within +/-0.5 NM)
    dist = calculate_haversine_distance_nm(51.9244, 4.4777, 51.22, 4.40)
    assert 41.5 <= dist <= 43.5

    # 2. Identical coordinates return 0.0 NM
    assert calculate_haversine_distance_nm(25.0, -80.0, 25.0, -80.0) == 0.0

    # 3. Equator test: 1 degree of longitude along equator is ~60.0 NM
    dist_eq = calculate_haversine_distance_nm(0.0, 0.0, 0.0, 1.0)
    assert 59.5 <= dist_eq <= 60.5

    # 4. Near antimeridian boundaries without domain error
    dist_anti = calculate_haversine_distance_nm(10.0, 179.9, 10.0, -179.9)
    assert dist_anti >= 0.0


def test_required_depth_and_swell_gating():
    """Verify UKC h_req depth calculation across calm/swell gating and all 13 vessel classes."""
    # Neo-Panamax draft is 15.2m
    # Calm swell (Hs=1.5m <= 2.0m): 1.10 * 15.2 = 16.72m
    assert calculate_required_depth_m("neoPanamax", wave_height_m=1.5) == 16.72

    # Heavy swell (Hs=2.5m > 2.0m): 1.35 * 15.2 = 20.52m
    assert calculate_required_depth_m("neoPanamax", wave_height_m=2.5) == 20.52

    # Boundary transition: Hs=2.0m -> 1.10; Hs=2.01m -> 1.35
    assert calculate_required_depth_m("neoPanamax", wave_height_m=2.0) == 16.72
    assert calculate_required_depth_m("neoPanamax", wave_height_m=2.01) == 20.52

    # All 13 vessel classes draft lookup
    for vc, draft in BENCHMARK_VESSEL_DRAFTS.items():
        h = calculate_required_depth_m(vc, 1.0)
        assert h == round(draft * 1.10, 2)

    # Invalid vessel class raises ValueError
    with pytest.raises(ValueError):
        calculate_required_depth_m("spaceship", 1.0)


@pytest.mark.asyncio
async def test_recommendations_trigger_condition(rec_test_db):
    """Verify engine bypasses discovery when primary risk tier is LOW or MEDIUM."""
    engine, session_factory = rec_test_db

    async with session_factory() as session:
        nlrtm = (await session.execute(select(Port).where(Port.unlocode == "NLRTM"))).scalar_one()

        # Primary risk LOW -> empty list
        recs_low = await recommend_alternative_ports(
            session=session,
            primary_port=nlrtm,
            vessel_class="neoPanamax",
            primary_risk_tier="LOW",
        )
        assert recs_low == []

        # Primary risk MEDIUM -> empty list
        recs_med = await recommend_alternative_ports(
            session=session,
            primary_port=nlrtm,
            vessel_class="neoPanamax",
            primary_risk_tier="medium",
        )
        assert recs_med == []


@pytest.mark.asyncio
async def test_recommendations_discovery_filtering_and_ranking(rec_test_db):
    """Verify SQL-level depth gating, operational hazard filtering, ascending ranking, and top-3 capping."""
    engine, session_factory = rec_test_db

    async with session_factory() as session:
        nlrtm = (await session.execute(select(Port).where(Port.unlocode == "NLRTM"))).scalar_one()

        # Primary port risk is HIGH -> trigger discovery
        # Neo-Panamax calm swell h_req = 16.72m
        # Candidates in NL-ZH:
        # - NLRTM: excluded (primary)
        # - NLSHA: 10.0m < 16.72m -> filtered out by SQL depth check
        # - NLAMS: different subdivision (NL-NH) -> filtered out by SQL subdivision check
        # - NLNOD: missing depth -> filtered out by SQL depth available check
        # - NLD01: 18.0m >= 16.72m, LOW risk -> eligible (~15 NM)
        # - NLD02: 17.5m >= 16.72m, MEDIUM risk -> eligible (~25 NM)
        # - NLD03: 19.0m >= 16.72m, HIGH risk -> disqualified by operational status
        # - NLD04: 20.0m >= 16.72m, LOW risk -> eligible (~45 NM)
        recs = await recommend_alternative_ports(
            session=session,
            primary_port=nlrtm,
            vessel_class="neoPanamax",
            primary_risk_tier="HIGH",
            wave_height_m=1.0,
        )

        # Only NLD01, NLD02, NLD04 should be returned!
        assert len(recs) == 3

        locodes = [r.unlocode for r in recs]
        assert locodes == ["NLD01", "NLD02", "NLD04"]

        # Strictly sorted ascending by distance
        distances = [r.distanceNm for r in recs]
        assert distances == sorted(distances)

        # Check fields of recommendation schema
        for r in recs:
            assert isinstance(r, AlternativePortRecommendation)
            assert r.unlocode in ["NLD01", "NLD02", "NLD04"]
            assert r.riskTier in ["low", "medium"]
            assert r.channelDepthM >= 16.72
            assert r.depthMarginM >= 0.0
            assert "anchored" in r.trafficStatus


@pytest.mark.asyncio
async def test_recommendations_empty_when_no_candidates_meet_depth(rec_test_db):
    """Verify empty list when all candidates fail physical depth requirement."""
    engine, session_factory = rec_test_db

    async with session_factory() as session:
        nlrtm = (await session.execute(select(Port).where(Port.unlocode == "NLRTM"))).scalar_one()

        # VLCC draft is 21.0m. Under swell (Hs=2.5m): h_req = 1.35 * 21.0 = 28.35m.
        # Max candidate depth is 20.0m, so NONE pass the depth gate.
        recs = await recommend_alternative_ports(
            session=session,
            primary_port=nlrtm,
            vessel_class="vlcc",
            primary_risk_tier="HIGH",
            wave_height_m=2.5,
        )
        assert recs == []
