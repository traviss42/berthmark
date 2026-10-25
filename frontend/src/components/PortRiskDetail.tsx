import { ArrowLeft, MapPin, Trash2, RefreshCw, Wind, Waves, Eye, Compass, Anchor, Clock } from 'lucide-react';
import type { RiskAssessment } from '@/types';
import { RiskBadge } from './RiskBadge';
import { SubRiskBreakdown } from './SubRiskBreakdown';
import { AlternativePortDiversion } from './AlternativePortDiversion';
import { TIER_COLORS, formatTimestamp } from '@/utils/riskDisplay';

interface Props {
  assessment: RiskAssessment;
  onBack: () => void;
  onRemove?: () => void;
  canRemove: boolean;
  onRefresh: () => void;
  refreshing: boolean;
}

export function PortRiskDetail({ assessment, onBack, onRemove, canRemove, onRefresh, refreshing }: Props) {
  const m = assessment.metrics;
  const compositeColors = TIER_COLORS[assessment.compositeTier];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors"
          >
            <ArrowLeft className="w-4 h-4 text-slate-600" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <MapPin className="w-5 h-5 text-slate-400" />
              <h2 className="text-xl font-bold text-slate-900">{assessment.portName}</h2>
            </div>
            <p className="text-sm text-slate-500 mt-0.5">
              {assessment.vesselClassLabel} · Updated {formatTimestamp(assessment.timestamp)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 text-slate-500 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="text-slate-600">Refresh</span>
          </button>
          {canRemove && onRemove && (
            <button
              onClick={onRemove}
              className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Remove
            </button>
          )}
        </div>
      </div>

      {/* Composite Score Banner */}
      <div className={`rounded-xl border-2 ${compositeColors.border} ${compositeColors.bg} p-5`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
              Composite Risk Status
            </div>
            <div className="flex items-center gap-3">
              <RiskBadge tier={assessment.compositeTier} size="lg" />
              <span className="text-sm text-slate-600">
                Weakest-Link Rule: highest sub-risk determines composite
              </span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-slate-800">{assessment.compositeScore}</div>
            <div className="text-xs text-slate-500">Composite Score</div>
          </div>
        </div>
      </div>

      {/* Inline Alternative Port Diversions (High/Critical risk only) */}
      <AlternativePortDiversion
        compositeTier={assessment.compositeTier}
        alternatives={assessment.alternatives}
      />

      {/* Sub-Risk Breakdown */}
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Sub-Risk Assessment</h3>
        <SubRiskBreakdown subRisks={assessment.subRisks} />
      </div>

      {/* Raw Metrics */}
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Live Metrics</h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Congestion Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Anchor className="w-4 h-4 text-slate-500" /> Congestion
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Anchorage Queue" value={`${m.congestion.anchorageQueueCount} vessels`} />
              <Metric label="Avg Wait Time" value={`${m.congestion.avgWaitingTimeHours}h`} />
              <Metric label="Berth Occupancy" value={`${m.congestion.berthOccupancyPct}%`} />
              <Metric
                label="30d Avg Queue"
                value={
                  m.congestion.rolling30dAvgQueue !== null && m.congestion.rolling30dAvgQueue !== undefined
                    ? `${m.congestion.rolling30dAvgQueue} vessels`
                    : 'N/A — Collecting Baseline'
                }
              />
            </div>
          </div>

          {/* Terminal Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-slate-500" /> Terminal
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Berth Turnaround" value={`${m.terminal.berthTurnaroundHours}h`} />
              <Metric label="Wait Ratio" value={m.terminal.berthToAnchorageWaitRatio.toFixed(2)} />
              <Metric label="Dwell Anomaly" value={`${m.terminal.dwellTimeAnomalyScore}/100`} />
              <Metric label="30d Avg Turnaround" value={`${m.terminal.rolling30dAvgTurnaround}h`} />
            </div>
          </div>

          {/* Weather Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Wind className="w-4 h-4 text-slate-500" /> Weather
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Wind Speed" value={`${m.weather.windSpeedKnots} kn`} icon={<Wind className="w-3 h-3" />} />
              <Metric label="Gusts" value={`${m.weather.gustSpeedKnots} kn`} />
              <Metric label="Wave Height" value={`${m.weather.waveHeightM} m`} icon={<Waves className="w-3 h-3" />} />
              <Metric label="Swell Period" value={`${m.weather.swellPeriodSec} s`} />
              <Metric label="Visibility" value={`${m.weather.visibilityNm} Nm`} icon={<Eye className="w-3 h-3" />} />
            </div>
          </div>

          {/* Navigational Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Compass className="w-4 h-4 text-slate-500" /> Navigational
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Under-Keel Clearance" value={`${m.navigational.underKeelClearanceM} m`} />
              <Metric label="Channel Depth" value={`${m.navigational.channelDepthM} m`} />
              <Metric label="Air Draft Clearance" value={`${m.navigational.airDraftClearanceM} m`} />
              <Metric label="Tide Height" value={`${m.navigational.tideHeightM} m`} />
              <Metric label="Pilotage" value={m.navigational.pilotageAvailable ? 'Available' : 'Unavailable'} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-slate-500 flex items-center gap-1">{icon}{label}</div>
      <div className="text-sm font-semibold text-slate-800 mt-0.5">{value}</div>
    </div>
  );
}

