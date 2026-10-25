import type { RiskTier } from '@/types';
import { TIER_COLORS, TIER_LABELS } from '@/utils/riskDisplay';

interface Props {
  tier: RiskTier;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export function RiskBadge({ tier, size = 'md', showLabel = true }: Props) {
  const colors = TIER_COLORS[tier];
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5 gap-1',
    md: 'text-sm px-2.5 py-1 gap-1.5',
    lg: 'text-base px-3 py-1.5 gap-2',
  };
  const dotSizes = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-2.5 h-2.5',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold ${colors.bg} ${colors.text} ${colors.border} ${sizeClasses[size]}`}
    >
      <span className={`rounded-full ${colors.dot} ${dotSizes[size]} animate-pulse`} />
      {showLabel && TIER_LABELS[tier]}
    </span>
  );
}
