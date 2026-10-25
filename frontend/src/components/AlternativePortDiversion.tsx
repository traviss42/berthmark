import React from 'react';
import {
  Compass,
  AlertCircle,
  Anchor,
  Waves,
  Navigation,
} from 'lucide-react';
import type { AlternativePortRecommendation, RiskTier } from '@/types';

export interface AlternativePortDiversionProps {
  compositeTier: RiskTier;
  alternatives?: AlternativePortRecommendation[] | null;
  className?: string;
  onSelectAlternative?: (portId: string) => void;
}

export const AlternativePortDiversion: React.FC<AlternativePortDiversionProps> = ({
  compositeTier,
  alternatives,
  className = '',
  onSelectAlternative,
}) => {
  // Trigger condition: strictly rendered when compositeTier is 'high'
  if (compositeTier !== 'high') {
    return null;
  }

  // Filter out any candidates with high risk and sort by distance ascending
  const viableCandidates = (alternatives || [])
    .filter((alt) => alt.riskTier !== 'high')
    .sort((a, b) => a.distanceNm - b.distanceNm)
    .slice(0, 3);

  return (
    <div
      data-testid="alternative-port-diversion"
      className={`mt-3.5 pt-3 border-t border-red-200/80 bg-red-50/50 rounded-lg p-3 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center gap-1.5 mb-2.5 text-xs font-bold text-red-900 uppercase tracking-wide">
        <Compass className="w-4 h-4 text-red-600 shrink-0" />
        <span>Alternative Port Recommendations</span>
      </div>

      {viableCandidates.length === 0 ? (
        // Empty advisory state
        <div
          role="alert"
          data-testid="no-alternatives-alert"
          className="p-2.5 rounded-md bg-amber-50 border border-amber-200 flex items-start gap-2 text-xs text-amber-800"
        >
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <span className="font-medium leading-relaxed">
            No viable alternative ports found in region meeting vessel draft requirements
          </span>
        </div>
      ) : (
        // Inline candidate list capped at top 3
        <div className="space-y-2">
          {viableCandidates.map((candidate) => {
            const isMarginPositive = candidate.depthMarginM >= 0;
            const marginPrefix = isMarginPositive ? '+' : '';
            const isLowRisk = candidate.riskTier === 'low';

            return (
              <div
                key={candidate.portId}
                data-testid={`alternative-candidate-${candidate.portId}`}
                onClick={(e) => {
                  if (onSelectAlternative) {
                    e.stopPropagation();
                    onSelectAlternative(candidate.portId);
                  }
                }}
                className={`p-2.5 rounded-lg border bg-white shadow-2xs transition-all ${
                  onSelectAlternative
                    ? 'hover:border-blue-400 hover:shadow-xs cursor-pointer'
                    : 'border-slate-200'
                }`}
              >
                {/* Top row: Name/Locode, Proximity distance, Risk Badge */}
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="min-w-0 flex-1">
                    <span className="text-xs font-bold text-slate-900 block truncate">
                      {candidate.portName} ({candidate.unlocode})
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {candidate.country}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <span
                      data-testid="candidate-distance"
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200"
                    >
                      <Navigation className="w-3 h-3 text-slate-500" />
                      {candidate.distanceNm.toFixed(1)} NM
                    </span>

                    <span
                      data-testid="candidate-risk-badge"
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                        isLowRisk
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}
                    >
                      {candidate.riskTier.toUpperCase()} RISK
                    </span>
                  </div>
                </div>

                {/* Details row: Channel depth, margin, swell height */}
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600 pt-1 border-t border-slate-100">
                  <span data-testid="candidate-depth-margin">
                    <span className="text-slate-500">Depth / Margin: </span>
                    <span className="font-medium text-slate-800">
                      {candidate.channelDepthM.toFixed(1)}m Depth
                    </span>
                    <span className="text-slate-400"> / </span>
                    <span
                      className={`font-semibold ${
                        isMarginPositive
                          ? 'text-emerald-700'
                          : 'text-red-600 font-bold'
                      }`}
                    >
                      {marginPrefix}
                      {candidate.depthMarginM.toFixed(1)}m Margin
                    </span>
                  </span>

                  <span
                    data-testid="candidate-swell"
                    className="inline-flex items-center gap-1"
                  >
                    <Waves className="w-3 h-3 text-slate-400" />
                    <span>{candidate.swellHeightM.toFixed(1)}m Swell</span>
                  </span>

                  {candidate.trafficStatus && (
                    <span
                      data-testid="candidate-traffic"
                      className="inline-flex items-center gap-1 text-slate-500"
                    >
                      <Anchor className="w-3 h-3 text-slate-400" />
                      <span>{candidate.trafficStatus}</span>
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
