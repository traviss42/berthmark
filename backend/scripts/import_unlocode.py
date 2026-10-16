"""CLI utility to import and merge official UNECE UN/LOCODE and NGA World Port Index (Pub 150) releases into SQLite.

Filters strictly for:
  1. Function Code '1' — Maritime transport (sea port or maritime port)
     per https://raw.githubusercontent.com/datasets/un-locode/refs/heads/main/data/function-classifiers.csv
  2. Presence in NGA World Port Index (UpdatedPub150.csv) with real Channel Depth (m) > 0
     per https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv
  3. Valid coordinates present in at least one of the two datasets (taken from the file that has them).
"""

import argparse
import csv
import glob
import json
import logging
import os
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
NGA_WPI_CSV_URL = (
    "https://msi.nga.mil/api/publications/download?type=view&key=16920959/SFH00000/UpdatedPub150.csv"
)

DEFAULT_PORT_LOCODES = {
    "NLRTM",
    "SGKEP",
    "DEHAM",
    "USLAX",
    "BEANR",
    "JPTYO",
    "CAVAN",
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


def _open_url_lines(url: str, timeout: int = 45) -> List[str]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Berthmark-Importer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return [line.decode("utf-8", errors="replace") for line in resp.readlines()]


def _parse_positive_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        num = float(val.strip())
        return round(num, 2) if num > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_coord_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        num = float(val.strip())
        return round(num, 4) if num != 0.0 else None
    except (ValueError, TypeError):
        return None


def _clean_text(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    cleaned = val.strip()
    if not cleaned or cleaned in ("-", "N/A"):
        return None
    return cleaned


def _parse_wpi_bool(val: Optional[str], fallback_compulsory: Optional[str] = None) -> bool:
    cleaned = (val or "").strip().lower()
    if cleaned == "yes":
        return True
    if cleaned == "no":
        return False
    if fallback_compulsory and fallback_compulsory.strip().lower() == "yes":
        return True
    return True


def load_country_names(url: str = UNLOCODE_COUNTRY_CODES_URL) -> Dict[str, str]:
    """Load ISO 2-letter country code to readable country name mapping from country-codes.csv."""
    mapping: Dict[str, str] = {}
    try:
        lines = _open_url_lines(url, timeout=15)
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


def parse_wpi_rows(rows: Iterable[List[str]]) -> Dict[str, Dict[str, Any]]:
    """Parse NGA World Port Index (UpdatedPub150.csv) rows keyed by 5-char UN/LOCODE.

    Only retains rows that have a valid 5-char UN/LOCODE and Channel Depth (m) > 0.
    """
    wpi_by_locode: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if len(row) < 109:
            continue
        raw_locode = row[5].strip().replace(" ", "").upper()
        if len(raw_locode) != 5 or raw_locode == "UN/LO":
            continue

        channel_depth = _parse_positive_float(row[17])
        if channel_depth is None:
            continue

        lat = _parse_coord_float(row[107])
        lon = _parse_coord_float(row[108])
        coords: Optional[Tuple[float, float]] = (lat, lon) if (lat is not None and lon is not None) else None

        entry: Dict[str, Any] = {
            "wpi_number": row[1].strip(),
            "main_port_name": row[3].strip(),
            "country_name": row[6].strip(),
            "coords": coords,
            "tidal_range_m": _parse_positive_float(row[15]),
            "channel_depth_m": channel_depth,
            "anchorage_depth_m": _parse_positive_float(row[18]),
            "cargo_pier_depth_m": _parse_positive_float(row[19]),
            "oil_terminal_depth_m": _parse_positive_float(row[20]),
            "lng_terminal_depth_m": _parse_positive_float(row[21]),
            "max_vessel_draft_m": _parse_positive_float(row[24]),
            "harbor_size": _clean_text(row[28]),
            "shelter_afforded": _clean_text(row[31]),
            "overhead_limits": _clean_text(row[36]),
            "pilotage_compulsory": _clean_text(row[49]),
            "pilotage_available": _parse_wpi_bool(row[50], row[49]),
            "tugs_assistance": _parse_wpi_bool(row[54]),
        }

        existing = wpi_by_locode.get(raw_locode)
        if existing is None or (
            (channel_depth, entry["cargo_pier_depth_m"] or 0.0, entry["anchorage_depth_m"] or 0.0)
            > (
                existing["channel_depth_m"],
                existing["cargo_pier_depth_m"] or 0.0,
                existing["anchorage_depth_m"] or 0.0,
            )
        ):
            wpi_by_locode[raw_locode] = entry

    return wpi_by_locode


def load_wpi_dataset(
    wpi_csv_path: Optional[Path] = None, wpi_url: str = NGA_WPI_CSV_URL
) -> Dict[str, Dict[str, Any]]:
    """Load NGA World Port Index dataset from local file or official NGA URL."""
    if wpi_csv_path and wpi_csv_path.exists():
        logger.info("Loading NGA World Port Index from %s...", wpi_csv_path)
        with open(wpi_csv_path, "r", encoding="utf-8", errors="replace") as f:
            return parse_wpi_rows(csv.reader(f))

    logger.info("Downloading NGA World Port Index (UpdatedPub150.csv) from %s...", wpi_url)
    lines = _open_url_lines(wpi_url, timeout=60)
    return parse_wpi_rows(csv.reader(lines))


def parse_csv_rows(
    rows: Iterable[List[str]],
    source_name: str = "code-list.csv",
    country_names: Optional[Dict[str, str]] = None,
    wpi_by_locode: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Port]:
    """Parse UN/LOCODE CSV rows, filtering strictly for Function=1 (Maritime), WPI depth data (if provided), and valid coordinates."""
    country_map = country_names or {}
    ports_by_locode: Dict[str, Port] = {}

    count_total = 0
    count_maritime = 0
    count_matched_wpi = 0
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
            or (country_code == "CO" and location_code == "LOC")
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

        # Filter 2: When combining with NGA World Port Index, require presence + required depth data in WPI
        wpi_entry: Optional[Dict[str, Any]] = None
        if wpi_by_locode is not None:
            wpi_entry = wpi_by_locode.get(full_locode)
            if not wpi_entry:
                continue
            count_matched_wpi += 1

        # Filter 3: Require coordinates in at least 1 file; take from the file that has them
        coord_raw = ""
        for col_idx in [10, 9, 8]:
            if len(row) > col_idx and any(c in row[col_idx] for c in ["N", "S"]):
                coord_raw = row[col_idx].strip()
                break

        coords = parse_unlocode_coordinates(coord_raw)
        if not coords and wpi_entry is not None:
            coords = wpi_entry.get("coords")

        if not coords:
            continue

        count_valid_coords += 1
        lat, lon = coords
        port_id = f"port-{full_locode.lower()}"
        country_display = country_map.get(country_code) or (
            wpi_entry["country_name"] if wpi_entry and wpi_entry.get("country_name") else country_code
        )
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
            channelDepthM=wpi_entry["channel_depth_m"] if wpi_entry else None,
            cargoPierDepthM=wpi_entry["cargo_pier_depth_m"] if wpi_entry else None,
            anchorageDepthM=wpi_entry["anchorage_depth_m"] if wpi_entry else None,
            oilTerminalDepthM=wpi_entry["oil_terminal_depth_m"] if wpi_entry else None,
            lngTerminalDepthM=wpi_entry["lng_terminal_depth_m"] if wpi_entry else None,
            maxVesselDraftM=wpi_entry["max_vessel_draft_m"] if wpi_entry else None,
            tidalRangeM=wpi_entry["tidal_range_m"] if wpi_entry else None,
            overheadLimits=wpi_entry["overhead_limits"] if wpi_entry else None,
            pilotageAvailable=wpi_entry["pilotage_available"] if wpi_entry else None,
            tugsAssistance=wpi_entry["tugs_assistance"] if wpi_entry else None,
            harborSize=wpi_entry["harbor_size"] if wpi_entry else None,
            shelterAfforded=wpi_entry["shelter_afforded"] if wpi_entry else None,
        )

    logger.info(
        "Source %s summary: Total rows=%d, Maritime (Function=1)=%d, Matched WPI (Depth>0)=%d, With valid coords=%d (Unique LOCODEs=%d)",
        source_name,
        count_total,
        count_maritime,
        count_matched_wpi,
        count_valid_coords,
        len(ports_by_locode),
    )
    return list(ports_by_locode.values())


def parse_csv_file(
    file_path: Path,
    country_names: Optional[Dict[str, str]] = None,
    wpi_by_locode: Optional[Dict[str, Dict[str, Any]]] = None,
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

    return parse_csv_rows(
        rows,
        source_name=file_path.name,
        country_names=country_names,
        wpi_by_locode=wpi_by_locode,
    )


def fetch_remote_unlocode_ports(
    code_list_url: str = UNLOCODE_CODE_LIST_URL,
    country_codes_url: str = UNLOCODE_COUNTRY_CODES_URL,
    wpi_url: str = NGA_WPI_CSV_URL,
    wpi_csv_path: Optional[Path] = None,
) -> List[Port]:
    """Download official UN/LOCODE and NGA World Port Index datasets and return matched maritime ports."""
    country_names = load_country_names(country_codes_url)
    wpi_by_locode = load_wpi_dataset(wpi_csv_path=wpi_csv_path, wpi_url=wpi_url)
    logger.info("Loaded %d WPI port records with valid UN/LOCODE and Channel Depth > 0.", len(wpi_by_locode))
    logger.info("Downloading UN/LOCODE dataset from %s...", code_list_url)
    lines = _open_url_lines(code_list_url, timeout=45)
    rows = csv.reader(lines)
    return parse_csv_rows(
        rows,
        source_name="remote:code-list.csv+UpdatedPub150.csv",
        country_names=country_names,
        wpi_by_locode=wpi_by_locode,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Import combined UNECE UN/LOCODE + NGA World Port Index data into Berthmark SQLite DB"
    )
    parser.add_argument("--csv", help="Path to single UNECE CodeList CSV file")
    parser.add_argument("--wpi-csv", help="Path to local NGA UpdatedPub150.csv file")
    parser.add_argument("--dir", help="Directory containing multiple CodeListPart*.csv files")
    parser.add_argument("--seed", action="store_true", help="Seed database from bundled maritime_ports.json")
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
            with db._get_connection() as conn:
                conn.execute("DELETE FROM unlocode_ports;")
                conn.commit()
            db.bulk_insert_ports(ports)
            logger.info("Inserted %d ports from %s into database.", len(ports), seed_file)
        count = db.count_ports()
        logger.info("Done. Total ports in DB: %d", count)
        return

    wpi_path = Path(args.wpi_csv) if args.wpi_csv else None
    all_ports: List[Port] = []
    if args.csv or args.dir:
        country_names = load_country_names()
        wpi_by_locode = load_wpi_dataset(wpi_csv_path=wpi_path)
        csv_files: List[Path] = []
        if args.csv:
            csv_files.append(Path(args.csv))
        elif args.dir:
            csv_files.extend([Path(p) for p in glob.glob(os.path.join(args.dir, "*.csv"))])
        for csv_file in csv_files:
            if csv_file.exists():
                all_ports.extend(
                    parse_csv_file(csv_file, country_names=country_names, wpi_by_locode=wpi_by_locode)
                )
    else:
        all_ports = fetch_remote_unlocode_ports(wpi_csv_path=wpi_path)

    if all_ports:
        logger.info("Saving %d matched maritime ports to %s...", len(all_ports), db_path)
        with db._get_connection() as conn:
            conn.execute("DELETE FROM unlocode_ports;")
            conn.commit()
        db.bulk_insert_ports(all_ports)

        # Also update the seed file so test runs and offline initializations use the real combined dataset
        seed_file = Path(db.seed_path)
        seed_file.parent.mkdir(parents=True, exist_ok=True)
        with open(seed_file, "w", encoding="utf-8") as f:
            json.dump([p.model_dump() for p in all_ports], f, indent=2)
        logger.info("Updated seed snapshot at %s (%d ports).", seed_file, len(all_ports))
        logger.info("Import completed successfully! Total ports in DB: %d", db.count_ports())
    else:
        logger.warning("No maritime port records extracted.")


if __name__ == "__main__":
    main()


