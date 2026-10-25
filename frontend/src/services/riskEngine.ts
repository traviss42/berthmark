import type {
  PortMetrics,
  RiskTier,
  SubRiskCategory,
  SubRiskResult,
  VesselClass,
  RiskAssessment,
} from '@/types';
import { VESSEL_CLASS_THRESHOLDS, getVesselClassInfo } from '@/data/vesselTaxonomy';

const TIER_SCORES: Record<RiskTier, number> = {
  low: 25,
  medium: 60,
  high: 90,
};

function tierToScore(tier: RiskTier): number {
  return TIER_SCORES[tier];
}

// ── Congestion: compare current metrics against rolling 30-day baselines ──
function assessCongestion(metrics: PortMetrics): SubRiskResult {
  const c = metrics.congestion;
  const factors: string[] = [];

  // Fallback if historical baseline is absent
  if (c.rolling30dAvgQueue === null || c.rolling30dAvgQueue === undefined) {
    let tier: RiskTier = 'low';
    let detail = `Normal congestion: ${c.anchorageQueueCount} vessels anchored (baseline collecting).`;

    if (c.anchorageQueueCount > 15) {
      tier = 'high';
      detail = `Severe congestion: ${c.anchorageQueueCount} vessels anchored.`;
      factors.push(`Anchored vessel count ${c.anchorageQueueCount} exceeds high threshold (>15)`);
    } else if (c.anchorageQueueCount >= 6) {
      tier = 'medium';
      detail = `Moderate congestion: ${c.anchorageQueueCount} vessels anchored.`;
      factors.push(`Anchored vessel count ${c.anchorageQueueCount} in moderate range (6-15)`);
    } else {
      factors.push(`Anchored vessel count ${c.anchorageQueueCount} in normal range (0-5)`);
    }
    factors.push('Historical baseline unavailable (collecting real data)');
    return { category: 'congestion', tier, score: tierToScore(tier), detail, factors };
  }

  const queueRatio = c.rolling30dAvgQueue > 0
    ? c.anchorageQueueCount / c.rolling30dAvgQueue
    : 1;
  const waitRatio = (c.rolling30dAvgWaitHours && c.rolling30dAvgWaitHours > 0)
    ? c.avgWaitingTimeHours / c.rolling30dAvgWaitHours
    : 1;

  let tier: RiskTier = 'low';
  let detail = 'Normal congestion levels relative to 30-day baseline.';

  if (queueRatio >= 1.5 || waitRatio >= 1.5 || c.berthOccupancyPct >= 90) {
    tier = 'high';
    detail = 'Severe congestion: queue or waiting times significantly above 30-day average.';
  } else if (queueRatio >= 1.2 || waitRatio >= 1.2 || c.berthOccupancyPct >= 75) {
    tier = 'medium';
    detail = 'Elevated congestion above rolling baseline.';
  }

  if (queueRatio >= 1.2) factors.push(`Anchorage queue ${c.anchorageQueueCount} vs ${c.rolling30dAvgQueue} avg (ratio ${queueRatio.toFixed(2)})`);
  if (waitRatio >= 1.2 && c.rolling30dAvgWaitHours) factors.push(`Avg wait ${c.avgWaitingTimeHours}h vs ${c.rolling30dAvgWaitHours}h avg (ratio ${waitRatio.toFixed(2)})`);
  if (c.berthOccupancyPct >= 75) factors.push(`Berth occupancy at ${c.berthOccupancyPct}%`);

  return { category: 'congestion', tier, score: tierToScore(tier), detail, factors };
}

// ── Terminal Delays: berth turnaround, wait ratios, dwell anomalies ──
function assessTerminalDelays(metrics: PortMetrics): SubRiskResult {
  const t = metrics.terminal;
  const factors: string[] = [];

  const turnaroundRatio = t.rolling30dAvgTurnaround > 0
    ? t.berthTurnaroundHours / t.rolling30dAvgTurnaround
    : 1;

  let tier: RiskTier = 'low';
  let detail = 'Terminal operations within normal turnaround range.';

  if (turnaroundRatio >= 1.5 || t.berthToAnchorageWaitRatio >= 0.7 || t.dwellTimeAnomalyScore >= 70) {
    tier = 'high';
    detail = 'Significant terminal delays: turnaround or dwell anomalies detected.';
  } else if (turnaroundRatio >= 1.2 || t.berthToAnchorageWaitRatio >= 0.5 || t.dwellTimeAnomalyScore >= 40) {
    tier = 'medium';
    detail = 'Terminal delays above baseline trends.';
  }

  if (turnaroundRatio >= 1.2) factors.push(`Turnaround ${t.berthTurnaroundHours}h vs ${t.rolling30dAvgTurnaround}h avg (ratio ${turnaroundRatio.toFixed(2)})`);
  if (t.berthToAnchorageWaitRatio >= 0.5) factors.push(`Berth-to-anchorage wait ratio ${t.berthToAnchorageWaitRatio}`);
  if (t.dwellTimeAnomalyScore >= 40) factors.push(`Dwell anomaly score ${t.dwellTimeAnomalyScore}/100`);

  return { category: 'terminalDelays', tier, score: tierToScore(tier), detail, factors };
}

// ── Weather: PIANC-based hard limits, adjusted per vessel class ──
function assessWeather(metrics: PortMetrics, vesselClass: VesselClass): SubRiskResult {
  const w = metrics.weather;
  const th = VESSEL_CLASS_THRESHOLDS[vesselClass];
  const factors: string[] = [];

  let tier: RiskTier = 'low';
  let detail = 'Weather conditions within safe operating limits.';

  // Wind is the primary factor — gusts count too
  const effectiveWind = Math.max(w.windSpeedKnots, w.gustSpeedKnots * 0.85);

  if (
    effectiveWind >= th.windHighKnots ||
    w.waveHeightM >= 4.0 ||
    w.visibilityNm <= 0.5
  ) {
    tier = 'high';
    detail = 'Severe weather exceeding PIANC safety limits for this vessel class.';
  } else if (
    effectiveWind >= th.windMediumKnots ||
    w.waveHeightM >= 2.5 ||
    w.visibilityNm <= 2.0
  ) {
    tier = 'medium';
    detail = 'Adverse weather approaching operational thresholds.';
  }

  if (effectiveWind >= th.windMediumKnots) factors.push(`Wind ${w.windSpeedKnots}kn, gusts ${w.gustSpeedKnots}kn (limit ${th.windHighKnots}kn)`);
  if (w.waveHeightM >= 2.5) factors.push(`Wave height ${w.waveHeightM}m`);
  if (w.visibilityNm <= 2.0) factors.push(`Visibility ${w.visibilityNm}Nm`);

  return { category: 'weather', tier, score: tierToScore(tier), detail, factors };
}

// ── Navigational: UKC, air draft, pilotage — PIANC safety floors ──
function assessNavigational(metrics: PortMetrics, vesselClass: VesselClass): SubRiskResult {
  const n = metrics.navigational;
  const th = VESSEL_CLASS_THRESHOLDS[vesselClass];
  const factors: string[] = [];

  let tier: RiskTier = 'low';
  let detail = 'Navigational conditions within safe clearance limits.';

  if (
    n.underKeelClearanceM <= th.ukcHighM ||
    n.airDraftClearanceM <= th.airDraftClearanceLowM ||
    !n.pilotageAvailable
  ) {
    tier = 'high';
    detail = 'Critical navigational constraint: insufficient clearance or pilotage unavailable.';
  } else if (
    n.underKeelClearanceM <= th.ukcMediumM ||
    n.airDraftClearanceM <= th.airDraftClearanceMediumM
  ) {
    tier = 'medium';
    detail = 'Navigational clearances approaching minimum safety margins.';
  }

  if (n.underKeelClearanceM <= th.ukcMediumM) factors.push(`UKC ${n.underKeelClearanceM}m (minimum ${th.ukcHighM}m)`);
  if (n.airDraftClearanceM <= th.airDraftClearanceMediumM) factors.push(`Air draft clearance ${n.airDraftClearanceM}m`);
  if (!n.pilotageAvailable) factors.push('Pilotage currently unavailable');

  return { category: 'navigational', tier, score: tierToScore(tier), detail, factors };
}

// ── Composite: "Weakest-Link" rule — any High sub-risk means composite High ──
export function computeCompositeTier(
  subRisks: Record<SubRiskCategory, SubRiskResult>
): { tier: RiskTier; score: number } {
  const tiers = Object.values(subRisks).map((r) => r.tier);

  if (tiers.includes('high')) {
    return { tier: 'high', score: 90 };
  }
  if (tiers.includes('medium')) {
    return { tier: 'medium', score: 60 };
  }
  return { tier: 'low', score: 25 };
}

export function assessRisk(
  portId: string,
  portName: string,
  vesselClass: VesselClass,
  metrics: PortMetrics
): RiskAssessment {
  const classInfo = getVesselClassInfo(vesselClass);

  const subRisks: Record<SubRiskCategory, SubRiskResult> = {
    congestion: assessCongestion(metrics),
    terminalDelays: assessTerminalDelays(metrics),
    weather: assessWeather(metrics, vesselClass),
    navigational: assessNavigational(metrics, vesselClass),
  };

  const composite = computeCompositeTier(subRisks);

  return {
    id: `risk-${portId}-${vesselClass}-${metrics.timestamp}`,
    portId,
    portName,
    vesselClass,
    vesselClassLabel: classInfo.label,
    timestamp: metrics.timestamp,
    compositeTier: composite.tier,
    compositeScore: composite.score,
    subRisks,
    metrics,
  };
}
