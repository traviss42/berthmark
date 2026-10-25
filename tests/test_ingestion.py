"""Unit and integration tests for UN/LOCODE & WPI data ingestion and reconciliation."""

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.ingestion.parser import (
    haversine_distance_km,
    parse_unlocode_coordinates,
    parse_unlocode_ports,
    parse_wpi_records,
    reconcile_ports,
)
from backend.ingestion.pipeline import run_ingestion
from backend.models import Base, Port


@pytest_asyncio.fixture
async def db_session():
    """Create an isolated test database session with schema loaded."""
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
        yield session

    await engine.dispose()


def test_parse_unlocode_coordinates():
    """Verify alphanumeric coordinate parsing, hemispheres, and edge cases."""
    # North / East
    lat, lon = parse_unlocode_coordinates("5155N 00430E")
    assert lat == pytest.approx(51.916667, rel=1e-4)
    assert lon == pytest.approx(4.5, rel=1e-4)

    # South / West
    lat, lon = parse_unlocode_coordinates("1230S 04515W")
    assert lat == pytest.approx(-12.5, rel=1e-4)
    assert lon == pytest.approx(-45.25, rel=1e-4)

    # Houston coordinates
    lat, lon = parse_unlocode_coordinates("2945N 09521W")
    assert lat == pytest.approx(29.75, rel=1e-4)
    assert lon == pytest.approx(-95.35, rel=1e-4)

    # Malformed or empty
    assert parse_unlocode_coordinates("") == (None, None)
    assert parse_unlocode_coordinates(None) == (None, None)
    assert parse_unlocode_coordinates("INVALID") == (None, None)
    assert parse_unlocode_coordinates("9999N 99999E") == (None, None)


def test_haversine_distance():
    """Verify Haversine distance calculation in kilometers."""
    # Distance between Rotterdam (51.92, 4.48) and Hook of Holland (51.98, 4.12) is ~25 km
    dist = haversine_distance_km(51.92, 4.48, 51.98, 4.12)
    assert 20.0 < dist < 30.0

    # Same point is 0 km
    assert haversine_distance_km(51.92, 4.48, 51.92, 4.48) == 0.0


def test_reconciliation_exact_fuzzy_and_unmatched():
    """Verify exact matching, fallback fuzzy spatial proximity matching, and unmatched logic."""
    unlocode_catalog = {
        "NLRTM": {
            "unlocode": "NLRTM",
            "port_name": "Rotterdam",
            "country_code": "NL",
            "subdivision_code": "NL-ZH",
            "latitude": 51.92,
            "longitude": 4.48,
        },
        "FRLEH": {
            "unlocode": "FRLEH",
            "port_name": "Le Havre",
            "country_code": "FR",
            "subdivision_code": "FR-76",
            "latitude": 49.49,
            "longitude": 0.11,
        },
        "GBSOU": {
            "unlocode": "GBSOU",
            "port_name": "Southampton",
            "country_code": "GB",
            "subdivision_code": "GB-HAM",
            "latitude": 50.90,
            "longitude": -1.40,
        },
    }

    wpi_records = [
        # Exact match
        {
            "wpi_number": 31140,
            "main_port_name": "Rotterdam",
            "locode": "NLRTM",
            "country_code": "Netherlands",
            "channel_depth_m": 11.0,
            "cargo_pier_depth_m": 6.4,
            "anchorage_depth_m": 11.0,
            "latitude": 51.90,
            "longitude": 4.48,
        },
        # Fuzzy match (lacks LOCODE but within 5 km of Le Havre)
        {
            "wpi_number": 37200,
            "main_port_name": "Port du Havre",
            "locode": None,
            "country_code": "France",
            "channel_depth_m": 15.5,
            "cargo_pier_depth_m": 12.0,
            "anchorage_depth_m": 16.0,
            "latitude": 49.48,
            "longitude": 0.12,
        },
    ]

    reconciled = reconcile_ports(unlocode_catalog, wpi_records)
    by_code = {p["unlocode"]: p for p in reconciled}

    # 1. Exact match check
    rtm = by_code["NLRTM"]
    assert rtm["reconciliation_method"] == "EXACT_UNLOCODE"
    assert rtm["is_depth_available"] is True
    assert rtm["channel_depth_m"] == 11.0
    assert rtm["wpi_number"] == 31140

    # 2. Fuzzy spatial match check (<= 10km)
    leh = by_code["FRLEH"]
    assert leh["reconciliation_method"] == "FUZZY_SPATIAL"
    assert leh["is_depth_available"] is True
    assert leh["channel_depth_m"] == 15.5
    assert leh["wpi_number"] == 37200

    # 3. Unmatched check
    sou = by_code["GBSOU"]
    assert sou["reconciliation_method"] == "UNMATCHED"
    assert sou["is_depth_available"] is False
    assert sou["channel_depth_m"] is None
    assert sou["wpi_number"] is None


def test_wpi_deduplication():
    """Verify that multiple WPI entries with the same LOCODE choose the deepest channel."""
    unlocode_catalog = {
        "TEST1": {
            "unlocode": "TEST1",
            "port_name": "Test Port",
            "country_code": "US",
            "subdivision_code": "US-CA",
            "latitude": 33.74,
            "longitude": -118.26,
        }
    }
    wpi_records = [
        {
            "wpi_number": 100,
            "main_port_name": "Terminal A",
            "locode": "TEST1",
            "country_code": "United States",
            "channel_depth_m": 10.0,
            "cargo_pier_depth_m": 8.0,
            "anchorage_depth_m": 10.0,
            "latitude": 33.74,
            "longitude": -118.26,
        },
        {
            "wpi_number": 101,
            "main_port_name": "Terminal B (Deepwater)",
            "locode": "TEST1",
            "country_code": "United States",
            "channel_depth_m": 16.5,
            "cargo_pier_depth_m": 14.0,
            "anchorage_depth_m": 16.0,
            "latitude": 33.74,
            "longitude": -118.26,
        },
    ]

    reconciled = reconcile_ports(unlocode_catalog, wpi_records)
    assert len(reconciled) == 1
    p = reconciled[0]
    assert p["channel_depth_m"] == 16.5
    assert p["wpi_number"] == 101


def test_benchmark_ports_reconciliation():
    """Verify that Rotterdam, Singapore, Houston, and Antwerp reconcile correctly against actual datasets."""
    unlocode_ports = parse_unlocode_ports("data/unlocode")
    wpi_records = parse_wpi_records("data/wpi/UpdatedPub150.csv")
    reconciled = reconcile_ports(unlocode_ports, wpi_records)
    ports_by_code = {p["unlocode"]: p for p in reconciled}

    # 1. Rotterdam (NLRTM)
    assert "NLRTM" in ports_by_code
    rtm = ports_by_code["NLRTM"]
    assert rtm["country_code"] == "NL"
    assert rtm["subdivision_code"] == "NL-ZH"
    assert rtm["is_depth_available"] is True
    assert rtm["channel_depth_m"] is not None and rtm["channel_depth_m"] > 10.0
    assert rtm["reconciliation_method"] == "EXACT_UNLOCODE"

    # 2. Singapore (SGSIN)
    assert "SGSIN" in ports_by_code
    sin = ports_by_code["SGSIN"]
    assert sin["country_code"] == "SG"
    assert sin["is_depth_available"] is True
    assert sin["channel_depth_m"] is not None and sin["channel_depth_m"] > 10.0
    assert sin["reconciliation_method"] == "EXACT_UNLOCODE"

    # 3. Houston (USHOU)
    assert "USHOU" in ports_by_code
    hou = ports_by_code["USHOU"]
    assert hou["country_code"] == "US"
    assert hou["subdivision_code"] == "US-TX"
    assert hou["is_depth_available"] is True
    assert hou["channel_depth_m"] is not None and hou["channel_depth_m"] > 10.0
    assert hou["reconciliation_method"] == "EXACT_UNLOCODE"

    # 4. Antwerp-Bruges (BEANR)
    assert "BEANR" in ports_by_code
    anr = ports_by_code["BEANR"]
    assert anr["country_code"] == "BE"
    assert anr["is_depth_available"] is True
    assert anr["channel_depth_m"] is not None and anr["channel_depth_m"] > 10.0
    assert anr["reconciliation_method"] == "EXACT_UNLOCODE"


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_and_idempotency(db_session: AsyncSession):
    """Verify full bulk ingestion and idempotent re-runs into the database."""
    # Run initial ingestion
    count1 = await run_ingestion(db_session, data_dir="data", drop_existing=True)
    assert count1 > 1000

    # Query benchmark ports from database
    rtm = await db_session.get(Port, "NLRTM")
    assert rtm is not None
    assert rtm.country_code == "NL"
    assert rtm.subdivision_code == "NL-ZH"
    assert rtm.is_depth_available is True
    assert rtm.channel_depth_m > 10.0
    assert rtm.reconciliation_method == "EXACT_UNLOCODE"

    sin = await db_session.get(Port, "SGSIN")
    assert sin is not None
    assert sin.country_code == "SG"
    assert sin.is_depth_available is True
    assert sin.reconciliation_method == "EXACT_UNLOCODE"

    # Idempotent re-run should succeed without constraint violations
    count2 = await run_ingestion(db_session, data_dir="data", drop_existing=True)
    assert count2 == count1
