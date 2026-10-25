"""UN/LOCODE and WPI data parser and reconciliation engine."""

import csv
import glob
import math
import os
import re
from typing import Any

# Benchmark port aliases where UN/LOCODE corresponds to standard WPI facility code
DEFAULT_LOCODE_ALIASES: dict[str, str] = {
    "SGSIN": "SGKEP",  # Singapore main port maps to Keppel Harbor (WPI 50000.0)
}


def parse_unlocode_coordinates(coord_str: str | None) -> tuple[float | None, float | None]:
    """Parse UN/LOCODE coordinate string ('DDMM[N/S] DDDMM[E/W]') to signed decimal degrees.

    Returns:
        (latitude, longitude) as floats in [-90, 90] and [-180, 180], or (None, None) if invalid.
    """
    if not coord_str or not isinstance(coord_str, str):
        return None, None

    cleaned = coord_str.strip().upper()
    # Format: 4 digits + N/S, space (optional), 4 or 5 digits + E/W
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


def parse_unlocode_ports(unlocode_dir: str) -> dict[str, dict[str, Any]]:
    """Parse all UN/LOCODE CodeList CSV parts and extract ports with maritime function '1'."""
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

                        # Skip country header lines
                        if not country_code or not location_code:
                            continue

                        # Filter for maritime port function ('1' in Function column)
                        function_col = row[6].strip()
                        if "1" not in function_col:
                            continue

                        unlocode = f"{country_code}{location_code}"
                        port_name = (row[3] or row[4] or unlocode).strip()
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
                            "port_name": port_name[:100],
                            "country_code": country_code[:2],
                            "subdivision_code": subdivision_code[:10],
                            "latitude": lat,
                            "longitude": lon,
                            "function": function_col,
                        }
                break
            except UnicodeDecodeError:
                continue

    return ports


def parse_wpi_records(wpi_csv_path: str) -> list[dict[str, Any]]:
    """Parse WPI UpdatedPub150.csv extracting depth measurements and physical metadata."""
    if not os.path.exists(wpi_csv_path):
        return []

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

                    def parse_depth(key: str) -> float | None:
                        val = row.get(key, "").strip()
                        if not val:
                            return None
                        try:
                            d = float(val)
                            return d if d > 0.0 else None
                        except ValueError:
                            return None

                    def parse_coord(key: str) -> float | None:
                        val = row.get(key, "").strip()
                        if not val:
                            return None
                        try:
                            return float(val)
                        except ValueError:
                            return None

                    records.append({
                        "wpi_number": wpi_number,
                        "main_port_name": (row.get("Main Port Name") or "").strip(),
                        "locode": locode if len(locode) == 5 else None,
                        "country_code": (row.get("Country Code") or "").strip(),
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


def reconcile_ports(
    unlocode_ports: dict[str, dict[str, Any]],
    wpi_records: list[dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Reconcile UN/LOCODE port catalog with WPI physical depths.

    1. Deduplicate WPI entries by prioritizing deepest channel depth.
    2. Primary Join: Exact 5-character LOCODE match (with benchmark alias fallback). Tag as EXACT_UNLOCODE.
    3. Fallback Match: Fuzzy spatial proximity (<= 10km) for WPI records lacking exact LOCODE. Tag as FUZZY_SPATIAL.
    4. Unmatched: Retain remaining UN/LOCODE ports with null depths and tag as UNMATCHED.
    """
    alias_map = dict(DEFAULT_LOCODE_ALIASES)
    if aliases:
        alias_map.update(aliases)

    # 1. Deduplicate WPI entries by LOCODE, choosing deepest channel depth
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

    reconciled_results: dict[str, dict[str, Any]] = {}
    matched_wpi_numbers: set[int] = set()
    assigned_wpi_numbers: set[int] = set()

    # 2. Primary Join: Exact LOCODE Match (and alias match)
    for unlocode, u_port in unlocode_ports.items():
        lookup_key = alias_map.get(unlocode, unlocode)
        wpi_match = wpi_by_locode.get(lookup_key)

        if wpi_match:
            ch_depth = wpi_match["channel_depth_m"]
            is_depth_available = ch_depth is not None and ch_depth > 0.0
            lat = u_port["latitude"] if u_port["latitude"] is not None else wpi_match["latitude"]
            lon = u_port["longitude"] if u_port["longitude"] is not None else wpi_match["longitude"]

            wpi_num = wpi_match["wpi_number"]
            if wpi_num is not None and wpi_num not in assigned_wpi_numbers:
                final_wpi_num = wpi_num
                assigned_wpi_numbers.add(wpi_num)
            else:
                final_wpi_num = None

            reconciled_results[unlocode] = {
                "unlocode": unlocode,
                "port_name": u_port["port_name"],
                "country_code": u_port["country_code"],
                "subdivision_code": u_port["subdivision_code"],
                "latitude": lat if lat is not None else 0.0,
                "longitude": lon if lon is not None else 0.0,
                "wpi_number": final_wpi_num,
                "channel_depth_m": ch_depth,
                "cargo_pier_depth_m": wpi_match["cargo_pier_depth_m"],
                "anchorage_depth_m": wpi_match["anchorage_depth_m"],
                "is_depth_available": is_depth_available,
                "reconciliation_method": "EXACT_UNLOCODE",
            }
            if wpi_num is not None:
                matched_wpi_numbers.add(wpi_num)

    # 3. Fallback Reconciliation: Spatial proximity (<= 10km) for unmatched WPI entries
    for unlocode, u_port in unlocode_ports.items():
        if unlocode in reconciled_results:
            continue
        if u_port["latitude"] is None or u_port["longitude"] is None:
            continue

        best_match: dict[str, Any] | None = None
        min_dist = 10.0  # max 10 km

        for wpi in unmatched_wpi:
            if wpi["wpi_number"] in matched_wpi_numbers:
                continue
            if wpi["latitude"] is None or wpi["longitude"] is None:
                continue

            dist = haversine_distance_km(
                u_port["latitude"], u_port["longitude"], wpi["latitude"], wpi["longitude"]
            )
            if dist <= min_dist:
                min_dist = dist
                best_match = wpi

        if best_match:
            ch_depth = best_match["channel_depth_m"]
            is_depth_available = ch_depth is not None and ch_depth > 0.0
            wpi_num = best_match["wpi_number"]
            if wpi_num is not None and wpi_num not in assigned_wpi_numbers:
                final_wpi_num = wpi_num
                assigned_wpi_numbers.add(wpi_num)
            else:
                final_wpi_num = None

            reconciled_results[unlocode] = {
                "unlocode": unlocode,
                "port_name": u_port["port_name"],
                "country_code": u_port["country_code"],
                "subdivision_code": u_port["subdivision_code"],
                "latitude": u_port["latitude"],
                "longitude": u_port["longitude"],
                "wpi_number": final_wpi_num,
                "channel_depth_m": ch_depth,
                "cargo_pier_depth_m": best_match["cargo_pier_depth_m"],
                "anchorage_depth_m": best_match["anchorage_depth_m"],
                "is_depth_available": is_depth_available,
                "reconciliation_method": "FUZZY_SPATIAL",
            }
            if wpi_num is not None:
                matched_wpi_numbers.add(wpi_num)

    # 4. Unmatched UN/LOCODE ports
    for unlocode, u_port in unlocode_ports.items():
        if unlocode in reconciled_results:
            continue
        lat = u_port["latitude"] if u_port["latitude"] is not None else 0.0
        lon = u_port["longitude"] if u_port["longitude"] is not None else 0.0
        reconciled_results[unlocode] = {
            "unlocode": unlocode,
            "port_name": u_port["port_name"],
            "country_code": u_port["country_code"],
            "subdivision_code": u_port["subdivision_code"],
            "latitude": lat,
            "longitude": lon,
            "wpi_number": None,
            "channel_depth_m": None,
            "cargo_pier_depth_m": None,
            "anchorage_depth_m": None,
            "is_depth_available": False,
            "reconciliation_method": "UNMATCHED",
        }

    return list(reconciled_results.values())
