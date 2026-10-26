"""Unit and integration tests for async database engine, connectivity, and auto-seeding."""

import json
import os
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from backend.database import (
    BENCHMARK_7_VESSEL_CLASSES,
    DEFAULT_DATABASE_URL,
    auto_init_database,
    get_database_url,
    get_engine,
    get_db_session,
    get_seed_data_path,
    ping_database,
)
from backend.models import (
    AlertLog,
    Base,
    Port,
    PortRiskSnapshot,
    PortTrafficBaseline,
    User,
    UserWatchlist,
    VesselClass,
)


def test_get_database_url_default(monkeypatch):
    """Verify default database URL when unset or empty."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL

    monkeypatch.setenv("DATABASE_URL", "")
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_get_database_url_normalization(monkeypatch):
    """Verify sqlite:/// is normalized to sqlite+aiosqlite:///."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    assert get_database_url() == "sqlite+aiosqlite:///test.db"

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///custom.db")
    assert get_database_url() == "sqlite+aiosqlite:///custom.db"


@pytest.mark.asyncio
async def test_ping_database():
    """Verify ping_database executes SELECT 1 and returns True."""
    healthy = await ping_database()
    assert healthy is True


@pytest.mark.asyncio
async def test_get_db_session():
    """Verify get_db_session yields an active session capable of executing queries."""
    async for session in get_db_session():
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_ports_seed_json_schema():
    """Verify app/data/ports_seed.json strictly conforms to specified output schema."""
    seed_path = get_seed_data_path()
    assert seed_path.exists(), f"Seed data file not found at {seed_path}"

    with open(seed_path, "r", encoding="utf-8") as f:
        ports = json.load(f)

    assert len(ports) >= 2800, f"Expected at least 2800 ports, got {len(ports)}"

    expected_keys = {
        "unlocode",
        "port_name",
        "country_code",
        "subdivision_code",
        "latitude",
        "longitude",
        "wpi_number",
        "channel_depth_m",
        "cargo_pier_depth_m",
        "anchorage_depth_m",
        "is_depth_available",
        "reconciliation_method",
    }

    # Verify first 100 ports conform strictly
    for p in ports[:100]:
        assert set(p.keys()) == expected_keys
        assert len(p["unlocode"]) == 5
        assert p["country_code"] == p["unlocode"][:2]
        assert -90.0 <= p["latitude"] <= 90.0
        assert -180.0 <= p["longitude"] <= 180.0
        assert isinstance(p["is_depth_available"], bool)
        assert p["reconciliation_method"] in {"EXACT_UNLOCODE", "FUZZY_SPATIAL"}

    # Spot check Rotterdam (NLRTM)
    rotterdam = next((p for p in ports if p["unlocode"] == "NLRTM"), None)
    assert rotterdam is not None
    assert rotterdam["port_name"] == "Rotterdam"
    assert rotterdam["country_code"] == "NL"
    assert rotterdam["subdivision_code"] == "NL-ZH"
    assert rotterdam["channel_depth_m"] == 11.0
    assert rotterdam["is_depth_available"] is True
    assert rotterdam["reconciliation_method"] == "EXACT_UNLOCODE"


@pytest.mark.asyncio
async def test_auto_init_database_lifecycle():
    """Verify fresh database auto-init: schema creation, bulk seeding, and skip when COUNT > 0."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    try:
        # 1. Fresh database initialization (COUNT == 0)
        seeded = await auto_init_database(engine)
        assert seeded is True

        session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            # Check all tables were created
            for table in [
                Port,
                VesselClass,
                UserWatchlist,
                PortTrafficBaseline,
                PortRiskSnapshot,
                AlertLog,
                User,
            ]:
                res = await session.execute(select(func.count()).select_from(table))
                assert res.scalar() is not None

            # Verify ports count
            ports_count = await session.scalar(select(func.count(Port.unlocode)))
            assert ports_count >= 2800

            # Verify Rotterdam port record
            rtm = await session.scalar(select(Port).where(Port.unlocode == "NLRTM"))
            assert rtm is not None
            assert rtm.port_name == "Rotterdam"
            assert rtm.channel_depth_m == 11.0

            # Verify the 7 benchmark vessel classes
            vc_res = await session.execute(select(VesselClass))
            vclasses = vc_res.scalars().all()
            assert len(vclasses) == 7

            vc_map = {vc.class_id: vc for vc in vclasses}

            # 1. Handymax / Supramax (Draft 10.0m–11.5m, Beam 28m–32m)
            handy = vc_map.get("handysize")
            assert handy is not None
            assert "Handymax / Supramax" in handy.class_name
            assert 10.0 <= handy.draft_m <= 11.5
            assert 28.0 <= handy.beam_m <= 32.0

            # 2. Panamax (Draft 12.0m–13.5m, Beam 32.2m)
            panamax = vc_map.get("panamax")
            assert panamax is not None
            assert "Panamax" in panamax.class_name
            assert 12.0 <= panamax.draft_m <= 13.5
            assert panamax.beam_m == 32.2

            # 3. New Panamax (Draft 15.2m, Beam 49m, LOA 366m)
            new_panamax = vc_map.get("neoPanamax")
            assert new_panamax is not None
            assert "New Panamax" in new_panamax.class_name
            assert new_panamax.draft_m == 15.2
            assert new_panamax.beam_m == 49.0
            assert new_panamax.loa_m == 366.0

            # 4. Aframax (Draft 14.5m–15.0m, Beam 44m)
            aframax = vc_map.get("aframax")
            assert aframax is not None
            assert "Aframax" in aframax.class_name
            assert 14.5 <= aframax.draft_m <= 15.0
            assert aframax.beam_m == 44.0

            # 5. Suezmax (Draft 16.0m–17.0m, Beam 50m)
            suezmax = vc_map.get("suezmax")
            assert suezmax is not None
            assert "Suezmax" in suezmax.class_name
            assert 16.0 <= suezmax.draft_m <= 17.0
            assert suezmax.beam_m == 50.0

            # 6. VLCC (Draft 20.0m–21.5m, Beam 60m)
            vlcc = vc_map.get("vlcc")
            assert vlcc is not None
            assert "VLCC" in vlcc.class_name
            assert 20.0 <= vlcc.draft_m <= 21.5
            assert vlcc.beam_m == 60.0

            # 7. ULCS (Draft 15.5m–16.5m, Beam 59m)
            ulcs = vc_map.get("ulcv")
            assert ulcs is not None
            assert "ULCS" in ulcs.class_name
            assert 15.5 <= ulcs.draft_m <= 16.5
            assert ulcs.beam_m == 59.0

            # Verify no hardcoded seed accounts were created
            user_count = await session.scalar(select(func.count(User.id)))
            assert user_count == 0

        # 2. Subsequent boot check: COUNT > 0 skips seeding instantly
        seeded_again = await auto_init_database(engine)
        assert seeded_again is False

        # Verify ports count remains unchanged
        async with session_maker() as session:
            final_count = await session.scalar(select(func.count(Port.unlocode)))
            assert final_count == ports_count
    finally:
        await engine.dispose()

