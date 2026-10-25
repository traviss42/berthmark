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
        "class_name": "Panamax / Sub-Panamax",
        "sector": "containerized",
        "draft_m": 12.0,
        "beam_m": 32.2,
        "loa_m": 290.0,
        "criteria": "Length 150–290m, Beam ≤ 32.2m, Draft ≤ 12m",
        "significance": "Traditional inter-regional trade routes; legacy lock limits.",
    },
    {
        "class_id": "neoPanamax",
        "class_name": "Neo-Panamax",
        "sector": "containerized",
        "draft_m": 15.2,
        "beam_m": 49.0,
        "loa_m": 366.0,
        "criteria": "Length up to 366m, Beam 32.2–51.2m, Draft ≤ 15.2m",
        "significance": "High capacity; expanded canal constraint rules.",
    },
    {
        "class_id": "ulcv",
        "class_name": "ULCV (Ultra Large)",
        "sector": "containerized",
        "draft_m": 16.0,
        "beam_m": 59.0,
        "loa_m": 400.0,
        "criteria": "Length > 366m, Beam > 51.2m, Draft > 15m",
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
        "criteria": "DWT 80,000–120,000, Draft 12–15m",
        "significance": "Medium-depth crude routes and lightering ops.",
    },
    {
        "class_id": "suezmax",
        "class_name": "Suezmax",
        "sector": "liquidBulk",
        "draft_m": 16.0,
        "beam_m": 50.0,
        "loa_m": 274.0,
        "criteria": "DWT 120,000–200,000, Draft up to 16m",
        "significance": "Constrained by canal draft & deep-water channels.",
    },
    {
        "class_id": "vlcc",
        "class_name": "VLCC / ULCC",
        "sector": "liquidBulk",
        "draft_m": 21.0,
        "beam_m": 60.0,
        "loa_m": 333.0,
        "criteria": "DWT 200,000+, Draft > 20m",
        "significance": "Deep-draft offshore SPM or deep terminal restrictions.",
    },
    # Dry Bulk
    {
        "class_id": "handysize",
        "class_name": "Handysize / Supramax",
        "sector": "dryBulk",
        "draft_m": 10.5,
        "beam_m": 28.0,
        "loa_m": 190.0,
        "criteria": "DWT 10,000–60,000, Draft 9–11m",
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
