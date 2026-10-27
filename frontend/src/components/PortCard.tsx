import React from 'react';
import {
  Anchor,
  Navigation,
  Ship,
  Waves,
  Wind,
  Compass,
  AlertTriangle,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import type { Port, RiskAssessment, VesselClass } from '@/types';
import {
  formatVesselClass,
  formatQueueVariance,
  TIER_COLORS,
  TIER_LABELS,
} from '@/utils/riskDisplay';
import { AlternativePortDiversion } from './AlternativePortDiversion';

export interface PortCardProps {
  port: Port;
  assessment?: RiskAssessment | null;
  vesselClass?: VesselClass;
  onSelect?: (portId: string) => void;
  className?: string;
}

export const PortCard: React.FC<PortCardProps> = ({
  port,
  assessment,
  vesselClass = 'neoPanamax',
  onSelect,
  className = '',
}) => {
  const effectiveVesselClass = assessment?.vesselClass || port.vesselClass || vesselClass;
  const vesselClassLabel = formatVesselClass(effectiveVesselClass);

  // Risk tier & score
  const tier = assessment?.compositeTier ?? 'low';
  const score = assessment?.compositeScore ?? 0;
  const tierColor = TIER_COLORS[tier];
  const tierLabel = TIER_LABELS[tier];

  // Cold start detection
  const isColdStart =
    Boolean((assessment as any)?.isColdStart) ||
    Boolean((assessment as any)?.isInitializing) ||
    Boolean((assessment?.metrics?.congestion as any)?.isColdStart) ||
    Boolean((assessment?.metrics?.congestion as any)?.isInitializing) ||
    !assessment?.metrics?.congestion;

  // Congestion / 4D traffic metrics
  const congestion = assessment?.metrics?.congestion;
  const anchoredCount = congestion?.anchorageQueueCount ?? 0;
  const underwayCount =
    (congestion as any)?.underwayCount ??
    (assessment?.metrics as any)?.underwayCount ??
    0;
  const totalActive =
    (congestion as any)?.totalActiveVessels ?? anchoredCount + underwayCount;
  const baselineAvg =
    (congestion as any)?.hist_avg_anchored ??
    congestion?.rolling30dAvgQueue ??
    null;

  const queueVariance = formatQueueVariance(
    anchoredCount,
    baselineAvg,
    congestion?.baselineDaysCollected
  );

  // Depth & Navigational metrics
  const navigational = assessment?.metrics?.navigational;
  const isDepthAvailable =
    (navigational as any)?.is_depth_available !== false &&
    (navigational as any)?.isDepthAvailable !== false &&
    navigational?.channelDepthM !== null &&
    navigational?.channelDepthM !== undefined;

  const channelDepth = navigational?.channelDepthM;
  const ukcMargin = navigational?.underKeelClearanceM;

  // Weather metrics
  const weather = assessment?.metrics?.weather;
  const swellHeight = weather?.waveHeightM;
  const windSpeed = weather?.windSpeedKnots;

  return (
    <div
      role="article"
      data-testid={`port-card-${port.id}`}
      onClick={() => onSelect && onSelect(port.id)}
      className={`bg-white rounded-xl border border-slate-200 shadow-xs hover:border-blue-400 hover:shadow-md transition-all p-5 flex flex-col justify-between cursor-pointer group ${className}`}
    >
      {/* ── Card Header ── */}
      <div>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold text-slate-900 group-hover:text-blue-600 transition-colors truncate">
                {port.name}
              </h3>
              <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-mono font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                {port.locode}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
              <span>{port.country}</span>
              <span>·</span>
              <span>{port.geofenceRadiusNm} NM Geofence</span>
              {!port.isDefault && (
                <>
                  <span>·</span>
                  <span className="text-emerald-600 font-medium">Private</span>
                </>
              )}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1.5 shrink-0">
            {/* Overall Risk Badge */}
            <div
              data-testid="risk-badge"
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border ${tierColor.bg} ${tierColor.text} ${tierColor.border} shadow-2xs`}
            >
              <span className={`w-2 h-2 rounded-full ${tierColor.dot}`} />
              <span>
                {tierLabel.toUpperCase()} · {Math.round(score)}
              </span>
            </div>

            {/* Vessel Class Badge */}
            <span
              data-testid="vessel-class-badge"
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200"
            >
              {vesselClassLabel}
            </span>
          </div>
        </div>

        {/* ── 4-Dimension Traffic Breakdown Block ── */}
        <div className="mt-4 pt-3 border-t border-slate-100">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Ship className="w-3.5 h-3.5 text-slate-400" />
              Live AIS Traffic
            </span>
            {!isColdStart && (
              <span
                data-testid="queue-variance"
                className={`text-[11px] font-medium flex items-center gap-0.5 ${
                  queueVariance.value && queueVariance.value > 0
                    ? 'text-red-600 font-semibold'
                    : queueVariance.value && queueVariance.value < 0
                    ? 'text-emerald-600'
                    : 'text-slate-500'
                }`}
              >
                {queueVariance.value && queueVariance.value > 0 ? (
                  <TrendingUp className="w-3 h-3" />
                ) : queueVariance.value && queueVariance.value < 0 ? (
                  <TrendingDown className="w-3 h-3" />
                ) : (
                  <Minus className="w-3 h-3" />
                )}
                {queueVariance.text}
              </span>
            )}
          </div>

          {isColdStart ? (
            <div
              data-testid="cold-start-indicator"
              className="py-3 px-3 rounded-lg bg-blue-50 border border-blue-200 text-center animate-pulse"
            >
              <span className="text-xs font-medium text-blue-800">
                Initializing Live Traffic (Collecting AIS Pings)...
              </span>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2 bg-slate-50 rounded-lg p-2.5 border border-slate-200/80">
              <div className="text-center">
                <div className="text-xs text-slate-500 flex items-center justify-center gap-1">
                  <Anchor className="w-3 h-3 text-slate-400" />
                  Anchored
                </div>
                <div
                  data-testid="anchored-count"
                  className="text-base font-bold text-slate-800 mt-0.5"
                >
                  {anchoredCount}
                </div>
                <div className="text-[10px] text-slate-400">SOG ≤ 0.5 kn</div>
              </div>

              <div className="text-center border-x border-slate-200">
                <div className="text-xs text-slate-500 flex items-center justify-center gap-1">
                  <Navigation className="w-3 h-3 text-slate-400" />
                  Underway
                </div>
                <div
                  data-testid="underway-count"
                  className="text-base font-bold text-slate-800 mt-0.5"
                >
                  {underwayCount}
                </div>
                <div className="text-[10px] text-slate-400">SOG &gt; 0.5 kn</div>
              </div>

              <div className="text-center">
                <div className="text-xs text-slate-500 flex items-center justify-center gap-1">
                  <Ship className="w-3 h-3 text-slate-400" />
                  Total Active
                </div>
                <div
                  data-testid="total-count"
                  className="text-base font-bold text-blue-700 mt-0.5"
                >
                  {totalActive}
                </div>
                <div className="text-[10px] text-slate-400">In Geofence</div>
              </div>
            </div>
          )}
        </div>

        {/* ── Depth & Weather Parameters Block ── */}
        <div className="mt-3.5 pt-3 border-t border-slate-100">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2">
            Depth &amp; Weather Parameters
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            {/* Channel Depth */}
            <div className="flex items-center justify-between p-2 rounded-md bg-slate-50 border border-slate-200/60">
              <span className="text-slate-500 flex items-center gap-1">
                <Compass className="w-3.5 h-3.5 text-slate-400" />
                Depth:
              </span>
              {isDepthAvailable && channelDepth !== undefined ? (
                <span data-testid="channel-depth" className="font-semibold text-slate-800">
                  {channelDepth.toFixed(1)}m
                </span>
              ) : (
                <span
                  data-testid="depth-na-badge"
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300"
                >
                  <AlertTriangle className="w-2.5 h-2.5" />
                  Depth N/A
                </span>
              )}
            </div>

            {/* UKC Margin */}
            <div className="flex items-center justify-between p-2 rounded-md bg-slate-50 border border-slate-200/60">
              <span className="text-slate-500">UKC Margin:</span>
              {ukcMargin !== undefined ? (
                <span
                  data-testid="ukc-margin"
                  className={`font-semibold ${
                    ukcMargin < 0 ? 'text-red-600 font-bold' : 'text-emerald-700'
                  }`}
                >
                  {ukcMargin > 0 ? `+${ukcMargin.toFixed(1)}m` : `${ukcMargin.toFixed(1)}m`} UKC
                </span>
              ) : (
                <span className="text-slate-400">N/A</span>
              )}
            </div>

            {/* Swell Height */}
            <div className="flex items-center justify-between p-2 rounded-md bg-slate-50 border border-slate-200/60">
              <span className="text-slate-500 flex items-center gap-1">
                <Waves className="w-3.5 h-3.5 text-slate-400" />
                Swell:
              </span>
              <span data-testid="swell-height" className="font-semibold text-slate-800">
                {swellHeight !== undefined ? `${swellHeight.toFixed(1)}m Swell` : 'N/A'}
              </span>
            </div>

            {/* Wind Speed */}
            <div className="flex items-center justify-between p-2 rounded-md bg-slate-50 border border-slate-200/60">
              <span className="text-slate-500 flex items-center gap-1">
                <Wind className="w-3.5 h-3.5 text-slate-400" />
                Wind:
              </span>
              <span data-testid="wind-speed" className="font-semibold text-slate-800">
                {windSpeed !== undefined ? `${windSpeed.toFixed(1)} kn Wind` : 'N/A'}
              </span>
            </div>
          </div>
        </div>

        {/* ── Inline Alternative Port Diversions (High Risk only) ── */}
        <AlternativePortDiversion
          compositeTier={tier}
          alternatives={assessment?.alternatives}
        />
      </div>

      {/* ── Direct Footer / Link ── */}
      <div
        data-testid="view-telemetry-link"
        onClick={(e) => {
          e.stopPropagation();
          onSelect && onSelect(port.id);
        }}
        className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-blue-600 group-hover:text-blue-700 font-medium cursor-pointer"
      >
        <span>View Operational Telemetry</span>
        <ChevronRight className="w-4 h-4 transform group-hover:translate-x-1 transition-transform" />
      </div>
    </div>
  );
};
