"""Unit and integration tests for SQLAlchemy 2.0 ORM models and constraints."""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import (
    AlertLog,
    Base,
    Port,
    PortRiskSnapshot,
    PortTrafficBaseline,
    UserWatchlist,
    VesselClass,
)


@pytest_asyncio.fixture
async def test_session():
    """Create an isolated in-memory SQLite database session with foreign key enforcement."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_crud_all_models(test_session: AsyncSession):
    """Verify asynchronous CRUD operations across all 6 models."""
    # 1. Create Port
    port = Port(
        unlocode="NLRTM",
        port_name="Port of Rotterdam",
        country_code="NL",
        subdivision_code="ZH",
        latitude=51.95,
        longitude=4.13,
        wpi_number=12345,
        channel_depth_m=20.0,
        cargo_pier_depth_m=18.0,
        anchorage_depth_m=22.0,
        is_depth_available=True,
        reconciliation_method="EXACT_UNLOCODE",
    )
    test_session.add(port)

    # 2. Create VesselClass
    vclass = VesselClass(
        class_id="vlcc",
        class_name="Very Large Crude Carrier",
        draft_m=21.0,
        beam_m=60.0,
        loa_m=330.0,
    )
    test_session.add(vclass)
    await test_session.commit()

    # Read back Port and VesselClass
    loaded_port = await test_session.get(Port, "NLRTM")
    assert loaded_port is not None
    assert loaded_port.port_name == "Port of Rotterdam"

    loaded_vclass = await test_session.get(VesselClass, "vlcc")
    assert loaded_vclass is not None
    assert loaded_vclass.draft_m == 21.0

    # 3. Create UserWatchlist
    user_id = uuid.uuid4()
    watchlist = UserWatchlist(
        user_id=user_id,
        unlocode="NLRTM",
        vessel_class_id="vlcc",
    )
    test_session.add(watchlist)

    # 4. Create PortTrafficBaseline
    baseline = PortTrafficBaseline(
        unlocode="NLRTM",
        day_of_week=2,
        hour_of_day=14,
        avg_anchored_count=12.5,
        avg_underway_count=6.0,
        avg_total_active=18.5,
    )
    test_session.add(baseline)

    # 5. Create PortRiskSnapshot
    snapshot = PortRiskSnapshot(
        unlocode="NLRTM",
        vessel_class_id="vlcc",
        grounding_risk_level="HIGH",
        anchored_vessel_count=14,
        underway_vessel_count=5,
        total_active_geofence_count=19,
        historical_avg_queue=12.5,
        queue_variance_pct=12.0,
        congestion_risk_level="MEDIUM",
        weather_risk_level="LOW",
        overall_risk_level="HIGH",
        swell_height_m=2.4,
        wind_speed_kts=18.5,
    )
    test_session.add(snapshot)

    # 6. Create AlertLog
    alert = AlertLog(
        user_id=user_id,
        unlocode="NLRTM",
        vessel_class_id="vlcc",
        previous_risk_level="MEDIUM",
        new_risk_level="HIGH",
        trigger_reason="Swell height exceeded 2.0m clearance threshold",
    )
    test_session.add(alert)
    await test_session.commit()

    # Verify query and update
    result = await test_session.execute(
        select(PortTrafficBaseline).where(PortTrafficBaseline.unlocode == "NLRTM")
    )
    bl = result.scalar_one()
    assert bl.avg_anchored_count == 12.5
    bl.avg_anchored_count = 15.0
    await test_session.commit()

    reloaded_bl = await test_session.get(PortTrafficBaseline, bl.baseline_id)
    assert reloaded_bl.avg_anchored_count == 15.0

    # Delete
    await test_session.delete(reloaded_bl)
    await test_session.commit()
    deleted_bl = await test_session.get(PortTrafficBaseline, bl.baseline_id)
    assert deleted_bl is None


@pytest.mark.asyncio
async def test_foreign_key_enforcement(test_session: AsyncSession):
    """Verify foreign key enforcement raises IntegrityError on invalid parent keys."""
    user_id = uuid.uuid4()

    # Inserting UserWatchlist with non-existent port should fail
    bad_watchlist = UserWatchlist(
        user_id=user_id,
        unlocode="ZZZZZ",  # Does not exist
        vessel_class_id="vlcc",
    )
    test_session.add(bad_watchlist)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()

    # Create port, but use non-existent vessel_class_id
    port = Port(
        unlocode="NLRTM",
        port_name="Port of Rotterdam",
        country_code="NL",
        subdivision_code="ZH",
        latitude=51.95,
        longitude=4.13,
    )
    test_session.add(port)
    await test_session.commit()

    bad_snapshot = PortRiskSnapshot(
        unlocode="NLRTM",
        vessel_class_id="unknown_class",
        grounding_risk_level="LOW",
    )
    test_session.add(bad_snapshot)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
async def test_unique_constraints(test_session: AsyncSession):
    """Verify composite and column unique constraints raise IntegrityError."""
    port1 = Port(
        unlocode="NLRTM",
        port_name="Rotterdam",
        country_code="NL",
        subdivision_code="ZH",
        latitude=51.95,
        longitude=4.13,
        wpi_number=1001,
    )
    vclass = VesselClass(
        class_id="vlcc",
        class_name="VLCC",
        draft_m=20.0,
        beam_m=60.0,
        loa_m=330.0,
    )
    test_session.add_all([port1, vclass])
    await test_session.commit()

    # Duplicate wpi_number
    port2 = Port(
        unlocode="NLAMS",
        port_name="Amsterdam",
        country_code="NL",
        subdivision_code="NH",
        latitude=52.37,
        longitude=4.90,
        wpi_number=1001,  # Duplicate
    )
    test_session.add(port2)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()

    # Duplicate user_watchlist (user_id, unlocode, vessel_class_id)
    uid = uuid.uuid4()
    w1 = UserWatchlist(user_id=uid, unlocode="NLRTM", vessel_class_id="vlcc")
    w2 = UserWatchlist(user_id=uid, unlocode="NLRTM", vessel_class_id="vlcc")
    test_session.add(w1)
    await test_session.commit()

    test_session.add(w2)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()

    # Duplicate baseline (unlocode, day_of_week, hour_of_day)
    b1 = PortTrafficBaseline(unlocode="NLRTM", day_of_week=0, hour_of_day=12)
    b2 = PortTrafficBaseline(unlocode="NLRTM", day_of_week=0, hour_of_day=12)
    test_session.add(b1)
    await test_session.commit()

    test_session.add(b2)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
async def test_check_constraints(test_session: AsyncSession):
    """Verify check constraints for day_of_week, hour_of_day, and risk levels."""
    port = Port(
        unlocode="NLRTM",
        port_name="Rotterdam",
        country_code="NL",
        subdivision_code="ZH",
        latitude=51.95,
        longitude=4.13,
    )
    vclass = VesselClass(
        class_id="vlcc",
        class_name="VLCC",
        draft_m=20.0,
        beam_m=60.0,
        loa_m=330.0,
    )
    test_session.add_all([port, vclass])
    await test_session.commit()

    # Invalid day_of_week (< 0 or > 6)
    bad_baseline = PortTrafficBaseline(
        unlocode="NLRTM",
        day_of_week=7,  # invalid
        hour_of_day=10,
    )
    test_session.add(bad_baseline)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()

    # Invalid hour_of_day (< 0 or > 23)
    bad_hour = PortTrafficBaseline(
        unlocode="NLRTM",
        day_of_week=3,
        hour_of_day=24,  # invalid
    )
    test_session.add(bad_hour)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()

    # Invalid risk level string
    bad_snapshot = PortRiskSnapshot(
        unlocode="NLRTM",
        vessel_class_id="vlcc",
        grounding_risk_level="CRITICAL",  # Check constraint only permits LOW, MEDIUM, HIGH
    )
    test_session.add(bad_snapshot)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
async def test_session_rollback_behavior(test_session: AsyncSession):
    """Verify rolling back an uncommitted transaction leaves the database unaffected."""
    port = Port(
        unlocode="NLRTM",
        port_name="Rotterdam",
        country_code="NL",
        subdivision_code="ZH",
        latitude=51.95,
        longitude=4.13,
    )
    test_session.add(port)
    await test_session.rollback()

    res = await test_session.execute(select(Port).where(Port.unlocode == "NLRTM"))
    assert res.scalar_one_or_none() is None

    # Database is clean and ready for subsequent queries
    test_session.add(port)
    await test_session.commit()
    res2 = await test_session.execute(select(Port).where(Port.unlocode == "NLRTM"))
    assert res2.scalar_one() is not None
