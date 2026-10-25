"""Terminal turnaround, berth dwell time anomaly, and delay risk calculation service."""

from backend.schemas.metrics import SubRiskResult, TerminalMetrics


def calculate_terminal_metrics(
    berth_turnaround_hours: float,
    rolling_30d_avg_turnaround: float,
    avg_waiting_time_hours: float = 0.0,
) -> TerminalMetrics:
    """Compute terminal turnaround metrics, wait ratio, and dwell anomaly score.

    Args:
        berth_turnaround_hours: Average vessel turnaround time at berth in hours.
        rolling_30d_avg_turnaround: 30-day baseline turnaround time in hours.
        avg_waiting_time_hours: Average anchorage queue waiting time in hours.

    Returns:
        TerminalMetrics schema object.
    """
    turnaround = max(0.0, round(float(berth_turnaround_hours), 1))
    baseline = max(0.0, round(float(rolling_30d_avg_turnaround), 1))
    wait_time = max(0.0, float(avg_waiting_time_hours))

    # Calculate berth-to-anchorage wait ratio
    if wait_time == 0.0 or turnaround == 0.0:
        ratio = 0.0
    else:
        ratio = round(turnaround / wait_time, 2)

    # Calculate turnaround variance percentage
    if baseline == 0.0:
        variance_pct = 0.0 if turnaround == 0.0 else 100.0
    else:
        variance_pct = round(((turnaround - baseline) / baseline) * 100.0, 2)

    # Calculate dwell time anomaly score: 25.0 + variance_pct clamped to [0.0, 100.0]
    raw_score = 25.0 + variance_pct
    anomaly_score = min(100.0, max(0.0, round(raw_score, 1)))

    return TerminalMetrics(
        berthTurnaroundHours=turnaround,
        berthToAnchorageWaitRatio=ratio,
        dwellTimeAnomalyScore=anomaly_score,
        rolling30dAvgTurnaround=baseline,
    )


def evaluate_terminal_delays(metrics: TerminalMetrics) -> SubRiskResult:
    """Evaluate terminal turnaround and dwell anomaly into OpenAPI SubRiskResult.

    Threshold Rules:
        - HIGH: dwellTimeAnomalyScore > 75.0 OR berthTurnaroundHours > 48.0 (Score: 90.0)
        - MEDIUM: (40.0 <= dwellTimeAnomalyScore <= 75.0 OR 24.0 < berthTurnaroundHours <= 48.0) and not HIGH (Score: 60.0)
        - LOW: dwellTimeAnomalyScore < 40.0 AND berthTurnaroundHours <= 24.0 (Score: 25.0)
    """
    turnaround = metrics.berthTurnaroundHours
    baseline = metrics.rolling30dAvgTurnaround
    score_val = metrics.dwellTimeAnomalyScore
    variance_pct = round(((turnaround - baseline) / baseline) * 100.0, 1) if baseline > 0 else 0.0

    factors: list[str] = [
        f"Berth turnaround: {turnaround:.1f}h vs {baseline:.1f}h 30-day baseline ({variance_pct:+.1f}%)",
        f"Dwell anomaly score: {score_val:.1f} (0-100 scale)",
        f"Berth-to-anchorage wait ratio: {metrics.berthToAnchorageWaitRatio:.2f}",
    ]

    # HIGH condition
    if score_val > 75.0 or turnaround > 48.0:
        tier = "high"
        score = 90.0
        if score_val > 75.0 and turnaround > 48.0:
            detail = f"Severe terminal delays: berth turnaround {turnaround:.1f}h exceeds 48.0h threshold with critical dwell anomaly score {score_val:.1f}."
            factors.append(f"Turnaround time {turnaround:.1f}h exceeds critical ceiling (>48.0h).")
            factors.append(f"Dwell anomaly score {score_val:.1f} exceeds high risk threshold (>75.0).")
        elif turnaround > 48.0:
            detail = f"Severe terminal delays: berth turnaround {turnaround:.1f}h exceeds 48.0h operational capacity threshold."
            factors.append(f"Turnaround time {turnaround:.1f}h exceeds critical ceiling (>48.0h).")
        else:
            detail = f"Critical dwell time anomaly: score {score_val:.1f} indicates severe cargo handling bottlenecks."
            factors.append(f"Dwell anomaly score {score_val:.1f} exceeds high risk threshold (>75.0).")

    # MEDIUM condition
    elif (40.0 <= score_val <= 75.0) or (24.0 < turnaround <= 48.0):
        tier = "medium"
        score = 60.0
        detail = f"Moderate terminal delays: berth turnaround {turnaround:.1f}h ({variance_pct:+.1f}% vs {baseline:.1f}h baseline), dwell anomaly score {score_val:.1f}."
        if 24.0 < turnaround <= 48.0:
            factors.append(f"Berth turnaround {turnaround:.1f}h in elevated range (24.0h - 48.0h).")
        if 40.0 <= score_val <= 75.0:
            factors.append(f"Dwell anomaly score {score_val:.1f} in moderate tolerance window (40.0 - 75.0).")

    # LOW condition
    else:
        tier = "low"
        score = 25.0
        detail = f"Normal terminal turnaround: {turnaround:.1f}h ({variance_pct:+.1f}% vs {baseline:.1f}h baseline), dwell anomaly score {score_val:.1f}."
        factors.append(f"Berth turnaround {turnaround:.1f}h within normal bounds (<=24.0h).")
        factors.append(f"Dwell anomaly score {score_val:.1f} within normal range (<40.0).")

    return SubRiskResult(
        category="terminalDelays",
        tier=tier,
        score=score,
        detail=detail,
        factors=factors,
    )
