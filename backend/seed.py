"""Unified database seeding entrypoint for Berthmark."""

import asyncio
import logging
from backend.auth.seed import seed_default_user
from backend.database import get_session_factory
from backend.ports.service import seed_benchmark_ports
from backend.taxonomy.seed import seed_vessel_classes

logger = logging.getLogger("backend.seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def run_seeders() -> dict[str, int | str]:
    """Execute all idempotent database seeders."""
    session_factory = get_session_factory()
    stats: dict[str, int | str] = {}

    async with session_factory() as session:
        logger.info("Seeding vessel classes taxonomy...")
        classes_count = await seed_vessel_classes(session)
        stats["vessel_classes"] = classes_count
        logger.info("Vessel classes seeded/verified: %d", classes_count)

        logger.info("Seeding default operator user...")
        user = await seed_default_user(session)
        stats["default_user"] = user.email
        logger.info("Default operator user verified: %s", user.email)

        logger.info("Seeding default benchmark ports...")
        ports_count = await seed_benchmark_ports(session)
        stats["benchmark_ports"] = ports_count
        logger.info("Benchmark ports seeded/verified: %d", ports_count)

    return stats


def main() -> None:
    """Synchronous CLI entrypoint."""
    asyncio.run(run_seeders())


if __name__ == "__main__":
    main()
