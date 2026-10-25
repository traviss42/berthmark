"""Service layer with in-memory caching for vessel taxonomy retrieval."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import VesselClass
from backend.taxonomy.schemas import VesselClassInfo

# Sector ordering for deterministic presentation
SECTOR_ORDER = {
    "containerized": 0,
    "liquidBulk": 1,
    "dryBulk": 2,
    "specialized": 3,
}

_vessel_classes_cache: list[VesselClassInfo] | None = None


def clear_vessel_classes_cache() -> None:
    """Clear in-memory cache (used by seed operations and tests)."""
    global _vessel_classes_cache
    _vessel_classes_cache = None


async def get_vessel_classes(session: AsyncSession) -> list[VesselClassInfo]:
    """Retrieve all vessel classes with in-memory caching and deterministic ordering."""
    global _vessel_classes_cache
    if _vessel_classes_cache is not None:
        return _vessel_classes_cache

    result = await session.execute(select(VesselClass))
    records = result.scalars().all()

    if not records:
        return []

    items = [
        VesselClassInfo(
            id=record.class_id,
            label=record.class_name,
            sector=record.sector or "containerized",
            criteria=record.criteria or "",
            significance=record.significance or "",
        )
        for record in records
    ]

    # Deterministic sort: sector group first, then class_id
    items.sort(key=lambda x: (SECTOR_ORDER.get(x.sector, 99), x.id))

    _vessel_classes_cache = items
    return _vessel_classes_cache
