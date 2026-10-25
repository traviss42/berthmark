"""Unit tests for Terminal Metrics and Terminal Delays evaluation."""

import pytest
from backend.services.terminal import (
    calculate_terminal_metrics,
    evaluate_terminal_delays,
)


def test_terminal_metrics_standard_calculation():
    """Verify standard terminal metrics matching OpenAPI specification example."""
    # 26.4h turnaround vs 22.0h baseline with 18.5h wait time
    metrics = calculate_terminal_metrics(
        berth_turnaround_hours=26.4,
        rolling_30d_avg_turnaround=22.0,
        avg_waiting_time_hours=18.5,
    )

    assert metrics.berthTurnaroundHours == 26.4
    assert metrics.rolling30dAvgTurnaround == 22.0
    # ratio = 26.4 / 18.5 ≈ 1.43
    assert metrics.berthToAnchorageWaitRatio == 1.43
    # variance = (26.4 - 22.0) / 22.0 = +20.0% -> score = 25.0 + 20.0 = 45.0
    assert metrics.dwellTimeAnomalyScore == 45.0


def test_terminal_metrics_variance_and_score_clamping():
    """Verify dwell time anomaly score clamping between [0.0, 100.0]."""
    # Baseline match: variance = 0.0% -> score = 25.0
    m_equal = calculate_terminal_metrics(20.0, 20.0, 10.0)
    assert m_equal.dwellTimeAnomalyScore == 25.0

    # High variance (+80%) -> score = min(100.0, 25.0 + 80.0) = 100.0
    m_high = calculate_terminal_metrics(36.0, 20.0, 10.0)
    assert m_high.dwellTimeAnomalyScore == 100.0

    # Negative variance (-50%) -> score = max(0.0, 25.0 - 50.0) = 0.0
    m_low = calculate_terminal_metrics(10.0, 20.0, 10.0)
    assert m_low.dwellTimeAnomalyScore == 0.0


def test_terminal_metrics_division_by_zero():
    """Verify zero-division handling for wait ratio and turnaround baseline."""
    # Zero wait time -> ratio returns 0.0
    m_zero_wait = calculate_terminal_metrics(24.0, 20.0, avg_waiting_time_hours=0.0)
    assert m_zero_wait.berthToAnchorageWaitRatio == 0.0

    # Zero turnaround -> ratio returns 0.0
    m_zero_turn = calculate_terminal_metrics(0.0, 20.0, avg_waiting_time_hours=10.0)
    assert m_zero_turn.berthToAnchorageWaitRatio == 0.0

    # Zero baseline with zero turnaround -> variance 0.0% -> score 25.0
    m_zero_base = calculate_terminal_metrics(0.0, 0.0, 0.0)
    assert m_zero_base.dwellTimeAnomalyScore == 25.0

    # Zero baseline with positive turnaround -> capped at +100.0% -> score 100.0
    m_zero_base_pos = calculate_terminal_metrics(15.0, 0.0, 0.0)
    assert m_zero_base_pos.dwellTimeAnomalyScore == 100.0


def test_terminal_delay_threshold_boundaries():
    """Verify exact tier boundaries for score (39.9/40.0, 75.0/75.1) and turnaround (24.0/24.1, 48.0/48.1)."""
    # Score 39.9 with turnaround 20.0h -> LOW
    m1 = calculate_terminal_metrics(20.0, 20.0 / 1.149, 10.0)
    # Explicitly test via TerminalMetrics with target score
    from backend.schemas.metrics import TerminalMetrics

    low_score = TerminalMetrics(
        berthTurnaroundHours=20.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=39.9,
        rolling30dAvgTurnaround=20.0,
    )
    assert evaluate_terminal_delays(low_score).tier == "low"
    assert evaluate_terminal_delays(low_score).score == 25.0

    med_score = TerminalMetrics(
        berthTurnaroundHours=20.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=40.0,
        rolling30dAvgTurnaround=20.0,
    )
    assert evaluate_terminal_delays(med_score).tier == "medium"
    assert evaluate_terminal_delays(med_score).score == 60.0

    med_score_high = TerminalMetrics(
        berthTurnaroundHours=20.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=75.0,
        rolling30dAvgTurnaround=20.0,
    )
    assert evaluate_terminal_delays(med_score_high).tier == "medium"

    high_score = TerminalMetrics(
        berthTurnaroundHours=20.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=75.1,
        rolling30dAvgTurnaround=20.0,
    )
    assert evaluate_terminal_delays(high_score).tier == "high"
    assert evaluate_terminal_delays(high_score).score == 90.0

    # Turnaround 24.0h vs 24.1h
    low_turn = TerminalMetrics(
        berthTurnaroundHours=24.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=30.0,
        rolling30dAvgTurnaround=24.0,
    )
    assert evaluate_terminal_delays(low_turn).tier == "low"

    med_turn = TerminalMetrics(
        berthTurnaroundHours=24.1,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=30.0,
        rolling30dAvgTurnaround=24.0,
    )
    assert evaluate_terminal_delays(med_turn).tier == "medium"

    # Turnaround 48.0h vs 48.1h
    med_turn_high = TerminalMetrics(
        berthTurnaroundHours=48.0,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=50.0,
        rolling30dAvgTurnaround=45.0,
    )
    assert evaluate_terminal_delays(med_turn_high).tier == "medium"

    high_turn = TerminalMetrics(
        berthTurnaroundHours=48.1,
        berthToAnchorageWaitRatio=1.0,
        dwellTimeAnomalyScore=50.0,
        rolling30dAvgTurnaround=45.0,
    )
    assert evaluate_terminal_delays(high_turn).tier == "high"
