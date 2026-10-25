"""Port traffic baseline repository and weekly 168-hour historical pattern seeder."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Port, PortTrafficBaseline, utc_now
from backend.ports.service import BENCHMARK_PORTS_METADATA

# Standard default benchmark ports for 168-hour baseline seeding
DEFAULT_BASELINE_PORTS: dict[str, dict[str, float]] = {
    "NLRTM": {"anchored_base": 12.0, "underway_base": 8.0},
    "SGSIN": {"anchored_base": 24.0, "underway_base": 18.0},
    "USHOU": {"anchored_base": 16.0, "underway_base": 10.0},
    "BEANR": {"anchored_base": 10.0, "underway_base": 7.0},
    "CNSHA": {"anchored_base": 30.0, "underway_base": 22.0},
}


class TrafficBaselineRepository:
    """Async repository for querying and managing hourly historical port traffic baselines."""

    @staticmethod
    async def get_baseline(
        session: AsyncSession,
        unlocode: str,
        day_of_week: int,
        hour_of_day: int,
    ) -> PortTrafficBaseline | None:
        """Retrieve baseline record for port by (day_of_week, hour_of_day).

        Raises:
            ValueError: If day_of_week not in 0..6 or hour_of_day not in 0..23.
        """
        if not (0 <= day_of_week <= 6):
            raise ValueError(f"day_of_week must be within [0, 6], got {day_of_week}")
        if not (0 <= hour_of_day <= 23):
            raise ValueError(f"hour_of_day must be within [0, 23], got {hour_of_day}")

        stmt = select(PortTrafficBaseline).where(
            PortTrafficBaseline.unlocode == unlocode.strip().upper(),
            PortTrafficBaseline.day_of_week == day_of_week,
            PortTrafficBaseline.hour_of_day == hour_of_day,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_current_baseline(
        session: AsyncSession,
        unlocode: str,
        timestamp: datetime | None = None,
    ) -> PortTrafficBaseline | None:
        """Map UTC timestamp to (day_of_week, hour_of_day) and retrieve matching baseline.

        Note:
            day_of_week: 0 = Sunday, 1 = Monday, ..., 6 = Saturday.
        """
        dt = timestamp if timestamp is not None else utc_now()
        # Convert to 0=Sunday to 6=Saturday
        day_of_week = (dt.weekday() + 1) % 7
        hour_of_day = dt.hour
        return await TrafficBaselineRepository.get_baseline(
            session, unlocode, day_of_week, hour_of_day
        )

    @staticmethod
    async def upsert_baseline(
        session: AsyncSession,
        unlocode: str,
        day_of_week: int,
        hour_of_day: int,
        avg_anchored: float,
        avg_underway: float,
        avg_total: float | None = None,
    ) -> PortTrafficBaseline:
        """Insert or update hourly traffic baseline average values."""
        if not (0 <= day_of_week <= 6):
            raise ValueError(f"day_of_week must be within [0, 6], got {day_of_week}")
        if not (0 <= hour_of_day <= 23):
            raise ValueError(f"hour_of_day must be within [0, 23], got {hour_of_day}")
        if avg_anchored < 0.0 or avg_underway < 0.0:
            raise ValueError("Average vessel counts must be >= 0.0")

        clean_locode = unlocode.strip().upper()
        total = avg_total if avg_total is not None else round(avg_anchored + avg_underway, 2)

        existing = await TrafficBaselineRepository.get_baseline(
            session, clean_locode, day_of_week, hour_of_day
        )

        if existing:
            existing.avg_anchored_count = round(avg_anchored, 2)
            existing.avg_underway_count = round(avg_underway, 2)
            existing.avg_total_active = round(total, 2)
            existing.updated_at = utc_now()
            record = existing
        else:
            record = PortTrafficBaseline(
                baseline_id=uuid.uuid4(),
                unlocode=clean_locode,
                day_of_week=day_of_week,
                hour_of_day=hour_of_day,
                avg_anchored_count=round(avg_anchored, 2),
                avg_underway_count=round(avg_underway, 2),
                avg_total_active=round(total, 2),
                updated_at=utc_now(),
            )
            session.add(record)

        await session.commit()
        return record


async def seed_traffic_baselines(session: AsyncSession) -> int:
    """Populate 168 weekly hourly baseline slots for benchmark ports idempotently.

    Ensures foreign key requirements are satisfied and generates realistic hourly traffic.
    Returns:
        Number of seeded/updated baseline slots.
    """
    total_seeded = 0

    # Ensure all benchmark port entities exist in ports table
    for locode in DEFAULT_BASELINE_PORTS:
        stmt = select(Port).where(Port.unlocode == locode)
        port = (await session.execute(stmt)).scalar_one_or_none()
        if port is None:
            meta = BENCHMARK_PORTS_METADATA.get(locode, {})
            port = Port(
                unlocode=locode,
                port_name=meta.get("name", f"Port of {locode}"),
                country_code=meta.get("country_code", locode[:2]),
                subdivision_code="",
                latitude=meta.get("lat", 0.0),
                longitude=meta.get("lon", 0.0),
                channel_depth_m=12.0,
                is_depth_available=True,
                reconciliation_method="BENCHMARK_DEFAULT",
            )
            session.add(port)
            await session.flush()

    for locode, config in DEFAULT_BASELINE_PORTS.items():
        base_anchored = config["anchored_base"]
        base_underway = config["underway_base"]

        # Check existing records for this port
        stmt = select(PortTrafficBaseline).where(PortTrafficBaseline.unlocode == locode)
        existing_rows = (await session.execute(stmt)).scalars().all()
        existing_map = {(r.day_of_week, r.hour_of_day): r for r in existing_rows}

        for day in range(7):
            # Weekend vs weekday factor
            day_factor = 0.85 if day in (0, 6) else 1.05

            for hour in range(24):
                # Diurnal traffic variation (peak activity midday 10:00-16:00, trough overnight 01:00-05:00)
                if 10 <= hour <= 16:
                    hour_factor = 1.20
                elif 1 <= hour <= 5:
                    hour_factor = 0.75
                else:
                    hour_factor = 1.00

                anchored = round(base_anchored * day_factor * (2.0 - hour_factor), 1)
                underway = round(base_underway * day_factor * hour_factor, 1)
                total = round(anchored + underway, 1)

                key = (day, hour)
                if key in existing_map:
                    rec = existing_map[key]
                    rec.avg_anchored_count = anchored
                    rec.avg_underway_count = underway
                    rec.avg_total_active = total
                    rec.updated_at = utc_now()
                else:
                    rec = PortTrafficBaseline(
                        baseline_id=uuid.uuid4(),
                        unlocode=locode,
                        day_of_week=day,
                        hour_of_day=hour,
                        avg_anchored_count=anchored,
                        avg_underway_count=underway,
                        avg_total_active=total,
                        updated_at=utc_now(),
                    )
                    session.add(rec)
                total_seeded += 1

    await session.commit()
    return total_seeded
