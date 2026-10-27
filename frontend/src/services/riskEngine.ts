import type {
  PortMetrics,
  RiskTier,
  SubRiskCategory,
  SubRiskResult,
  VesselClass,
  RiskAssessment,
  AlternativePortRecommendation,
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

const MOCK_ALTERNATIVES_BY_PORT: Record<string, AlternativePortRecommendation[]> = {
  'port-rotterdam': [
    {
      portId: 'port-wilhelmshaven',
      unlocode: 'DEWVN',
      portName: 'Port of Wilhelmshaven',
      country: 'Germany',
      distanceNm: 140.0,
      channelDepthM: 20.0,
      depthMarginM: 3.3,
      swellHeightM: 1.0,
      riskTier: 'low',
      trafficStatus: '3 anchored / 2 underway',
    },
    {
      portId: 'port-europoort',
      unlocode: 'NLEUR',
      portName: 'Europoort',
      country: 'Netherlands',
      distanceNm: 13.5,
      channelDepthM: 20.1,
      depthMarginM: 3.4,
      swellHeightM: 0.9,
      riskTier: 'low',
      trafficStatus: '5 anchored / 4 underway',
    },
  ],
  'port-singapore': [
    {
      portId: 'port-tanjungbalai',
      unlocode: 'IDTJB',
      portName: 'Tanjungbalai',
      country: 'Indonesia',
      distanceNm: 29.2,
      channelDepthM: 21.6,
      depthMarginM: 4.9,
      swellHeightM: 0.8,
      riskTier: 'low',
      trafficStatus: '2 anchored / 1 underway',
    },
    {
      portId: 'port-sungai-udang',
      unlocode: 'MYSUP',
      portName: 'Sungai Udang Port',
      country: 'Malaysia',
      distanceNm: 118.3,
      channelDepthM: 17.1,
      depthMarginM: 0.4,
      swellHeightM: 0.9,
      riskTier: 'low',
      trafficStatus: '1 anchored / 1 underway',
    },
  ],
  'port-houston': [
    {
      portId: 'port-corpus-christi',
      unlocode: 'USCRP',
      portName: 'Port of Corpus Christi',
      country: 'United States',
      distanceNm: 150.0,
      channelDepthM: 16.5,
      depthMarginM: 1.3,
      swellHeightM: 1.0,
      riskTier: 'low',
      trafficStatus: '4 anchored / 2 underway',
    },
    {
      portId: 'port-loop-terminal',
      unlocode: 'USLO9',
      portName: 'Loop Terminal',
      country: 'United States',
      distanceNm: 280.4,
      channelDepthM: 23.2,
      depthMarginM: 6.5,
      swellHeightM: 1.2,
      riskTier: 'low',
      trafficStatus: '3 anchored / 1 underway',
    },
  ],
  'port-losangeles': [
    {
      portId: 'port-longbeach',
      unlocode: 'USLGB',
      portName: 'Port of Long Beach',
      country: 'United States',
      distanceNm: 17.3,
      channelDepthM: 23.2,
      depthMarginM: 6.5,
      swellHeightM: 0.9,
      riskTier: 'low',
      trafficStatus: '4 anchored / 3 underway',
    },
  ],
  'port-antwerp': [
    {
      portId: 'port-europoort',
      unlocode: 'NLEUR',
      portName: 'Europoort',
      country: 'Netherlands',
      distanceNm: 45.1,
      channelDepthM: 20.1,
      depthMarginM: 3.4,
      swellHeightM: 0.9,
      riskTier: 'low',
      trafficStatus: '4 anchored / 2 underway',
    },
    {
      portId: 'port-dunkerque',
      unlocode: 'FRDKK',
      portName: 'Dunkerque',
      country: 'France',
      distanceNm: 76.8,
      channelDepthM: 20.1,
      depthMarginM: 3.4,
      swellHeightM: 1.1,
      riskTier: 'low',
      trafficStatus: '3 anchored / 1 underway',
    },
  ],
  'port-shanghai': [
    {
      portId: 'port-zhoushan',
      unlocode: 'CNZOS',
      portName: 'Zhoushan',
      country: 'China',
      distanceNm: 80.7,
      channelDepthM: 21.6,
      depthMarginM: 4.9,
      swellHeightM: 1.0,
      riskTier: 'low',
      trafficStatus: '5 anchored / 3 underway',
    },
  ],
};

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

  const alternatives: AlternativePortRecommendation[] = [];
  if (composite.tier === 'high') {
    const cleanId = portId.toLowerCase().trim();
    const matched = MOCK_ALTERNATIVES_BY_PORT[cleanId];
    if (matched) {
      alternatives.push(...matched);
    } else {
      alternatives.push({
        portId: `port-alt-${cleanId}`,
        unlocode: `${cleanId.slice(0, 3).toUpperCase()}AL`,
        portName: `Regional Safe Harbor (${portName || 'Alternative'})`,
        country: 'Regional Waters',
        distanceNm: 45.0,
        channelDepthM: 18.5,
        depthMarginM: 2.5,
        swellHeightM: 0.9,
        riskTier: 'low',
        trafficStatus: '2 anchored / 1 underway',
      });
    }
  }

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
    alternatives,
  };
}
