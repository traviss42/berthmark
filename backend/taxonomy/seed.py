"""Benchmark vessel classes taxonomy and database seeder."""

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import VesselClass

BENCHMARK_VESSEL_CLASSES: list[dict[str, Any]] = [
    # Containerized
    {
        "class_id": "feeder",
        "class_name": "Feeder",
        "sector": "containerized",
        "draft_m": 8.5,
        "beam_m": 24.0,
        "loa_m": 140.0,
        "criteria": "Length < 150m, Beam < 25m, Draft < 9m",
        "significance": "Rapid turnarounds, high maneuverability, minimal windage.",
    },
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
    # Liquid Bulk
    {
        "class_id": "mrTanker",
        "class_name": "MR / Handysize Tanker",
        "sector": "liquidBulk",
        "draft_m": 11.0,
        "beam_m": 32.2,
        "loa_m": 183.0,
        "criteria": "DWT 25,000–50,000, Draft < 11m",
        "significance": "Regional product/chemical distribution.",
    },
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
    # Dry Bulk
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
    {
        "class_id": "panamaxBulk",
        "class_name": "Panamax (Bulk)",
        "sector": "dryBulk",
        "draft_m": 14.5,
        "beam_m": 32.2,
        "loa_m": 225.0,
        "criteria": "Beam ≤ 32.2m, Draft ≤ 15m",
        "significance": "Major agricultural & coal route standard.",
    },
    {
        "class_id": "capesize",
        "class_name": "Capesize",
        "sector": "dryBulk",
        "draft_m": 18.0,
        "beam_m": 45.0,
        "loa_m": 290.0,
        "criteria": "DWT 120,000+, Draft > 17m",
        "significance": "Deep-water mineral export/import terminals only.",
    },
    # Specialized
    {
        "class_id": "pctc",
        "class_name": "PCC / PCTC (Car Carriers)",
        "sector": "specialized",
        "draft_m": 10.0,
        "beam_m": 32.2,
        "loa_m": 200.0,
        "criteria": "High air draft (> 40m), High sailage",
        "significance": "Extremely sensitive to lateral crosswinds; strict wind holds.",
    },
    {
        "class_id": "lng",
        "class_name": "LNG / LPG Carriers",
        "sector": "specialized",
        "draft_m": 12.0,
        "beam_m": 45.0,
        "loa_m": 290.0,
        "criteria": "Specialized containment profile",
        "significance": "Mandatory safety exclusion zones & tug escorts.",
    },
]


async def seed_vessel_classes(session: AsyncSession) -> int:
    """Idempotently seed all 13 commercial vessel classes into the database."""
    seeded_count = 0
    for vc_data in BENCHMARK_VESSEL_CLASSES:
        result = await session.execute(
            select(VesselClass).where(VesselClass.class_id == vc_data["class_id"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            vclass = VesselClass(
                class_id=vc_data["class_id"],
                class_name=vc_data["class_name"],
                sector=vc_data["sector"],
                draft_m=vc_data["draft_m"],
                beam_m=vc_data["beam_m"],
                loa_m=vc_data["loa_m"],
                criteria=vc_data["criteria"],
                significance=vc_data["significance"],
            )
            session.add(vclass)
            seeded_count += 1
        else:
            existing.class_name = vc_data["class_name"]
            existing.sector = vc_data["sector"]
            existing.draft_m = vc_data["draft_m"]
            existing.beam_m = vc_data["beam_m"]
            existing.loa_m = vc_data["loa_m"]
            existing.criteria = vc_data["criteria"]
            existing.significance = vc_data["significance"]

    await session.commit()
    return seeded_count


# The 7 core benchmark commercial vessel classes
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


async def seed_seven_benchmark_vessel_classes(session: AsyncSession) -> int:
    """Idempotently seed the 7 benchmark vessel classes into the database."""
    seeded_count = 0
    for vc_data in BENCHMARK_7_VESSEL_CLASSES:
        result = await session.execute(
            select(VesselClass).where(VesselClass.class_id == vc_data["class_id"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            vclass = VesselClass(
                class_id=vc_data["class_id"],
                class_name=vc_data["class_name"],
                sector=vc_data["sector"],
                draft_m=vc_data["draft_m"],
                beam_m=vc_data["beam_m"],
                loa_m=vc_data["loa_m"],
                criteria=vc_data["criteria"],
                significance=vc_data["significance"],
            )
            session.add(vclass)
            seeded_count += 1
        else:
            existing.class_name = vc_data["class_name"]
            existing.sector = vc_data["sector"]
            existing.draft_m = vc_data["draft_m"]
            existing.beam_m = vc_data["beam_m"]
            existing.loa_m = vc_data["loa_m"]
            existing.criteria = vc_data["criteria"]
            existing.significance = vc_data["significance"]

    await session.commit()
    return seeded_count
