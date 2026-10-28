"""Port traffic congestion risk evaluation and anomaly assessment engine."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PortRiskSnapshot, PortTrafficBaseline, utc_now


def calculate_queue_variance(anchored_count: int, hist_avg_anchored: float | None) -> float | None:
    """Calculate percentage variance between current queue and historical baseline.

    Formula:
        ΔQ_pct = ((N_anchored - N_hist_avg) / N_hist_avg) * 100%

    Edge Cases:
        - hist_avg_anchored is None -> None (no baseline data)
        - N_hist_avg == 0.0 and N_anchored == 0 -> 0.0%
        - N_hist_avg == 0.0 and N_anchored > 0 -> +100.0%
    """
    if hist_avg_anchored is None:
        return None

    if hist_avg_anchored == 0.0:
        if anchored_count == 0:
            return 0.0
        return 100.0

    diff = float(anchored_count) - float(hist_avg_anchored)
    variance_pct = (diff / float(hist_avg_anchored)) * 100.0
    return round(variance_pct, 2)


@dataclass(frozen=True, slots=True)
class CongestionAssessment:
    """Immutable evaluation result for port traffic congestion and queue anomaly."""

    anchored_count: int | None
    underway_count: int
    hist_avg_anchored: float | None
    queue_variance_pct: float | None
    tier: str  # "low", "medium", "high"
    score: float  # 25.0, 60.0, 90.0
    detail: str
    factors: list[str]
    is_cold_start: bool
    is_initializing: bool = False
    baseline_days_collected: int | None = None

    def to_subrisk_result(self) -> dict[str, Any]:
        """Convert assessment into OpenAPI SubRiskResult schema object."""
        return {
            "category": "congestion",
            "tier": self.tier,
            "score": self.score,
            "detail": self.detail,
            "factors": list(self.factors),
        }

    def to_congestion_metrics(
        self,
        avg_waiting_time_hours: float | None = None,
        berth_occupancy_pct: float | None = None,
        rolling_30d_avg_wait_hours: float | None = None,
    ) -> dict[str, Any]:
        """Convert assessment into OpenAPI CongestionMetrics schema object."""
        q_count = self.anchored_count if self.anchored_count is not None else 0

        # Heuristic operational defaults if not explicitly measured
        wait_hours = (
            avg_waiting_time_hours
            if avg_waiting_time_hours is not None
            else round(max(2.0, q_count * 1.5), 1)
        )
        occupancy = (
            berth_occupancy_pct
            if berth_occupancy_pct is not None
            else min(95.0, round(50.0 + q_count * 2.5, 1))
        )
        avg_wait = (
            rolling_30d_avg_wait_hours
            if rolling_30d_avg_wait_hours is not None
            else (round(max(2.0, self.hist_avg_anchored * 1.4), 1) if self.hist_avg_anchored is not None else None)
        )

        return {
            "anchorageQueueCount": q_count,
            "avgWaitingTimeHours": wait_hours,
            "berthOccupancyPct": occupancy,
            "rolling30dAvgQueue": round(self.hist_avg_anchored, 1) if self.hist_avg_anchored is not None else None,
            "rolling30dAvgWaitHours": avg_wait,
            "isColdStart": self.is_cold_start,
            "isInitializing": self.is_initializing,
            "underwayCount": self.underway_count,
            "baselineDaysCollected": self.baseline_days_collected,
        }


def assess_congestion_risk(
    anchored_count: int | None,
    hist_avg_anchored: float | None = None,
    underway_count: int = 0,
    is_initializing: bool | None = None,
    baseline_days_collected: int | None = None,
) -> CongestionAssessment:
    """Evaluate port congestion risk based on current anchored queue and historical baseline.

    When historical baseline is unavailable (port_traffic_baselines has no recorded data for slot):
        - queue_variance_pct is set to None.
        - Evaluates risk solely using live anchored count thresholds:
            * 0 to 5 anchored vessels: LOW (25.0)
            * 6 to 15 anchored vessels: MEDIUM (60.0)
            * > 15 anchored vessels: HIGH (90.0)

    When historical baseline is available:
        - HIGH: N_anchored > 15 OR ΔQ_pct > +75.0%
        - MEDIUM: (6 <= N_anchored <= 15 OR +30.0% <= ΔQ_pct <= +75.0%) AND not HIGH
        - LOW: 0 <= N_anchored <= 5 AND ΔQ_pct < +30.0%
    """
    is_init = is_initializing if is_initializing is not None else (anchored_count is None)

    # 1. Uninitialized live count (prior to live AIS ping aggregation completion)
    if is_init or anchored_count is None:
        return CongestionAssessment(
            anchored_count=anchored_count,
            underway_count=underway_count,
            hist_avg_anchored=hist_avg_anchored,
            queue_variance_pct=None,
            tier="low",
            score=25.0,
            detail="Initializing live traffic (collecting AIS pings)...",
            factors=["Live anchorage queue initializing; defaulting to safe tier."],
            is_cold_start=hist_avg_anchored is None or (baseline_days_collected is not None and baseline_days_collected < 30),
            is_initializing=True,
            baseline_days_collected=baseline_days_collected,
        )

    # 2. Cold-start handling (missing historical baseline)
    if hist_avg_anchored is None:
        if anchored_count > 15:
            tier = "high"
            score = 90.0
            detail = f"High congestion: {anchored_count} vessels anchored (baseline collecting)."
            factors = [
                f"Anchored vessel count {anchored_count} exceeds high threshold (>15).",
                "Historical baseline unavailable (collecting real data).",
            ]
        elif anchored_count >= 6:
            tier = "medium"
            score = 60.0
            detail = f"Moderate congestion: {anchored_count} vessels anchored (baseline collecting)."
            factors = [
                f"Anchored vessel count {anchored_count} in moderate range (6-15).",
                "Historical baseline unavailable (collecting real data).",
            ]
        else:
            tier = "low"
            score = 25.0
            detail = f"Normal congestion: {anchored_count} vessels anchored (baseline collecting)."
            factors = [
                f"Anchored vessel count {anchored_count} in normal range (0-5).",
                "Historical baseline unavailable (collecting real data).",
            ]

        return CongestionAssessment(
            anchored_count=anchored_count,
            underway_count=underway_count,
            hist_avg_anchored=None,
            queue_variance_pct=None,
            tier=tier,
            score=score,
            detail=detail,
            factors=factors,
            is_cold_start=True,
            is_initializing=False,
            baseline_days_collected=baseline_days_collected or 0,
        )

    # 3. Standard assessment with historical baseline
    variance_pct = calculate_queue_variance(anchored_count, hist_avg_anchored)
    factors: list[str] = [
        f"Anchorage queue: {anchored_count} vs {hist_avg_anchored:.1f} baseline ({variance_pct:+.1f}% variance)",
    ]

    # Evaluate HIGH condition first: N > 15 OR ΔQ > +75.0%
    if anchored_count > 15 or variance_pct > 75.0:
        tier = "high"
        score = 90.0
        if anchored_count > 15 and variance_pct > 75.0:
            detail = f"Severe congestion anomaly: {anchored_count} vessels anchored ({variance_pct:+.1f}% vs baseline {hist_avg_anchored:.1f})."
            factors.append(f"Queue count {anchored_count} exceeds high threshold (>15).")
            factors.append(f"Queue variance {variance_pct:+.1f}% exceeds critical anomaly threshold (>+75.0%).")
        elif anchored_count > 15:
            detail = f"High congestion: {anchored_count} vessels anchored in queue exceeding capacity threshold."
            factors.append(f"Queue count {anchored_count} exceeds high threshold (>15).")
        else:
            detail = f"Severe queue surge: {anchored_count} vessels anchored ({variance_pct:+.1f}% surge vs baseline {hist_avg_anchored:.1f})."
            factors.append(f"Queue variance {variance_pct:+.1f}% exceeds critical anomaly threshold (>+75.0%).")

    # Evaluate MEDIUM condition: (6 <= N <= 15 OR +30.0% <= ΔQ <= +75.0%)
    elif (6 <= anchored_count <= 15) or (30.0 <= variance_pct <= 75.0):
        tier = "medium"
        score = 60.0
        detail = f"Moderate congestion: {anchored_count} vessels anchored ({variance_pct:+.1f}% vs baseline {hist_avg_anchored:.1f})."
        if 6 <= anchored_count <= 15:
            factors.append(f"Anchored vessel count {anchored_count} in moderate range (6-15).")
        if 30.0 <= variance_pct <= 75.0:
            factors.append(f"Queue variance {variance_pct:+.1f}% above standard operating tolerance (+30.0% to +75.0%).")

    # LOW condition: 0 <= N <= 5 AND ΔQ < +30.0%
    else:
        tier = "low"
        score = 25.0
        detail = f"Normal congestion: {anchored_count} vessels anchored ({variance_pct:+.1f}% vs baseline {hist_avg_anchored:.1f})."
        factors.append(f"Anchored queue count {anchored_count} within normal bounds (0-5).")
        factors.append(f"Queue variance {variance_pct:+.1f}% within baseline limits (<+30.0%).")

    is_mature = baseline_days_collected is not None and baseline_days_collected >= 30
    return CongestionAssessment(
        anchored_count=anchored_count,
        underway_count=underway_count,
        hist_avg_anchored=hist_avg_anchored,
        queue_variance_pct=variance_pct,
        tier=tier,
        score=score,
        detail=detail,
        factors=factors,
        is_cold_start=not is_mature if baseline_days_collected is not None else False,
        is_initializing=False,
        baseline_days_collected=baseline_days_collected,
    )


# ─── Database Access & Real Baseline Rolling Average Updates ──────────────────

async def get_rolling_congestion_baseline(
    session: AsyncSession,
    unlocode: str,
    timestamp: datetime | None = None,
    max_days: int = 30,
) -> tuple[float | None, int | None]:
    """Retrieve or compute historical traffic moving average up to 30 days.

    Queries PortRiskSnapshot over the rolling 30-day window to dynamically refine
    the empirical queue baseline as days go on. If empirical snapshots exist, calculates the
    average queue count and number of distinct observation days collected.

    If no snapshot history exists yet, checks PortTrafficBaseline for the slot (pre-seeded).
    Returns (None, 0) if no baseline data exists at all.
    """
    clean_locode = unlocode.strip().upper()
    now_dt = timestamp if timestamp is not None else utc_now()
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    cutoff = now_dt - timedelta(days=max_days)

    stmt = (
        select(PortRiskSnapshot.anchored_vessel_count, PortRiskSnapshot.updated_at)
        .where(
            PortRiskSnapshot.unlocode == clean_locode,
            PortRiskSnapshot.updated_at >= cutoff,
        )
    )
    res = await session.execute(stmt)
    rows = res.all()

    if rows:
        counts = [r[0] for r in rows if r[0] is not None]
        dates = {r[1].date() if hasattr(r[1], "date") else r[1] for r in rows if r[1] is not None}
        avg_queue = sum(counts) / len(counts) if counts else 0.0
        days_collected = min(max_days, max(1, len(dates)))
        return round(float(avg_queue), 1), days_collected

    # Fallback to slot baseline if available
    slot_baseline = await get_port_traffic_baseline(session, clean_locode, now_dt)
    if slot_baseline:
        return round(float(slot_baseline.avg_anchored_count), 1), 30

    # Fallback to any existing baseline for this port
    stmt_any = (
        select(PortTrafficBaseline)
        .where(PortTrafficBaseline.unlocode == clean_locode)
        .order_by(PortTrafficBaseline.updated_at.desc())
        .limit(1)
    )
    any_baseline = (await session.execute(stmt_any)).scalar_one_or_none()
    if any_baseline:
        return round(float(any_baseline.avg_anchored_count), 1), 30

    return None, 0


async def get_port_traffic_baseline(
    session: AsyncSession,
    unlocode: str,
    timestamp: datetime | None = None,
) -> PortTrafficBaseline | None:
    """Retrieve historical traffic baseline for a port matching the timestamp's (day_of_week, hour_of_day) slot.

    Returns None if no real baseline observations have been recorded for this slot.
    """
    dt = timestamp if timestamp is not None else utc_now()
    day_of_week = (dt.weekday() + 1) % 7
    hour_of_day = dt.hour

    stmt = select(PortTrafficBaseline).where(
        PortTrafficBaseline.unlocode == unlocode.strip().upper(),
        PortTrafficBaseline.day_of_week == day_of_week,
        PortTrafficBaseline.hour_of_day == hour_of_day,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_baseline_slot(
    session: AsyncSession,
    unlocode: str,
    day_of_week: int,
    hour_of_day: int,
) -> PortTrafficBaseline | None:
    """Retrieve baseline record by explicit (day_of_week, hour_of_day)."""
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


async def update_port_traffic_baseline_from_observation(
    session: AsyncSession,
    unlocode: str,
    anchored_count: int,
    underway_count: int,
    total_count: int,
    timestamp: datetime | None = None,
    alpha: float = 0.1,
) -> PortTrafficBaseline:
    """Update rolling baseline average from real AIS observations without synthetic data.

    If no record exists for this (day_of_week, hour_of_day) slot, initializes the record
    using the observed real vessel counts. Otherwise, applies exponential moving average
    smoothing with parameter alpha.
    """
    dt = timestamp if timestamp is not None else utc_now()
    day_of_week = (dt.weekday() + 1) % 7
    hour_of_day = dt.hour
    clean_locode = unlocode.strip().upper()

    existing = await get_baseline_slot(session, clean_locode, day_of_week, hour_of_day)
    if existing:
        existing.avg_anchored_count = round(
            (1.0 - alpha) * existing.avg_anchored_count + alpha * float(anchored_count), 2
        )
        existing.avg_underway_count = round(
            (1.0 - alpha) * existing.avg_underway_count + alpha * float(underway_count), 2
        )
        existing.avg_total_active = round(
            (1.0 - alpha) * existing.avg_total_active + alpha * float(total_count), 2
        )
        existing.updated_at = utc_now()
        record = existing
    else:
        record = PortTrafficBaseline(
            baseline_id=uuid.uuid4(),
            unlocode=clean_locode,
            day_of_week=day_of_week,
            hour_of_day=hour_of_day,
            avg_anchored_count=round(float(anchored_count), 2),
            avg_underway_count=round(float(underway_count), 2),
            avg_total_active=round(float(total_count), 2),
            updated_at=utc_now(),
        )
        session.add(record)

    await session.commit()
    return record
