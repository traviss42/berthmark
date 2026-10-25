"""Bulk data ingestion pipeline loading UN/LOCODE and WPI into the database."""

import asyncio
import logging
import os
from typing import Any
from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db_session
from backend.ingestion.parser import (
    parse_unlocode_ports,
    parse_wpi_records,
    reconcile_ports,
)
from backend.models import Port

logger = logging.getLogger(__name__)


async def run_ingestion(
    session: AsyncSession,
    data_dir: str = "data",
    drop_existing: bool = True,
    batch_size: int = 1000,
) -> int:
    """Execute complete ingestion pipeline and bulk-insert reconciled ports.

    Args:
        session: Active async SQLAlchemy session.
        data_dir: Base directory containing `unlocode/` and `wpi/` folders.
        drop_existing: If True, clear existing ports before ingestion to guarantee idempotency.
        batch_size: Number of records to insert per Core mapping chunk.

    Returns:
        Total number of ports inserted.
    """
    unlocode_dir = os.path.join(data_dir, "unlocode")
    wpi_file = os.path.join(data_dir, "wpi", "UpdatedPub150.csv")

    logger.info("Parsing UN/LOCODE dataset from %s...", unlocode_dir)
    unlocode_ports = parse_unlocode_ports(unlocode_dir)
    logger.info("Parsed %d maritime ports from UN/LOCODE.", len(unlocode_ports))

    logger.info("Parsing WPI dataset from %s...", wpi_file)
    wpi_records = parse_wpi_records(wpi_file)
    logger.info("Parsed %d entries from WPI.", len(wpi_records))

    logger.info("Reconciling datasets...")
    reconciled = reconcile_ports(unlocode_ports, wpi_records)
    logger.info("Reconciliation complete. Total ports to insert: %d", len(reconciled))

    if drop_existing:
        logger.info("Clearing existing ports table for clean idempotent load...")
        await session.execute(delete(Port))

    # Core bulk insert mappings in batches
    for i in range(0, len(reconciled), batch_size):
        chunk = reconciled[i : i + batch_size]
        await session.execute(insert(Port), chunk)

    await session.commit()
    logger.info("Successfully ingested %d ports.", len(reconciled))
    return len(reconciled)


async def main():
    """CLI entry point for running data ingestion."""
    logging.basicConfig(level=logging.INFO)
    async for session in get_db_session():
        count = await run_ingestion(session)
        print(f"Ingested {count} ports into database.")


if __name__ == "__main__":
    asyncio.run(main())
