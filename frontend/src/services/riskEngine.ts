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

// ── Congestion: compare current live vessel queue against rolling baseline ──
function assessCongestion(metrics: PortMetrics): SubRiskResult {
  const c = metrics.congestion;
  const factors: string[] = [];

  const queueRatio = c.rolling30dAvgQueue > 0
    ? c.anchorageQueueCount / c.rolling30dAvgQueue
    : 1;

  let tier: RiskTier = 'low';
  let detail = 'Normal vessel traffic relative to rolling historical baseline.';

  if (queueRatio >= 1.5 || c.anchorageQueueCount >= 25) {
    tier = 'high';
    detail = 'Severe anchorage congestion: stationary/anchored vessel queue significantly above baseline.';
  } else if (queueRatio >= 1.2 || c.anchorageQueueCount >= 12) {
    tier = 'medium';
    detail = 'Elevated vessel queue above rolling baseline.';
  }

  if (queueRatio >= 1.2) {
    factors.push(`Anchored/stationary queue ${c.anchorageQueueCount} vs ${c.rolling30dAvgQueue} avg (ratio ${queueRatio.toFixed(2)})`);
  }
  if (c.anchorageQueueCount >= 12) {
    factors.push(`${c.anchorageQueueCount} stationary/anchored vessels in port geofence`);
  }
  if (c.activeVesselCount > 0) {
    factors.push(`${c.activeVesselCount} total active vessels (${c.movingVesselCount} underway)`);
  }

  return { category: 'congestion', tier, score: tierToScore(tier), detail, factors };
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

// ── Navigational: NGA WPI UKC, overhead limits, pilotage & tugs ──
function assessNavigational(metrics: PortMetrics, vesselClass: VesselClass): SubRiskResult {
  const n = metrics.navigational;
  const th = VESSEL_CLASS_THRESHOLDS[vesselClass];
  const factors: string[] = [];

  let tier: RiskTier = 'low';
  let detail = 'Navigational and NGA WPI depth clearances within safe operating limits.';

  const highAirDraftClass = ['ulcv', 'neoPanamax', 'pctc', 'lng', 'vlcc'].includes(vesselClass);
  const hasOverheadConstraint = n.overheadLimits === 'Yes' && highAirDraftClass;

  if (
    n.underKeelClearanceM <= th.ukcHighM ||
    !n.pilotageAvailable
  ) {
    tier = 'high';
    detail = 'Critical navigational constraint: insufficient under-keel clearance or pilotage unavailable.';
  } else if (
    n.underKeelClearanceM <= th.ukcMediumM ||
    hasOverheadConstraint ||
    !n.tugsAssistance
  ) {
    tier = 'medium';
    detail = 'Navigational clearances or port infrastructure approaching safety margins.';
  }

  if (n.underKeelClearanceM <= th.ukcMediumM) {
    factors.push(`UKC ${n.underKeelClearanceM}m (Channel ${n.channelDepthM}m vs Draft ${n.vesselDraftM}m, min margin ${th.ukcHighM}m)`);
  }
  if (hasOverheadConstraint) {
    factors.push('Overhead bridge/cable limits reported in NGA World Port Index');
  }
  if (!n.pilotageAvailable) {
    factors.push('Pilotage unavailable in NGA World Port Index');
  }
  if (!n.tugsAssistance) {
    factors.push('Tug assistance unavailable in NGA World Port Index');
  }

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

