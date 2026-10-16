import { Anchor, CloudRain, Compass } from 'lucide-react';
import type { SubRiskCategory, SubRiskResult } from '@/types';
import { RiskBadge } from './RiskBadge';
import { CATEGORY_LABELS } from '@/utils/riskDisplay';

const ICONS: Record<SubRiskCategory, typeof Anchor> = {
  congestion: Anchor,
  weather: CloudRain,
  navigational: Compass,
};

interface Props {
  subRisks: Record<SubRiskCategory, SubRiskResult>;
}

export function SubRiskBreakdown({ subRisks }: Props) {
  const categories = Object.keys(subRisks) as SubRiskCategory[];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {categories.map((cat) => {
        const result = subRisks[cat];
        const Icon = ICONS[cat] || Compass;
        return (
          <div
            key={cat}
            className="rounded-lg border border-slate-200 p-4 bg-white"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Icon className="w-4 h-4 text-slate-500" />
                <span className="text-sm font-medium text-slate-700">
                  {CATEGORY_LABELS[cat]}
                </span>
              </div>
              <RiskBadge tier={result.tier} size="sm" />
            </div>
            <p className="text-xs text-slate-500 mb-2">{result.detail}</p>
            {result.factors.length > 0 && (
              <ul className="space-y-1">
                {result.factors.map((f, i) => (
                  <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-slate-400 mt-1.5 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
