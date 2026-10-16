import { MapPin, ChevronRight, Globe, Trash2, Bell, BellOff } from 'lucide-react';
import type { Port, RiskAssessment } from '@/types';
import { RiskBadge } from './RiskBadge';

interface Props {
  ports: Port[];
  assessments: Map<string, RiskAssessment>;
  onSelectPort: (portId: string) => void;
  onRemovePort?: (portId: string) => void;
  onToggleNotifications?: (portId: string, enabled: boolean) => void;
  userEmail?: string;
  loading: boolean;
}

export function PortList({
  ports,
  assessments,
  onSelectPort,
  onRemovePort,
  onToggleNotifications,
  userEmail,
  loading,
}: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-slate-200 p-4 bg-white animate-pulse">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-slate-100" />
                <div className="space-y-2">
                  <div className="h-4 w-40 rounded bg-slate-100" />
                  <div className="h-3 w-24 rounded bg-slate-100" />
                </div>
              </div>
              <div className="h-6 w-16 rounded-full bg-slate-100" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (ports.length === 0) {
    return (
      <div className="text-center py-16 px-4 rounded-xl border border-dashed border-slate-300 bg-white shadow-sm">
        <Globe className="w-12 h-12 text-slate-300 mx-auto mb-3" />
        <h3 className="text-sm font-semibold text-slate-700">No ports monitored</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
          You are not currently monitoring any ports. Use the search bar above to look up ports by name, UN/LOCODE (e.g. NLRTM, SGSIN), or country.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {ports.map((port) => {
        const assessment = assessments.get(port.id);
        const isNotifEnabled = port.notificationsEnabled !== false;
        return (
          <div
            key={port.id}
            onClick={() => onSelectPort(port.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelectPort(port.id);
              }
            }}
            className="w-full text-left rounded-xl border border-slate-200 bg-white p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  port.isDefault ? 'bg-blue-50' : 'bg-emerald-50'
                }`}>
                  <MapPin className={`w-5 h-5 ${port.isDefault ? 'text-blue-500' : 'text-emerald-500'}`} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-slate-900 truncate">{port.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-2 flex-wrap">
                    <span>{port.locode} · {port.country} · {port.geofenceRadiusNm}nm</span>
                    {isNotifEnabled ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100">
                        <Bell className="w-2.5 h-2.5" /> Email alerts ON
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                        <BellOff className="w-2.5 h-2.5" /> Email alerts OFF
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2.5 flex-shrink-0">
                {assessment ? (
                  <RiskBadge tier={assessment.compositeTier} size="sm" />
                ) : (
                  <span className="text-xs text-slate-400">Loading risk...</span>
                )}
                {onToggleNotifications && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleNotifications(port.id, !isNotifEnabled);
                    }}
                    title={
                      isNotifEnabled
                        ? `Email notifications ON (sent to ${userEmail || 'your email'}). Click to opt out.`
                        : 'Email notifications OFF. Click to opt in.'
                    }
                    className={`p-1.5 rounded-lg transition-colors ${
                      isNotifEnabled
                        ? 'text-blue-600 hover:text-blue-700 hover:bg-blue-50'
                        : 'text-slate-400 hover:text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {isNotifEnabled ? <Bell className="w-4 h-4" /> : <BellOff className="w-4 h-4" />}
                  </button>
                )}
                {onRemovePort && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemovePort(port.id);
                    }}
                    title="Remove port from monitored list"
                    className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
                <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-slate-500 group-hover:translate-x-0.5 transition-all" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
