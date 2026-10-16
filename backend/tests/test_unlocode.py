"""Tests for UN/LOCODE coordinate parsing, filtering, SQLite database, and search."""

import tempfile
from pathlib import Path
import pytest
from app.clients.unlocode_db import (
    UnlocodeDatabase,
    is_maritime_port,
    parse_unlocode_coordinates,
)
from app.models.port import Port
from scripts.import_unlocode import parse_csv_file


def test_parse_unlocode_coordinates_valid():
    """Verify coordinate parser correctly parses North/South and East/West degrees & minutes."""
    # Rotterdam: 51 deg 55 min N, 004 deg 24 min E
    res1 = parse_unlocode_coordinates("5155N 00424E")
    assert res1 is not None
    assert res1 == (51.9167, 4.4)

    # Santos: 23 deg 54 min S, 046 deg 19 min W
    res2 = parse_unlocode_coordinates("2354S 04619W")
    assert res2 is not None
    assert res2 == (-23.9, -46.3167)

    # Los Angeles: 33 deg 43 min N, 118 deg 16 min W
    res3 = parse_unlocode_coordinates("3343N 11816W")
    assert res3 is not None
    assert res3 == (33.7167, -118.2667)


def test_parse_unlocode_coordinates_invalid():
    """Verify coordinate parser returns None for empty, malformed, or invalid strings."""
    assert parse_unlocode_coordinates("") is None
    assert parse_unlocode_coordinates(None) is None
    assert parse_unlocode_coordinates("invalid") is None
    assert parse_unlocode_coordinates("1234N") is None
    assert parse_unlocode_coordinates("5155X 00424E") is None


def test_is_maritime_port():
    """Verify Function 1 detection for maritime/waterborne ports."""
    assert is_maritime_port("1-------") is True
    assert is_maritime_port("1234----") is True
    assert is_maritime_port("10------") is True
    assert is_maritime_port("-234----") is False
    assert is_maritime_port("0-------") is False
    assert is_maritime_port("4-------") is False
    assert is_maritime_port("") is False
    assert is_maritime_port(None) is False


def test_unlocode_database_seeding_and_search(tmp_path: Path):
    """Verify SQLite database initialization, seeding, and search ranking."""
    db_file = tmp_path / "test_unlocode.db"
    seed_file = Path("backend/data/maritime_ports.json")

    db = UnlocodeDatabase(db_path=str(db_file), seed_path=str(seed_file))

    # Test count
    count = db.count_ports()
    assert count >= 40

    # Search by LOCODE (exact match)
    res_locode = db.search_ports("NLRTM")
    assert len(res_locode) > 0
    assert res_locode[0].locode == "NLRTM"
    assert "Rotterdam" in res_locode[0].name

    # Search by Name
    res_name = db.search_ports("Singapore")
    assert any(p.locode == "SGSIN" for p in res_name)

    # Search by Country
    res_country = db.search_ports("Netherlands")
    assert any(p.locode == "NLRTM" for p in res_country)

    # Get by LOCODE
    port = db.get_port_by_locode("USLAX")
    assert port is not None
    assert port.locode == "USLAX"
    assert port.country == "United States"

    # Get by non-existent LOCODE
    missing = db.get_port_by_locode("ZZZZZ")
    assert missing is None


def test_parse_csv_file_import(tmp_path: Path):
    """Verify reading and parsing a sample UNECE CSV format."""
    csv_content = """Ch,Country,Location,Name,NameWoDiacritics,Subdivision,Function,Status,Date,IATA,Coordinates,Remarks
+,NL,AMS,Amsterdam,Amsterdam,NH,12345---,AI,0101,,5222N 00454E,
+,NL,RTM,Rotterdam,Rotterdam,ZH,12345---,AI,0101,,5155N 00424E,
+,NL,UTC,Utrecht,Utrecht,UT,-2345---,AI,0101,,5205N 00507E,
+,US,NYC,New York,New York,NY,12345---,AI,0101,,4042N 07400W,
"""
    test_csv = tmp_path / "sample_unlocode.csv"
    test_csv.write_text(csv_content, encoding="utf-8")

    parsed_ports = parse_csv_file(test_csv)

    # Utrecht has function -2345--- (no port/waterborne 1), so it must be excluded
    locodes = [p.locode for p in parsed_ports]
    assert "NLAMS" in locodes
    assert "NLRTM" in locodes
    assert "USNYC" in locodes
    assert "NLUTC" not in locodes

    # Verify coordinates of Amsterdam
    ams = next(p for p in parsed_ports if p.locode == "NLAMS")
    assert ams.lat == 52.3667
    assert ams.lon == 4.9
