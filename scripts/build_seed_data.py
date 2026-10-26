#!/usr/bin/env python3
"""Offline Dataset ETL & Seed Generation Script.

Reconciles UN/LOCODE maritime ports and World Port Index (WPI) physical depth records,
generating the clean static reference seed file at app/data/ports_seed.json.
"""

import csv
import difflib
import glob
import json
import logging
import math
import os
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("build_seed_data")

DEFAULT_LOCODE_ALIASES: dict[str, str] = {
    "SGSIN": "SGKEP",  # Singapore main port maps to Keppel Harbor (WPI 50000.0)
}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth's radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def parse_unlocode_coordinates(coord_str: str | None) -> tuple[float | None, float | None]:
    """Parse UN/LOCODE coordinate string ('DDMM[N/S] DDDMM[E/W]') to signed decimal degrees."""
    if not coord_str or not isinstance(coord_str, str):
        return None, None

    cleaned = coord_str.strip().upper()
    pattern = r"^(\d{2})(\d{2})([NS])\s*(\d{2,3})(\d{2})([EW])$"
    match = re.match(pattern, cleaned)
    if not match:
        return None, None

    lat_deg, lat_min, lat_hemi, lon_deg, lon_min, lon_hemi = match.groups()
    lat = int(lat_deg) + int(lat_min) / 60.0
    if lat_hemi == "S":
        lat = -lat

    lon = int(lon_deg) + int(lon_min) / 60.0
    if lon_hemi == "W":
        lon = -lon

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None

    return round(lat, 6), round(lon, 6)


def load_subdivision_codes(csv_path: str) -> dict[tuple[str, str], str]:
    """Load SubdivisionCodes.csv mapping (country_code, subdivision) -> full subdivision_code."""
    subdivisions: dict[tuple[str, str], str] = {}
    if not os.path.exists(csv_path):
        return subdivisions

    for encoding in ("utf-8-sig", "latin1"):
        try:
            with open(csv_path, mode="r", encoding=encoding) as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and row[1].strip():
                        c_code = row[0].strip().upper()
                        s_code = row[1].strip().upper()
                        subdivisions[(c_code, s_code)] = f"{c_code}-{s_code}"
            break
        except UnicodeDecodeError:
            continue
    return subdivisions


def build_country_name_to_iso(unlocode_dir: str) -> dict[str, str]:
    """Build country name to ISO 2-letter code mapping from UN/LOCODE headers."""
    country_map: dict[str, str] = {
        "united states": "US",
        "united states of america": "US",
        "united kingdom": "GB",
        "netherlands": "NL",
        "singapore": "SG",
        "china": "CN",
        "belgium": "BE",
        "germany": "DE",
        "france": "FR",
        "spain": "ES",
        "italy": "IT",
        "japan": "JP",
        "south korea": "KR",
        "korea, republic of": "KR",
        "russia": "RU",
        "russian federation": "RU",
        "australia": "AU",
        "brazil": "BR",
        "canada": "CA",
        "india": "IN",
        "indonesia": "ID",
        "malaysia": "MY",
        "united arab emirates": "AE",
        "saudi arabia": "SA",
        "panama": "PA",
        "egypt": "EG",
        "south africa": "ZA",
    }

    codelist_files = sorted(glob.glob(os.path.join(unlocode_dir, "UNLOCODE CodeListPart*.csv")))
    for file_path in codelist_files:
        for encoding in ("utf-8-sig", "latin1"):
            try:
                with open(file_path, mode="r", encoding=encoding) as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 4 and row[1].strip() and not row[2].strip() and row[3].strip().startswith('.'):
                            code = row[1].strip().upper()
                            name = row[3].strip().lstrip('.').strip().lower()
                            # Clean parenthetical qualifiers
                            clean_name = re.sub(r"\s*\([^)]*\)", "", name).strip()
                            country_map[clean_name] = code
                            country_map[name] = code
                break
            except UnicodeDecodeError:
                continue

    return country_map


def parse_unlocode_ports(unlocode_dir: str) -> dict[str, dict[str, Any]]:
    """Parse UN/LOCODE CodeList CSV parts and extract maritime ports (function '1')."""
    subdivisions = load_subdivision_codes(os.path.join(unlocode_dir, "SubdivisionCodes.csv"))
    codelist_files = sorted(glob.glob(os.path.join(unlocode_dir, "UNLOCODE CodeListPart*.csv")))

    ports: dict[str, dict[str, Any]] = {}

    for file_path in codelist_files:
        for encoding in ("utf-8-sig", "latin1"):
            try:
                with open(file_path, mode="r", encoding=encoding) as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) < 7:
                            continue
                        country_code = row[1].strip().upper()
                        location_code = row[2].strip().upper()

                        if not country_code or not location_code or len(location_code) != 3:
                            continue

                        # Filter for maritime port function ('1' in Function column)
                        function_col = row[6].strip()
                        if "1" not in function_col:
                            continue

                        unlocode = f"{country_code}{location_code}"
                        # Prefer name without diacritics (col 4) if available, else col 3
                        raw_name = (row[4] or row[3] or unlocode).strip()
                        port_name = raw_name[:100]

                        subdiv_raw = row[5].strip().upper() if len(row) > 5 else ""
                        if subdiv_raw:
                            subdivision_code = subdivisions.get(
                                (country_code, subdiv_raw), f"{country_code}-{subdiv_raw}"
                            )
                        else:
                            subdivision_code = f"{country_code}"

                        coord_str = row[10].strip() if len(row) > 10 else None
                        lat, lon = parse_unlocode_coordinates(coord_str)

                        ports[unlocode] = {
                            "unlocode": unlocode,
                            "port_name": port_name,
                            "country_code": country_code[:2],
                            "subdivision_code": subdivision_code[:10],
                            "latitude": lat,
                            "longitude": lon,
                        }
                break
            except UnicodeDecodeError:
                continue

    return ports


def parse_wpi_records(wpi_csv_path: str, country_map: dict[str, str]) -> list[dict[str, Any]]:
    """Parse WPI UpdatedPub150.csv extracting depth measurements and physical metadata."""
    if not os.path.exists(wpi_csv_path):
        raise FileNotFoundError(f"WPI file not found: {wpi_csv_path}")

    records: list[dict[str, Any]] = []

    for encoding in ("utf-8-sig", "latin1"):
        try:
            with open(wpi_csv_path, mode="r", encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_wpi = row.get("World Port Index Number", "").strip()
                    if not raw_wpi:
                        continue
                    try:
                        wpi_number = int(float(raw_wpi))
                    except ValueError:
                        continue

                    raw_locode = row.get("UN/LOCODE", "") or ""
                    locode = raw_locode.replace(" ", "").strip().upper()

                    raw_country = (row.get("Country Code") or "").strip()
                    # Map country name to ISO 2-letter code if necessary
                    if len(raw_country) == 2 and raw_country.isalpha():
                        country_iso = raw_country.upper()
                    else:
                        norm_country = raw_country.lower()
                        clean_norm = re.sub(r"\s*\([^)]*\)", "", norm_country).strip()
                        country_iso = country_map.get(clean_norm, country_map.get(norm_country, ""))

                    def parse_depth(key: str) -> float | None:
                        val = row.get(key, "").strip()
                        if not val:
                            return None
                        try:
                            d = float(val)
                            return round(d, 2) if d > 0.0 else None
                        except ValueError:
                            return None

                    def parse_coord(key: str) -> float | None:
                        val = row.get(key, "").strip()
                        if not val:
                            return None
                        try:
                            return round(float(val), 6)
                        except ValueError:
                            return None

                    records.append({
                        "wpi_number": wpi_number,
                        "main_port_name": (row.get("Main Port Name") or "").strip(),
                        "locode": locode if len(locode) == 5 else None,
                        "country_code": country_iso,
                        "channel_depth_m": parse_depth("Channel Depth (m)"),
                        "cargo_pier_depth_m": parse_depth("Cargo Pier Depth (m)"),
                        "anchorage_depth_m": parse_depth("Anchorage Depth (m)"),
                        "latitude": parse_coord("Latitude"),
                        "longitude": parse_coord("Longitude"),
                    })
            break
        except UnicodeDecodeError:
            continue

    return records


def build_ports_seed(
    unlocode_ports: dict[str, dict[str, Any]],
    wpi_records: list[dict[str, Any]],
    output_path: str,
) -> list[dict[str, Any]]:
    """Reconcile WPI and UN/LOCODE records into ports_seed.json format.

    Reconciliation Logic:
    1. Primary Join: Inner-join WPI and UN/LOCODE records using WPI's built-in 5-character
       unlocode attribute (with benchmark alias fallback). Tagged as "EXACT_UNLOCODE".
    2. Secondary Fuzzy/Spatial Match: For WPI port records missing an explicit UN/LOCODE tag,
       perform a fuzzy string match on port names combined with distance proximity (<= 10 km)
       and matching ISO country codes. Tagged as "FUZZY_SPATIAL".
    3. Set is_depth_available = true if channel_depth_m or anchorage_depth_m contains
       non-null depth values; otherwise false.
    """
    alias_map = dict(DEFAULT_LOCODE_ALIASES)

    # Index WPI records by LOCODE (deduplicating by deepest channel depth)
    wpi_by_locode: dict[str, dict[str, Any]] = {}
    unmatched_wpi: list[dict[str, Any]] = []

    for wpi in wpi_records:
        locode = wpi["locode"]
        if locode:
            if locode not in wpi_by_locode:
                wpi_by_locode[locode] = wpi
            else:
                existing_depth = wpi_by_locode[locode].get("channel_depth_m") or 0.0
                current_depth = wpi.get("channel_depth_m") or 0.0
                if current_depth > existing_depth:
                    wpi_by_locode[locode] = wpi
        else:
            unmatched_wpi.append(wpi)

    reconciled_ports: dict[str, dict[str, Any]] = {}
    assigned_wpi_numbers: set[int] = set()

    # 1. Primary Join: Exact UN/LOCODE match
    for unlocode, u_port in unlocode_ports.items():
        lookup_key = alias_map.get(unlocode, unlocode)
        wpi_match = wpi_by_locode.get(lookup_key)

        if wpi_match:
            ch_depth = wpi_match["channel_depth_m"]
            anc_depth = wpi_match["anchorage_depth_m"]
            is_depth_available = bool(
                (ch_depth is not None and ch_depth > 0.0)
                or (anc_depth is not None and anc_depth > 0.0)
            )

            # Prefer UN/LOCODE coordinates; fallback to WPI coordinates
            lat = u_port["latitude"] if u_port["latitude"] is not None else wpi_match["latitude"]
            lon = u_port["longitude"] if u_port["longitude"] is not None else wpi_match["longitude"]

            if lat is None or lon is None:
                continue

            wpi_num = wpi_match["wpi_number"]
            if wpi_num is not None and wpi_num not in assigned_wpi_numbers:
                assigned_wpi_numbers.add(wpi_num)
                final_wpi = wpi_num
            else:
                final_wpi = None

            reconciled_ports[unlocode] = {
                "unlocode": unlocode,
                "port_name": u_port["port_name"],
                "country_code": u_port["country_code"],
                "subdivision_code": u_port["subdivision_code"],
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "wpi_number": final_wpi,
                "channel_depth_m": ch_depth,
                "cargo_pier_depth_m": wpi_match["cargo_pier_depth_m"],
                "anchorage_depth_m": anc_depth,
                "is_depth_available": is_depth_available,
                "reconciliation_method": "EXACT_UNLOCODE",
            }

    # 2. Secondary Fuzzy/Spatial Match for WPI records missing explicit UN/LOCODE
    # Index remaining UN/LOCODE ports by country for fast proximity search
    unmatched_uports_by_country: dict[str, list[dict[str, Any]]] = {}
    for unlocode, u_port in unlocode_ports.items():
        if unlocode in reconciled_ports or u_port["latitude"] is None or u_port["longitude"] is None:
            continue
        c = u_port["country_code"]
        unmatched_uports_by_country.setdefault(c, []).append(u_port)

    for wpi in unmatched_wpi:
        wpi_country = wpi["country_code"]
        wpi_lat = wpi["latitude"]
        wpi_lon = wpi["longitude"]
        wpi_name = wpi["main_port_name"].lower()

        if not wpi_country or wpi_lat is None or wpi_lon is None:
            continue

        candidate_ports = unmatched_uports_by_country.get(wpi_country, [])
        best_uport: dict[str, Any] | None = None
        best_score = -1.0

        for u_port in candidate_ports:
            dist = haversine_distance_km(wpi_lat, wpi_lon, u_port["latitude"], u_port["longitude"])
            if dist <= 10.0:
                # Calculate name similarity
                u_name = u_port["port_name"].lower()
                ratio = difflib.SequenceMatcher(None, wpi_name, u_name).ratio()
                # Score combines high proximity and string similarity
                score = ratio + (1.0 - (dist / 10.0)) * 0.2
                if ratio >= 0.4 and score > best_score:
                    best_score = score
                    best_uport = u_port

        if best_uport:
            target_locode = best_uport["unlocode"]
            if target_locode not in reconciled_ports:
                ch_depth = wpi["channel_depth_m"]
                anc_depth = wpi["anchorage_depth_m"]
                is_depth_available = bool(
                    (ch_depth is not None and ch_depth > 0.0)
                    or (anc_depth is not None and anc_depth > 0.0)
                )

                wpi_num = wpi["wpi_number"]
                if wpi_num is not None and wpi_num not in assigned_wpi_numbers:
                    assigned_wpi_numbers.add(wpi_num)
                    final_wpi = wpi_num
                else:
                    final_wpi = None

                reconciled_ports[target_locode] = {
                    "unlocode": target_locode,
                    "port_name": best_uport["port_name"],
                    "country_code": best_uport["country_code"],
                    "subdivision_code": best_uport["subdivision_code"],
                    "latitude": round(best_uport["latitude"], 6),
                    "longitude": round(best_uport["longitude"], 6),
                    "wpi_number": final_wpi,
                    "channel_depth_m": ch_depth,
                    "cargo_pier_depth_m": wpi["cargo_pier_depth_m"],
                    "anchorage_depth_m": anc_depth,
                    "is_depth_available": is_depth_available,
                    "reconciliation_method": "FUZZY_SPATIAL",
                }

    # Sort output consistently by UN/LOCODE
    output_list = sorted(reconciled_ports.values(), key=lambda p: p["unlocode"])

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_list, f, indent=2)

    logger.info("Wrote %d reconciled ports to %s", len(output_list), output_path)
    return output_list


def main():
    """Main build seed data entry point."""
    root_dir = Path(__file__).resolve().parent.parent
    unlocode_dir = str(root_dir / "data" / "unlocode")
    wpi_file = str(root_dir / "data" / "wpi" / "UpdatedPub150.csv")
    output_path = str(root_dir / "app" / "data" / "ports_seed.json")

    logger.info("Loading country name mapping...")
    country_map = build_country_name_to_iso(unlocode_dir)

    logger.info("Parsing UN/LOCODE ports from %s...", unlocode_dir)
    unlocode_ports = parse_unlocode_ports(unlocode_dir)
    logger.info("Parsed %d maritime ports from UN/LOCODE", len(unlocode_ports))

    logger.info("Parsing WPI records from %s...", wpi_file)
    wpi_records = parse_wpi_records(wpi_file, country_map)
    logger.info("Parsed %d records from WPI", len(wpi_records))

    logger.info("Reconciling datasets and generating %s...", output_path)
    result = build_ports_seed(unlocode_ports, wpi_records, output_path)

    exact_count = sum(1 for p in result if p["reconciliation_method"] == "EXACT_UNLOCODE")
    fuzzy_count = sum(1 for p in result if p["reconciliation_method"] == "FUZZY_SPATIAL")
    depth_count = sum(1 for p in result if p["is_depth_available"])

    logger.info("Reconciliation Summary:")
    logger.info("  Total Reconciled Ports: %d", len(result))
    logger.info("  EXACT_UNLOCODE Matches: %d", exact_count)
    logger.info("  FUZZY_SPATIAL Matches:  %d", fuzzy_count)
    logger.info("  Ports with Depth Available: %d", depth_count)


if __name__ == "__main__":
    main()
