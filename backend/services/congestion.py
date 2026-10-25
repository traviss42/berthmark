"""Port traffic congestion risk evaluation and anomaly assessment engine."""

from dataclasses import dataclass
from typing import Any


def calculate_queue_variance(anchored_count: int, hist_avg_anchored: float) -> float:
    """Calculate percentage variance between current queue and historical baseline.

    Formula:
        ΔQ_pct = ((N_anchored - N_hist_avg) / N_hist_avg) * 100%

    Edge Cases:
        - N_hist_avg == 0.0 and N_anchored == 0 -> 0.0%
        - N_hist_avg == 0.0 and N_anchored > 0 -> +100.0%
    """
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
    queue_variance_pct: float
    tier: str  # "low", "medium", "high"
    score: float  # 25.0, 60.0, 90.0
    detail: str
    factors: list[str]
    is_cold_start: bool

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
        hist_avg = self.hist_avg_anchored if self.hist_avg_anchored is not None else 0.0

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
            else round(max(2.0, hist_avg * 1.4), 1)
        )

        return {
            "anchorageQueueCount": q_count,
            "avgWaitingTimeHours": wait_hours,
            "berthOccupancyPct": occupancy,
            "rolling30dAvgQueue": round(hist_avg, 1),
            "rolling30dAvgWaitHours": avg_wait,
        }


def assess_congestion_risk(
    anchored_count: int | None,
    hist_avg_anchored: float | None = None,
    underway_count: int = 0,
) -> CongestionAssessment:
    """Evaluate port congestion risk based on current anchored queue and historical baseline.

    Risk Tiers:
        - HIGH: N_anchored > 15 OR ΔQ_pct > +75.0%
        - MEDIUM: (6 <= N_anchored <= 15 OR +30.0% <= ΔQ_pct <= +75.0%) AND not HIGH
        - LOW: 0 <= N_anchored <= 5 AND ΔQ_pct < +30.0%

    Scores:
        - LOW: 25.0
        - MEDIUM: 60.0
        - HIGH: 90.0
    """
    # 1. Uninitialized live count
    if anchored_count is None:
        return CongestionAssessment(
            anchored_count=None,
            underway_count=underway_count,
            hist_avg_anchored=hist_avg_anchored,
            queue_variance_pct=0.0,
            tier="low",
            score=25.0,
            detail="Initializing live traffic (collecting AIS pings)...",
            factors=["Live anchorage queue initializing; defaulting to safe tier."],
            is_cold_start=False,
        )

    # 2. Cold-start handling (missing historical baseline)
    if hist_avg_anchored is None:
        if anchored_count > 15:
            tier = "high"
            score = 90.0
            detail = f"High congestion: {anchored_count} vessels anchored (cold-start baseline mode)."
            factors = [f"Anchored vessel count {anchored_count} exceeds high threshold (>15).", "Historical baseline unavailable (cold-start)."]
        elif anchored_count >= 6:
            tier = "medium"
            score = 60.0
            detail = f"Moderate congestion: {anchored_count} vessels anchored (cold-start baseline mode)."
            factors = [f"Anchored vessel count {anchored_count} in moderate range (6-15).", "Historical baseline unavailable (cold-start)."]
        else:
            tier = "low"
            score = 25.0
            detail = f"Normal congestion: {anchored_count} vessels anchored (cold-start baseline mode)."
            factors = [f"Anchored vessel count {anchored_count} in normal range (0-5).", "Historical baseline unavailable (cold-start)."]

        return CongestionAssessment(
            anchored_count=anchored_count,
            underway_count=underway_count,
            hist_avg_anchored=None,
            queue_variance_pct=0.0,
            tier=tier,
            score=score,
            detail=detail,
            factors=factors,
            is_cold_start=True,
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

    return CongestionAssessment(
        anchored_count=anchored_count,
        underway_count=underway_count,
        hist_avg_anchored=hist_avg_anchored,
        queue_variance_pct=variance_pct,
        tier=tier,
        score=score,
        detail=detail,
        factors=factors,
        is_cold_start=False,
    )
