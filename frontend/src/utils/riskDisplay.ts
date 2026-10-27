import type { RiskTier, SubRiskCategory } from '@/types';

export const TIER_LABELS: Record<RiskTier, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
};

export const TIER_COLORS: Record<RiskTier, { bg: string; text: string; border: string; dot: string; ring: string }> = {
  low: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    dot: 'bg-emerald-500',
    ring: 'ring-emerald-200',
  },
  medium: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    dot: 'bg-amber-500',
    ring: 'ring-amber-200',
  },
  high: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    dot: 'bg-red-500',
    ring: 'ring-red-200',
  },
};

export const CATEGORY_LABELS: Record<SubRiskCategory, string> = {
  congestion: 'Congestion',
  weather: 'Weather',
  navigational: 'Navigational',
};

export const CATEGORY_ICONS: Record<SubRiskCategory, string> = {
  congestion: 'Anchor',
  weather: 'CloudRain',
  navigational: 'Compass',
};

export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export const VESSEL_CLASS_LABELS: Record<string, string> = {
  feeder: 'Feeder',
  panamax: 'Panamax',
  neoPanamax: 'Neo-Panamax',
  ulcv: 'ULCV',
  mrTanker: 'MR Tanker',
  aframax: 'Aframax',
  suezmax: 'Suezmax',
  vlcc: 'VLCC',
  handysize: 'Handysize',
  panamaxBulk: 'Panamax Bulk',
  capesize: 'Capesize',
  pctc: 'PCTC',
  lng: 'LNG',
};

export function formatVesselClass(vesselClass: string): string {
  if (VESSEL_CLASS_LABELS[vesselClass]) {
    return VESSEL_CLASS_LABELS[vesselClass];
  }
  return vesselClass
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (c) => c.toUpperCase());
}

export function formatQueueVariance(
  anchored: number,
  baselineAvg: number | null | undefined,
  daysCollected?: number | null
): { text: string; value: number | null } {
  if (baselineAvg === null || baselineAvg === undefined || isNaN(baselineAvg)) {
    return { text: 'N/A — Collecting Baseline', value: null };
  }

  let baselineLabel = '7-day Avg';
  if (daysCollected !== undefined && daysCollected !== null) {
    if (daysCollected >= 30) {
      baselineLabel = '30-day Avg';
    } else if (daysCollected === 1) {
      baselineLabel = '1-day Avg';
    } else {
      baselineLabel = `${daysCollected}-day Avg`;
    }
  }

  if (baselineAvg === 0) {
    if (anchored === 0) {
      return { text: `0% vs ${baselineLabel}`, value: 0 };
    }
    return { text: `+100% vs ${baselineLabel}`, value: 100 };
  }
  const variance = ((anchored - baselineAvg) / baselineAvg) * 100;
  const rounded = Math.round(variance);
  const sign = rounded > 0 ? '+' : '';
  return {
    text: `${sign}${rounded}% vs ${baselineLabel}`,
    value: rounded,
  };
}

