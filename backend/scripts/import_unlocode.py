"""CLI utility to import and parse official UNECE UN/LOCODE releases into SQLite.

Usage examples:
    # 1. Parse a downloaded UNECE CSV file:
    python backend/scripts/import_unlocode.py --csv path/to/2024-1_CodeList.csv

    # 2. Parse a directory containing multiple CodeListPart*.csv files:
    python backend/scripts/import_unlocode.py --dir path/to/unlocode_csvs/

    # 3. Seed from bundled maritime seed data:
    python backend/scripts/import_unlocode.py --seed
"""

import argparse
import csv
import glob
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

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


def parse_csv_file(file_path: Path) -> List[Port]:
    """Parse a UNECE UN/LOCODE CSV file, filter for maritime ports, and extract coordinates."""
    ports: List[Port] = []
    logger.info("Scanning %s...", file_path)

    encodings_to_try = ["utf-8", "latin-1", "cp1252"]
    reader = None

    for enc in encodings_to_try:
        try:
            with open(file_path, "r", encoding=enc) as f:
                # Read sample to verify encoding
                f.read(2048)
                f.seek(0)
                csv_reader = csv.reader(f)
                rows = list(csv_reader)
                reader = rows
                break
        except (UnicodeDecodeError, Exception):
            continue

    if reader is None:
        logger.error("Could not read %s with standard encodings.", file_path)
        return []

    count_total = 0
    count_maritime = 0
    count_valid_coords = 0

    for row in reader:
        count_total += 1
        if len(row) < 10:
            continue

        # Standard UNECE layout or header check
        # Col 1: Country, Col 2: Locode, Col 3: Name, Col 4: NameWoDiacritics
        # Col 6: Function, Col 9 or 10: Coordinates
        country_code = row[1].strip()
        location_code = row[2].strip()

        # Skip headers or empty locodes
        if not country_code or not location_code or len(country_code) != 2:
            continue

        full_locode = f"{country_code}{location_code}".upper()

        name = row[4].strip() or row[3].strip()
        function_code = row[6].strip() if len(row) > 6 else ""
        coord_raw = ""

        # Coordinates may be in col 9 or 10 depending on release format
        for col_idx in [10, 9, 8]:
            if len(row) > col_idx and any(c in row[col_idx] for c in ["N", "S"]):
                coord_raw = row[col_idx].strip()
                break

        # Filter: only waterborne / maritime ports (Function position 1 = '1')
        if not is_maritime_port(function_code):
            continue

        count_maritime += 1
        coords = parse_unlocode_coordinates(coord_raw)
        if not coords:
            continue

        count_valid_coords += 1
        lat, lon = coords
        port_id = f"port-{full_locode.lower()}"

        ports.append(
            Port(
                id=port_id,
                name=f"Port of {name}" if not name.lower().startswith("port") else name,
                locode=full_locode,
                country=country_code,
                lat=lat,
                lon=lon,
                isDefault=False,
                geofenceRadiusNm=8.0,
                addedByUserId=None,
            )
        )

    logger.info(
        "File %s summary: Total rows=%d, Maritime ports=%d, Valid coords=%d",
        file_path.name,
        count_total,
        count_maritime,
        count_valid_coords,
    )
    return ports


def main():
    parser = argparse.ArgumentParser(description="Import UNECE UN/LOCODE data into Berthmark SQLite DB")
    parser.add_argument("--csv", help="Path to single UNECE CodeList CSV file")
    parser.add_argument("--dir", help="Directory containing multiple CodeListPart*.csv files")
    parser.add_argument("--seed", action="store_true", help="Re-seed database from default maritime_ports.json")
    parser.add_argument("--db", help="Target SQLite database path (defaults to config UNLOCODE_DB_PATH)")
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db or settings.UNLOCODE_DB_PATH
    db = UnlocodeDatabase(db_path=db_path)

    if args.seed:
        logger.info("Seeding database %s from bundled dataset %s...", db_path, settings.UNLOCODE_SEED_PATH)
        count = db.count_ports()
        logger.info("Done. Total ports in DB: %d", count)
        return

    csv_files: List[Path] = []
    if args.csv:
        csv_files.append(Path(args.csv))
    elif args.dir:
        csv_files.extend([Path(p) for p in glob.glob(os.path.join(args.dir, "*.csv"))])
    else:
        logger.info("No --csv or --dir provided. Ensuring database is initialized and seeded...")
        db.init_db()
        db.seed_if_empty()
        print("\nDatabase ready at:", db_path)
        print("To import full official UNECE releases, run:")
        print("    python backend/scripts/import_unlocode.py --csv <path-to-unlocode.csv>")
        print("    python backend/scripts/import_unlocode.py --dir <directory-with-parts>")
        return

    all_ports: List[Port] = []
    for csv_file in csv_files:
        if csv_file.exists():
            ports = parse_csv_file(csv_file)
            all_ports.extend(ports)

    if all_ports:
        logger.info("Saving %d maritime ports to %s...", len(all_ports), db_path)
        db.bulk_insert_ports(all_ports)
        logger.info("Import completed successfully!")
    else:
        logger.warning("No maritime port records extracted from provided files.")


if __name__ == "__main__":
    main()
