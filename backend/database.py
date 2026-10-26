"""Asynchronous database engine and session management for Berthmark."""

import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from sqlalchemy import event, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from backend.models import Base, Port, VesselClass

logger = logging.getLogger("backend.database")
DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./berthmark.db"

# The 7 benchmark commercial vessel classes
BENCHMARK_7_VESSEL_CLASSES: list[dict[str, Any]] = [
    # Handymax / Supramax (Draft 10.0m–11.5m, Beam 28m–32m)
    {
        "class_id": "handysize",
        "class_name": "Handymax / Supramax",
        "sector": "dryBulk",
        "draft_m": 10.5,
        "beam_m": 28.0,
        "loa_m": 190.0,
        "criteria": "Draft 10.0m–11.5m, Beam 28m–32m",
        "significance": "Self-sustaining (geared cranes); accesses smaller ports.",
    },
    # Panamax (Draft 12.0m–13.5m, Beam 32.2m)
    {
        "class_id": "panamax",
        "class_name": "Panamax",
        "sector": "containerized",
        "draft_m": 12.0,
        "beam_m": 32.2,
        "loa_m": 290.0,
        "criteria": "Draft 12.0m–13.5m, Beam 32.2m",
        "significance": "Traditional inter-regional trade routes; legacy lock limits.",
    },
    # New Panamax (Draft 15.2m, Beam 49m, LOA 366m)
    {
        "class_id": "neoPanamax",
        "class_name": "New Panamax",
        "sector": "containerized",
        "draft_m": 15.2,
        "beam_m": 49.0,
        "loa_m": 366.0,
        "criteria": "Draft 15.2m, Beam 49m, LOA 366m",
        "significance": "High capacity; expanded canal constraint rules.",
    },
    # Aframax (Draft 14.5m–15.0m, Beam 44m)
    {
        "class_id": "aframax",
        "class_name": "Aframax",
        "sector": "liquidBulk",
        "draft_m": 14.8,
        "beam_m": 44.0,
        "loa_m": 245.0,
        "criteria": "Draft 14.5m–15.0m, Beam 44m",
        "significance": "Medium-depth crude routes and lightering ops.",
    },
    # Suezmax (Draft 16.0m–17.0m, Beam 50m)
    {
        "class_id": "suezmax",
        "class_name": "Suezmax",
        "sector": "liquidBulk",
        "draft_m": 16.0,
        "beam_m": 50.0,
        "loa_m": 274.0,
        "criteria": "Draft 16.0m–17.0m, Beam 50m",
        "significance": "Constrained by canal draft & deep-water channels.",
    },
    # VLCC (Draft 20.0m–21.5m, Beam 60m)
    {
        "class_id": "vlcc",
        "class_name": "VLCC",
        "sector": "liquidBulk",
        "draft_m": 21.0,
        "beam_m": 60.0,
        "loa_m": 333.0,
        "criteria": "Draft 20.0m–21.5m, Beam 60m",
        "significance": "Deep-draft offshore SPM or deep terminal restrictions.",
    },
    # ULCS (Draft 15.5m–16.5m, Beam 59m)
    {
        "class_id": "ulcv",
        "class_name": "ULCS",
        "sector": "containerized",
        "draft_m": 16.0,
        "beam_m": 59.0,
        "loa_m": 400.0,
        "criteria": "Draft 15.5m–16.5m, Beam 59m",
        "significance": "Severe wind sailage impact; channel squat & strict depth limits.",
    },
]


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints on SQLite connections."""
    if hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_database_url() -> str:
    """Retrieve and normalize database URL from environment."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("sqlite:///"):
        # Normalize sqlite:/// to sqlite+aiosqlite:///
        url = "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    return url


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = get_database_url()
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create singleton async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session that commits on success and rolls back on exception."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ping_database() -> bool:
    """Test connectivity by executing SELECT 1 on the database."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        scalar = result.scalar()
        return scalar == 1


async def reset_engine() -> None:
    """Dispose active engine and reset singletons (useful for test isolation)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_seed_data_path() -> Path:
    """Resolve absolute path to app/data/ports_seed.json reference seed dataset."""
    env_path = os.getenv("PORTS_SEED_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    repo_root = Path(__file__).resolve().parent.parent
    candidate = repo_root / "app" / "data" / "ports_seed.json"
    if candidate.exists():
        return candidate

    docker_candidate = Path("/app/app/data/ports_seed.json")
    if docker_candidate.exists():
        return docker_candidate

    return candidate


async def auto_init_database(engine: AsyncEngine | None = None) -> bool:
    """Auto-initialize database schema and bulk-seed ports and vessel classes on boot.

    Executes Base.metadata.create_all() to create berthmark.db and all required tables
    if they do not exist. Then checks SELECT COUNT(*) FROM ports;:
    - If COUNT == 0: Loads app/data/ports_seed.json and bulk inserts ports,
      bulk inserts the 7 benchmark vessel classes, and creates default user.
    - If COUNT > 0: Skips seeding instantly.

    Returns:
        bool: True if initial seeding was executed; False if already seeded.
    """
    target_engine = engine or get_engine()

    # 1. Auto-schema creation: execute Base.metadata.create_all() to ensure all tables exist
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Automated bulk seed check: SELECT COUNT(*) FROM ports;
    session_factory = async_sessionmaker(
        bind=target_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM ports"))
        ports_count = result.scalar() or 0

        if ports_count > 0:
            logger.info("Database already seeded (ports count = %d). Skipping seeding.", ports_count)
            return False

        logger.info("Fresh database detected (ports count = 0). Executing automated bulk seeding...")

        # 3. Load app/data/ports_seed.json (run ETL script if file is missing)
        seed_path = get_seed_data_path()
        if not seed_path.exists():
            logger.warning(
                "Reference ports seed file %s not found. Running scripts/build_seed_data.py...",
                seed_path,
            )
            from scripts.build_seed_data import main as build_seed_main
            build_seed_main()

        with open(seed_path, "r", encoding="utf-8") as f:
            ports_data = json.load(f)

        # Bulk insert ports into ports table in batches for high-speed insertion
        batch_size = 500
        for i in range(0, len(ports_data), batch_size):
            batch = ports_data[i : i + batch_size]
            await session.execute(insert(Port), batch)

        # 4. Bulk-insert the 7 benchmark vessel classes into vessel_classes
        for vc in BENCHMARK_7_VESSEL_CLASSES:
            existing = await session.execute(
                select(VesselClass).where(VesselClass.class_id == vc["class_id"])
            )
            if existing.scalar_one_or_none() is None:
                session.add(VesselClass(**vc))

        await session.commit()
        logger.info(
            "Bulk seeding successfully finished: %d ports, %d vessel classes inserted.",
            len(ports_data),
            len(BENCHMARK_7_VESSEL_CLASSES),
        )
        return True

