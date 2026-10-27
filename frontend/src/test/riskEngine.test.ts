import { describe, it, expect } from 'vitest';
import { assessRisk, computeCompositeTier } from '@/services/riskEngine';
import { formatQueueVariance } from '@/utils/riskDisplay';
import { generateMockMetrics } from '@/data/mockData';
import type { PortMetrics, SubRiskResult, SubRiskCategory, RiskTier } from '@/types';

function makeSubRisk(tier: RiskTier): SubRiskResult {
  return {
    category: 'congestion',
    tier,
    score: tier === 'high' ? 90 : tier === 'medium' ? 60 : 25,
    detail: 'test',
    factors: [],
  };
}

describe('Risk Engine - Composite Tier (Weakest-Link Rule)', () => {
  it('returns high when any sub-risk is high', () => {
    const subRisks = {
      congestion: makeSubRisk('low'),
      weather: makeSubRisk('high'),
      navigational: makeSubRisk('low'),
    };
    const result = computeCompositeTier(subRisks);
    expect(result.tier).toBe('high');
  });

  it('returns high even if only one of three is high', () => {
    const subRisks = {
      congestion: makeSubRisk('low'),
      weather: makeSubRisk('low'),
      navigational: makeSubRisk('high'),
    };
    expect(computeCompositeTier(subRisks).tier).toBe('high');
  });

  it('returns medium when highest sub-risk is medium', () => {
    const subRisks = {
      congestion: makeSubRisk('low'),
      weather: makeSubRisk('medium'),
      navigational: makeSubRisk('low'),
    };
    expect(computeCompositeTier(subRisks).tier).toBe('medium');
  });

  it('returns low when all sub-risks are low', () => {
    const subRisks = {
      congestion: makeSubRisk('low'),
      weather: makeSubRisk('low'),
      navigational: makeSubRisk('low'),
    };
    expect(computeCompositeTier(subRisks).tier).toBe('low');
  });

  it('prioritizes high over medium', () => {
    const subRisks = {
      congestion: makeSubRisk('medium'),
      weather: makeSubRisk('high'),
      navigational: makeSubRisk('low'),
    };
    expect(computeCompositeTier(subRisks).tier).toBe('high');
  });
});

describe('Risk Engine - assessRisk', () => {
  it('produces a complete risk assessment with all sub-risks', () => {
    const metrics = generateMockMetrics('port-test', 'panamax');
    const assessment = assessRisk('port-test', 'Test Port', 'panamax', metrics);

    expect(assessment.portId).toBe('port-test');
    expect(assessment.portName).toBe('Test Port');
    expect(assessment.vesselClass).toBe('panamax');
    expect(assessment.compositeTier).toMatch(/^(low|medium|high)$/);
    expect(assessment.subRisks.congestion).toBeDefined();
    expect(assessment.subRisks.weather).toBeDefined();
    expect(assessment.subRisks.navigational).toBeDefined();
  });

  it('composite tier matches weakest-link of sub-risks', () => {
    const metrics = generateMockMetrics('port-test2', 'feeder');
    const assessment = assessRisk('port-test2', 'Test Port 2', 'feeder', metrics);

    const subTiers: RiskTier[] = Object.values(assessment.subRisks).map((r) => r.tier);
    const hasHigh = subTiers.includes('high');
    const hasMedium = subTiers.includes('medium');

    if (hasHigh) expect(assessment.compositeTier).toBe('high');
    else if (hasMedium) expect(assessment.compositeTier).toBe('medium');
    else expect(assessment.compositeTier).toBe('low');
  });

  it('is deterministic for the same port + vessel class', () => {
    const m1 = generateMockMetrics('port-deterministic', 'suezmax');
    const m2 = generateMockMetrics('port-deterministic', 'suezmax');
    const a1 = assessRisk('port-deterministic', 'D Port', 'suezmax', m1);
    const a2 = assessRisk('port-deterministic', 'D Port', 'suezmax', m2);
    expect(a1.compositeTier).toBe(a2.compositeTier);
    expect(a1.subRisks.congestion.tier).toBe(a2.subRisks.congestion.tier);
  });
});

describe('Risk Engine - Weather assessment by vessel class', () => {
  function makeWeatherMetrics(windKnots: number): PortMetrics {
    const base = generateMockMetrics('weather-test', 'feeder');
    return {
      ...base,
      weather: {
        ...base.weather,
        windSpeedKnots: windKnots,
        gustSpeedKnots: windKnots * 1.1,
        waveHeightM: 1.0,
        visibilityNm: 8,
      },
    };
  }

  it('PCTC flags high wind at lower threshold than feeder', () => {
    const wind25 = makeWeatherMetrics(25);

    const pctcAssessment = assessRisk('weather-test', 'Weather Test', 'pctc', wind25);
    const feederAssessment = assessRisk('weather-test', 'Weather Test', 'feeder', wind25);

    // PCTC windHigh is 25 — should be high or medium
    expect(pctcAssessment.subRisks.weather.tier).not.toBe('low');
    // Feeder windHigh is 45 — 25kn should be low
    expect(feederAssessment.subRisks.weather.tier).toBe('low');
  });
});

describe('Queue Variance Baseline Refinement (formatQueueVariance)', () => {
  it('returns N/A when baseline average is null or undefined', () => {
    expect(formatQueueVariance(10, null).text).toBe('N/A — Collecting Baseline');
    expect(formatQueueVariance(10, undefined).text).toBe('N/A — Collecting Baseline');
    expect(formatQueueVariance(10, null).value).toBeNull();
  });

  it('formats backward compatible vs 7-day Avg when daysCollected is omitted', () => {
    const res = formatQueueVariance(15, 12);
    expect(res.text).toBe('+25% vs 7-day Avg');
    expect(res.value).toBe(25);
  });

  it('formats day-specific baseline label when daysCollected < 30', () => {
    // 1-day empirical baseline
    expect(formatQueueVariance(15, 12, 1).text).toBe('+25% vs 1-day Avg');

    // 5-day empirical baseline
    expect(formatQueueVariance(15, 12, 5).text).toBe('+25% vs 5-day Avg');

    // 14-day empirical baseline
    expect(formatQueueVariance(9, 12, 14).text).toBe('-25% vs 14-day Avg');
  });

  it('formats 30-day Avg once 30+ days of observations have accumulated', () => {
    expect(formatQueueVariance(15, 12, 30).text).toBe('+25% vs 30-day Avg');
    expect(formatQueueVariance(15, 12, 45).text).toBe('+25% vs 30-day Avg');
  });

  it('handles zero baseline edge cases', () => {
    expect(formatQueueVariance(0, 0, 30).text).toBe('0% vs 30-day Avg');
    expect(formatQueueVariance(5, 0, 30).text).toBe('+100% vs 30-day Avg');
  });
});
