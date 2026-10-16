"""SQLite-backed UN/LOCODE repository with parsing, seeding, and indexing."""

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple
from app.config import get_settings
from app.models.port import Port

logger = logging.getLogger(__name__)


def parse_unlocode_coordinates(coord_str: Optional[str]) -> Optional[Tuple[float, float]]:
    """Parse UNECE standard coordinates (e.g., '5155N 00424E') to (lat, lon) in decimal degrees."""
    if not coord_str or not isinstance(coord_str, str):
        return None
    coord_str = coord_str.strip()
    match = re.match(r"^(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])$", coord_str)
    if not match:
        return None

    lat_deg, lat_min, lat_dir, lon_deg, lon_min, lon_dir = match.groups()
    lat = int(lat_deg) + int(lat_min) / 60.0
    if lat_dir == "S":
        lat = -lat

    lon = int(lon_deg) + int(lon_min) / 60.0
    if lon_dir == "W":
        lon = -lon

    return round(lat, 4), round(lon, 4)


def is_maritime_port(function_code: Optional[str]) -> bool:
    """Determine whether a UN/LOCODE record represents a waterborne/maritime port (Function 1)."""
    if not function_code or not isinstance(function_code, str):
        return False
    func = function_code.strip()
    # In UNECE, function 1 is in the first position or anywhere in the function classifier
    return func.startswith("1") or "1" in func[:2]


def _resolve_data_path(path_str: str) -> str:
    p = Path(path_str)
    if p.is_absolute():
        return str(p)
    if p.exists() or p.parent.exists():
        return str(p)
    parts = p.parts
    if parts and parts[0] == "backend":
        sub = Path(*parts[1:])
        return str(sub)
    return str(p)


class UnlocodeDatabase:
    """Embedded SQLite database for high-performance UN/LOCODE lookups and fuzzy searches."""

    def __init__(self, db_path: Optional[str] = None, seed_path: Optional[str] = None):
        settings = get_settings()
        self.db_path = _resolve_data_path(db_path or settings.UNLOCODE_DB_PATH)
        self.seed_path = _resolve_data_path(seed_path or settings.UNLOCODE_SEED_PATH)

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.seed_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Create port tables and search indexes."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS unlocode_ports (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    locode TEXT NOT NULL UNIQUE,
                    country TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    geofence_radius_nm REAL NOT NULL DEFAULT 8.0,
                    added_by_user_id TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_unlocode_locode ON unlocode_ports(locode);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_unlocode_name ON unlocode_ports(name COLLATE NOCASE);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_unlocode_country ON unlocode_ports(country COLLATE NOCASE);")
            conn.commit()

    def seed_if_empty(self) -> None:
        """Populate database from bundled maritime ports seed if database table is empty."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM unlocode_ports;")
            count = cursor.fetchone()[0]
            if count > 0:
                return

        # Seed from seed file if present
        seed_file = Path(self.seed_path)
        if seed_file.exists():
            try:
                with open(seed_file, "r", encoding="utf-8") as f:
                    ports_data = json.load(f)
                ports = [Port(**item) for item in ports_data]
                self.bulk_insert_ports(ports)
                logger.info("Successfully seeded %d maritime ports into UN/LOCODE database.", len(ports))
            except Exception as e:
                logger.warning("Failed to seed UN/LOCODE database: %s", str(e))

    def bulk_insert_ports(self, ports: List[Port]) -> None:
        """Insert or replace a list of ports in a single transaction."""
        records = [
            (
                p.id,
                p.name,
                p.locode.upper(),
                p.country,
                p.lat,
                p.lon,
                1 if p.isDefault else 0,
                p.geofenceRadiusNm,
                p.addedByUserId,
            )
            for p in ports
        ]
        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO unlocode_ports (
                    id, name, locode, country, lat, lon, is_default, geofence_radius_nm, added_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                records,
            )
            conn.commit()

    def get_port_by_locode(self, locode: str) -> Optional[Port]:
        """Fetch port by 5-character LOCODE."""
        clean_locode = locode.upper().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM unlocode_ports WHERE locode = ? LIMIT 1;",
                (clean_locode,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_port(row)
        return None

    def get_port_by_id(self, port_id: str) -> Optional[Port]:
        """Fetch port by unique ID from UN/LOCODE database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM unlocode_ports WHERE id = ? LIMIT 1;",
                (port_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_port(row)
        return None

    def get_default_ports(self) -> List[Port]:
        """Fetch all global default ports."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM unlocode_ports WHERE is_default = 1 ORDER BY name ASC;")
            rows = cursor.fetchall()
            return [self._row_to_port(r) for r in rows]

    def count_ports(self) -> int:
        """Return total number of ports in database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM unlocode_ports;")
            return cursor.fetchone()[0]

    def search_ports(self, query: str = "", limit: int = 50) -> List[Port]:
        """Search ports with exact LOCODE match priority, followed by name/country matching."""
        q = query.strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not q:
                cursor.execute("SELECT * FROM unlocode_ports ORDER BY name ASC LIMIT ?;", (limit,))
                return [self._row_to_port(r) for r in cursor.fetchall()]

        pattern = f"%{q}%"
        upper_q = q.upper()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *,
                    CASE
                        WHEN locode = ? THEN 1
                        WHEN locode LIKE ? THEN 2
                        WHEN name LIKE ? OR name LIKE ? THEN 3
                        WHEN name LIKE ? THEN 4
                        ELSE 5
                    END AS rank
                FROM unlocode_ports
                WHERE locode LIKE ? OR name LIKE ? OR country LIKE ?
                ORDER BY rank ASC, is_default DESC, name ASC
                LIMIT ?;
                """,
                (
                    upper_q,
                    f"{upper_q}%",
                    f"{q}%",
                    f"Port of {q}%",
                    pattern,
                    pattern,
                    pattern,
                    pattern,
                    limit,
                ),
            )
            rows = cursor.fetchall()
            return [self._row_to_port(r) for r in rows]


    def _row_to_port(self, row: sqlite3.Row) -> Port:
        return Port(
            id=row["id"],
            name=row["name"],
            locode=row["locode"],
            country=row["country"],
            lat=row["lat"],
            lon=row["lon"],
            isDefault=bool(row["is_default"]),
            geofenceRadiusNm=row["geofence_radius_nm"],
            addedByUserId=row["added_by_user_id"],
        )
