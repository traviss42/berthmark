import type { Port, VesselClass } from '@/types';

export const DEFAULT_PORTS: Port[] = [
  {
    id: 'port-rotterdam',
    name: 'Port of Rotterdam',
    locode: 'NLRTM',
    country: 'Netherlands',
    lat: 51.9244,
    lon: 4.4777,
    isDefault: true,
    geofenceRadiusNm: 8,
    addedByUserId: null,
  },
  {
    id: 'port-singapore',
    name: 'Port of Singapore',
    locode: 'SGSIN',
    country: 'Singapore',
    lat: 1.2648,
    lon: 103.8408,
    isDefault: true,
    geofenceRadiusNm: 10,
    addedByUserId: null,
  },
  {
    id: 'port-shanghai',
    name: 'Port of Shanghai',
    locode: 'CNSHA',
    country: 'China',
    lat: 31.2304,
    lon: 121.4737,
    isDefault: true,
    geofenceRadiusNm: 10,
    addedByUserId: null,
  },
  {
    id: 'port-hamburg',
    name: 'Port of Hamburg',
    locode: 'DEHAM',
    country: 'Germany',
    lat: 53.5399,
    lon: 9.9472,
    isDefault: true,
    geofenceRadiusNm: 7,
    addedByUserId: null,
  },
  {
    id: 'port-losangeles',
    name: 'Port of Los Angeles',
    locode: 'USLAX',
    country: 'United States',
    lat: 33.7291,
    lon: -118.2639,
    isDefault: true,
    geofenceRadiusNm: 8,
    addedByUserId: null,
  },
  {
    id: 'port-jebelali',
    name: 'Jebel Ali Port',
    locode: 'AEJEA',
    country: 'UAE',
    lat: 25.0125,
    lon: 55.0717,
    isDefault: true,
    geofenceRadiusNm: 8,
    addedByUserId: null,
  },
];

// Seedable RNG so mock data is deterministic per port+class
function hashSeed(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function generateMockMetrics(portId: string, vesselClass: VesselClass) {
  const rng = mulberry32(hashSeed(`${portId}-${vesselClass}`));

  // Rolling 30-day baselines (per vessel class per port)
  const rolling30dAvgQueue = Math.round(3 + rng() * 15);
  const rolling30dAvgWaitHours = Math.round((2 + rng() * 20) * 10) / 10;
  const rolling30dAvgTurnaround = Math.round((12 + rng() * 36) * 10) / 10;

  // Current metrics — sometimes above baseline (anomaly), sometimes normal
  const anomalyFactor = 0.6 + rng() * 1.2; // 0.6–1.8
  const anchorageQueueCount = Math.round(rolling30dAvgQueue * anomalyFactor);
  const avgWaitingTimeHours = Math.round(rolling30dAvgWaitHours * anomalyFactor * 10) / 10;
  const berthOccupancyPct = Math.round((40 + rng() * 55) * 10) / 10;

  const berthTurnaroundHours = Math.round(rolling30dAvgTurnaround * anomalyFactor * 10) / 10;
  const berthToAnchorageWaitRatio = Math.round((0.2 + rng() * 0.8) * 100) / 100;
  const dwellTimeAnomalyScore = Math.round(rng() * 100);

  // Weather — occasionally severe
  const weatherSeverity = rng();
  const windSpeedKnots = Math.round((5 + weatherSeverity * 45) * 10) / 10;
  const gustSpeedKnots = Math.round((windSpeedKnots * (1.2 + rng() * 0.3)) * 10) / 10;
  const waveHeightM = Math.round((0.5 + weatherSeverity * 5) * 10) / 10;
  const swellPeriodSec = Math.round(4 + rng() * 12);
  const visibilityNm = Math.round((1 + rng() * 9) * 10) / 10;

  // Navigational
  const channelDepthM = Math.round((12 + rng() * 18) * 10) / 10;
  const underKeelClearanceM = Math.round((0.5 + rng() * 5) * 10) / 10;
  const airDraftClearanceM = Math.round((1 + rng() * 15) * 10) / 10;
  const tideHeightM = Math.round((0.5 + rng() * 3.5) * 10) / 10;
  const pilotageAvailable = rng() > 0.15;

  return {
    portId,
    timestamp: new Date().toISOString(),
    congestion: {
      anchorageQueueCount,
      avgWaitingTimeHours,
      berthOccupancyPct,
      rolling30dAvgQueue,
      rolling30dAvgWaitHours,
    },
    terminal: {
      berthTurnaroundHours,
      berthToAnchorageWaitRatio,
      dwellTimeAnomalyScore,
      rolling30dAvgTurnaround,
    },
    weather: {
      windSpeedKnots,
      waveHeightM,
      swellPeriodSec,
      visibilityNm,
      gustSpeedKnots,
    },
    navigational: {
      underKeelClearanceM,
      channelDepthM,
      airDraftClearanceM,
      pilotageAvailable,
      tideHeightM,
    },
  };
}
