import { ArrowLeft, MapPin, Trash2, RefreshCw, Wind, Waves, Eye, Compass, Anchor, Bell, BellOff, Mail } from 'lucide-react';
import type { RiskAssessment } from '@/types';
import { RiskBadge } from './RiskBadge';
import { SubRiskBreakdown } from './SubRiskBreakdown';
import { TIER_COLORS, formatTimestamp } from '@/utils/riskDisplay';
import { isDemoAccount } from '@/utils/demoAccount';

interface Props {
  assessment: RiskAssessment;
  onBack: () => void;
  onRemove?: () => void;
  canRemove: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  notificationsEnabled?: boolean;
  onToggleNotifications?: (enabled: boolean) => void;
  userEmail?: string;
}

export function PortRiskDetail({
  assessment,
  onBack,
  onRemove,
  canRemove,
  onRefresh,
  refreshing,
  notificationsEnabled = true,
  onToggleNotifications,
  userEmail,
}: Props) {
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

      {/* Email Notifications Settings Card */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center justify-between gap-4 flex-wrap shadow-sm">
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
            notificationsEnabled ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-400'
          }`}>
            {notificationsEnabled ? <Bell className="w-5 h-5" /> : <BellOff className="w-5 h-5" />}
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <span>Email Risk Alerts</span>
              {notificationsEnabled ? (
                <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  Active
                </span>
              ) : (
                <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                  Opted Out
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
              <Mail className="w-3 h-3 text-slate-400" />
              {notificationsEnabled
                ? isDemoAccount(userEmail)
                  ? `In-app alerts active (Demo account: outbound emails turned off)`
                  : `Alerts dispatched to: ${userEmail || 'login email'}`
                : 'Email alerts are disabled for this port.'}
            </p>
          </div>
        </div>

        {onToggleNotifications && (
          <button
            type="button"
            onClick={() => onToggleNotifications(!notificationsEnabled)}
            className={`text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              notificationsEnabled
                ? 'border-slate-300 text-slate-700 bg-white hover:bg-slate-50'
                : 'border-blue-600 text-white bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {notificationsEnabled ? 'Opt Out of Alerts' : 'Opt In to Alerts'}
          </button>
        )}
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

      {/* Sub-Risk Breakdown */}
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Sub-Risk Assessment</h3>
        <SubRiskBreakdown subRisks={assessment.subRisks} />
      </div>

      {/* Raw Metrics */}
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Live & Hydrographic Metrics</h3>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Congestion Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Anchor className="w-4 h-4 text-slate-500" /> Vessel Traffic (AISStream)
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Anchored / Stationary" value={`${m.congestion.anchorageQueueCount} vessels`} />
              <Metric label="Active in Geofence" value={`${m.congestion.activeVesselCount} vessels`} />
              <Metric label="Underway Vessels" value={`${m.congestion.movingVesselCount} vessels`} />
              <Metric label="Historical Avg Queue" value={`${m.congestion.rolling30dAvgQueue} vessels`} />
            </div>
          </div>

          {/* Weather Metrics */}
          <div className="rounded-lg border border-slate-200 p-4 bg-white">
            <h4 className="text-sm font-medium text-slate-700 mb-3 flex items-center gap-2">
              <Wind className="w-4 h-4 text-slate-500" /> Marine Weather (Open-Meteo)
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
              <Compass className="w-4 h-4 text-slate-500" /> Navigational & Depth (NGA WPI)
            </h4>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Metric label="Under-Keel Clearance" value={`${m.navigational.underKeelClearanceM} m`} />
              <Metric label="Channel Depth" value={`${m.navigational.channelDepthM} m`} />
              {m.navigational.cargoPierDepthM != null && (
                <Metric label="Cargo Pier Depth" value={`${m.navigational.cargoPierDepthM} m`} />
              )}
              <Metric label="Vessel Design Draft" value={`${m.navigational.vesselDraftM} m`} />
              <Metric label="Overhead Limits" value={m.navigational.overheadLimits} />
              <Metric label="Tidal Range" value={`${m.navigational.tideHeightM} m`} />
              <Metric label="Pilotage" value={m.navigational.pilotageAvailable ? 'Available' : 'Unavailable'} />
              <Metric label="Tug Assistance" value={m.navigational.tugsAssistance ? 'Available' : 'Unavailable'} />
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

