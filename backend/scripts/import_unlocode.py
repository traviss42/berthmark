"""CLI utility to import and parse official UNECE UN/LOCODE releases into SQLite.

Filters strictly for:
  1. Function Code '1' — Maritime transport (sea port or maritime port)
     per https://raw.githubusercontent.com/datasets/un-locode/refs/heads/main/data/function-classifiers.csv
  2. Rows with valid UNECE coordinates present in the dataset (no fallback or guessed coordinates).

Usage examples:
    # 1. Fetch and import directly from the official UN/LOCODE dataset repository:
    python backend/scripts/import_unlocode.py

    # 2. Parse a downloaded UNECE CSV file:
    python backend/scripts/import_unlocode.py --csv path/to/code-list.csv

    # 3. Parse a directory containing multiple CodeListPart*.csv files:
    python backend/scripts/import_unlocode.py --dir path/to/unlocode_csvs/
"""

import argparse
import csv
import glob
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.clients.unlocode_db import (
    UnlocodeDatabase,
    is_maritime_port,
    parse_unlocode_coordinates,
)
from app.config import get_settings
from app.models.port import Port

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("unlocode_importer")

UNLOCODE_CODE_LIST_URL = (
    "https://raw.githubusercontent.com/datasets/un-locode/refs/heads/main/data/code-list.csv"
)
UNLOCODE_COUNTRY_CODES_URL = (
    "https://raw.githubusercontent.com/datasets/un-locode/refs/heads/main/data/country-codes.csv"
)

DEFAULT_PORT_LOCODES = {
    "NLRTM",
    "SGSIN",
    "DEHAM",
    "USLAX",
    "BEANR",
    "JPTYO",
    "KRPUS",
    "USNYC",
}

COUNTRY_NAME_OVERRIDES: Dict[str, str] = {
    "US": "United States",
    "GB": "United Kingdom",
    "KR": "South Korea",
    "KP": "North Korea",
    "NL": "Netherlands",
    "AE": "United Arab Emirates",
    "RU": "Russia",
    "VN": "Vietnam",
    "TW": "Taiwan",
    "IR": "Iran",
    "VE": "Venezuela",
    "BO": "Bolivia",
    "TZ": "Tanzania",
    "SY": "Syria",
    "MD": "Moldova",
    "CD": "DR Congo",
    "CG": "Congo",
    "PH": "Philippines",
    "DO": "Dominican Republic",
    "BS": "Bahamas",
    "GM": "Gambia",
    "SD": "Sudan",
    "NE": "Niger",
    "KM": "Comoros",
    "KY": "Cayman Islands",
    "FK": "Falkland Islands",
    "FO": "Faroe Islands",
    "MH": "Marshall Islands",
    "MP": "Northern Mariana Islands",
    "TC": "Turks and Caicos Islands",
    "VG": "British Virgin Islands",
    "VI": "U.S. Virgin Islands",
    "UM": "U.S. Minor Outlying Islands",
    "CC": "Cocos (Keeling) Islands",
    "CK": "Cook Islands",
}


def load_country_names(url: str = UNLOCODE_COUNTRY_CODES_URL) -> Dict[str, str]:
    """Load ISO 2-letter country code to readable country name mapping from country-codes.csv."""
    mapping: Dict[str, str] = {}
    try:
        req = urllib.request.urlopen(url, timeout=15)
        lines = [line.decode("utf-8", errors="replace") for line in req.readlines()]
        reader = csv.reader(lines)
        for row in reader:
            if len(row) < 2:
                continue
            code = row[0].strip().upper()
            name = row[1].strip()
            if len(code) != 2 or code == "COUNTRYCODE":
                continue
            if name.endswith(" (the)"):
                name = name[:-6].strip()
            mapping[code] = name
    except Exception as e:
        logger.warning("Could not fetch remote country-codes.csv (%s), using overrides.", e)

    mapping.update(COUNTRY_NAME_OVERRIDES)
    return mapping


def parse_csv_rows(
    rows: Iterable[List[str]],
    source_name: str = "code-list.csv",
    country_names: Optional[Dict[str, str]] = None,
) -> List[Port]:
    """Parse UN/LOCODE CSV rows, filtering strictly for Function=1 (Maritime) and valid coordinates."""
    country_map = country_names or {}
    ports_by_locode: Dict[str, Port] = {}

    count_total = 0
    count_maritime = 0
    count_valid_coords = 0

    for row in rows:
        count_total += 1
        if len(row) < 10:
            continue

        # Standard UN/LOCODE code-list.csv layout (12 columns):
        # 0: Change, 1: Country, 2: Location, 3: Name, 4: NameWoDiacritics,
        # 5: Subdivision, 6: Status, 7: Function, 8: Date, 9: IATA, 10: Coordinates, 11: Remarks
        country_code = row[1].strip().upper()
        location_code = row[2].strip().upper()

        # Skip header row or invalid country/location codes
        if (
            not country_code
            or not location_code
            or len(country_code) != 2
            or len(location_code) != 3
            or country_code == "CO" and location_code == "LOC"
        ):
            continue

        full_locode = f"{country_code}{location_code}"
        name = row[4].strip() or row[3].strip()

        # Function classifier is in col 7 (standard code-list.csv) or col 6 (alternate UNECE layout)
        col7 = row[7].strip() if len(row) > 7 else ""
        col6 = row[6].strip() if len(row) > 6 else ""
        if "-" in col7 or any(c.isdigit() for c in col7):
            function_code = col7
        elif "-" in col6 or any(c.isdigit() for c in col6):
            function_code = col6
        else:
            function_code = col7 or col6


        # Filter 1: Only maritime transport ports (Function Code '1' per function-classifiers.csv)
        if not is_maritime_port(function_code):
            continue

        count_maritime += 1

        # Filter 2: Must have valid coordinates present in UN/LOCODE (no fallback/guessed coordinates)
        coord_raw = ""
        for col_idx in [10, 9, 8]:
            if len(row) > col_idx and any(c in row[col_idx] for c in ["N", "S"]):
                coord_raw = row[col_idx].strip()
                break

        coords = parse_unlocode_coordinates(coord_raw)
        if not coords:
            continue

        count_valid_coords += 1
        lat, lon = coords
        port_id = f"port-{full_locode.lower()}"
        country_display = country_map.get(country_code, country_code)
        display_name = f"Port of {name}" if not name.lower().startswith("port") else name

        ports_by_locode[full_locode] = Port(
            id=port_id,
            name=display_name,
            locode=full_locode,
            country=country_display,
            lat=lat,
            lon=lon,
            isDefault=full_locode in DEFAULT_PORT_LOCODES,
            geofenceRadiusNm=8.0,
            addedByUserId=None,
        )

    logger.info(
        "Source %s summary: Total rows=%d, Maritime ports (Function=1)=%d, With valid coordinates=%d (Unique LOCODEs=%d)",
        source_name,
        count_total,
        count_maritime,
        count_valid_coords,
        len(ports_by_locode),
    )
    return list(ports_by_locode.values())


def parse_csv_file(
    file_path: Path, country_names: Optional[Dict[str, str]] = None
) -> List[Port]:
    """Parse a local UNECE UN/LOCODE CSV file."""
    logger.info("Scanning %s...", file_path)
    encodings_to_try = ["utf-8", "latin-1", "cp1252"]
    rows = None

    for enc in encodings_to_try:
        try:
            with open(file_path, "r", encoding=enc) as f:
                f.read(2048)
                f.seek(0)
                rows = list(csv.reader(f))
                break
        except (UnicodeDecodeError, Exception):
            continue

    if rows is None:
        logger.error("Could not read %s with standard encodings.", file_path)
        return []

    return parse_csv_rows(rows, source_name=file_path.name, country_names=country_names)


def fetch_remote_unlocode_ports(
    code_list_url: str = UNLOCODE_CODE_LIST_URL,
    country_codes_url: str = UNLOCODE_COUNTRY_CODES_URL,
) -> List[Port]:
    """Download official UN/LOCODE code-list.csv and country-codes.csv and return valid maritime ports."""
    country_names = load_country_names(country_codes_url)
    logger.info("Downloading UN/LOCODE dataset from %s...", code_list_url)
    req = urllib.request.urlopen(code_list_url, timeout=30)
    lines = [line.decode("utf-8", errors="replace") for line in req.readlines()]
    rows = csv.reader(lines)
    return parse_csv_rows(rows, source_name="remote:code-list.csv", country_names=country_names)


def main():
    parser = argparse.ArgumentParser(description="Import UNECE UN/LOCODE data into Berthmark SQLite DB")
    parser.add_argument("--csv", help="Path to single UNECE CodeList CSV file")
    parser.add_argument("--dir", help="Directory containing multiple CodeListPart*.csv files")
    parser.add_argument("--seed", action="store_true", help="Seed database from fallback maritime_ports.json")
    parser.add_argument("--db", help="Target SQLite database path (defaults to config UNLOCODE_DB_PATH)")
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db or settings.UNLOCODE_DB_PATH
    db = UnlocodeDatabase(db_path=db_path)

    if args.seed:
        logger.info("Seeding database %s from bundled dataset %s...", db_path, settings.UNLOCODE_SEED_PATH)
        seed_file = Path(db.seed_path)
        if seed_file.exists():
            with open(seed_file, "r", encoding="utf-8") as f:
                ports_data = json.load(f)
            ports = [Port(**item) for item in ports_data]
            db.bulk_insert_ports(ports)
            logger.info("Inserted %d ports from %s into database.", len(ports), seed_file)
        count = db.count_ports()
        logger.info("Done. Total ports in DB: %d", count)
        return

    all_ports: List[Port] = []
    if args.csv or args.dir:
        country_names = load_country_names()
        csv_files: List[Path] = []
        if args.csv:
            csv_files.append(Path(args.csv))
        elif args.dir:
            csv_files.extend([Path(p) for p in glob.glob(os.path.join(args.dir, "*.csv"))])
        for csv_file in csv_files:
            if csv_file.exists():
                all_ports.extend(parse_csv_file(csv_file, country_names=country_names))
    else:
        all_ports = fetch_remote_unlocode_ports()

    if all_ports:
        logger.info("Saving %d maritime ports with valid coordinates to %s...", len(all_ports), db_path)
        with db._get_connection() as conn:
            conn.execute("DELETE FROM unlocode_ports;")
            conn.commit()
        db.bulk_insert_ports(all_ports)
        logger.info("Import completed successfully! Total ports in DB: %d", db.count_ports())
    else:
        logger.warning("No maritime port records extracted.")


if __name__ == "__main__":
    main()

