import { useState, useMemo, useCallback } from 'react';
import { Bell, Globe, RefreshCw, Activity, AlertTriangle } from 'lucide-react';
import type { VesselClass } from '@/types';
import { usePorts, useRiskAssessments, useNotifications } from '@/hooks/useServices';
import { PortList } from '@/components/PortList';
import { PortSearch } from '@/components/PortSearch';
import { PortRiskDetail } from '@/components/PortRiskDetail';
import { VesselClassSelector } from '@/components/VesselClassSelector';
import { NotificationPanel } from '@/components/NotificationPanel';
import { getServices } from '@/services';

export default function App() {
  const { ports, loading: portsLoading, addPort, removePort } = usePorts();
  const [vesselClass, setVesselClass] = useState<VesselClass>('neoPanamax');
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const { assessments, loading: riskLoading, refresh: refreshRisk } = useRiskAssessments(ports, vesselClass);
  const { notifications, unreadCount, markAsRead, markAllAsRead } = useNotifications();

  const assessmentMap = useMemo(() => {
    const map = new Map();
    assessments.forEach((a) => map.set(a.portId, a));
    return map;
  }, [assessments]);

  const selectedPort = useMemo(
    () => ports.find((p) => p.id === selectedPortId) ?? null,
    [ports, selectedPortId]
  );

  const selectedAssessment = useMemo(
    () => (selectedPortId ? assessmentMap.get(selectedPortId) ?? null : null),
    [assessmentMap, selectedPortId]
  );

  const summary = useMemo(() => {
    const high = assessments.filter((a) => a.compositeTier === 'high').length;
    const medium = assessments.filter((a) => a.compositeTier === 'medium').length;
    const low = assessments.filter((a) => a.compositeTier === 'low').length;
    return { high, medium, low, total: assessments.length };
  }, [assessments]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshRisk();
    } finally {
      setRefreshing(false);
    }
  }, [refreshRisk]);

  const handleSelectPort = useCallback((portId: string) => {
    setSelectedPortId(portId);
  }, []);

  const handleRefreshDetail = useCallback(async () => {
    if (!selectedPort) return;
    setRefreshing(true);
    try {
      await refreshRisk();
    } finally {
      setRefreshing(false);
    }
  }, [refreshRisk, selectedPort]);

  const handleRemovePort = useCallback(async () => {
    if (!selectedPortId) return;
    await removePort(selectedPortId);
    setSelectedPortId(null);
  }, [removePort, selectedPortId]);

  const existingLocodes = useMemo(() => ports.map((p) => p.locode), [ports]);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shadow-sm">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-slate-900">Port-Call Risk Tracker</h1>
                <p className="text-xs text-slate-500 hidden sm:block">Monitoring & Assessment Tool</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-2 text-sm">
                <Globe className="w-4 h-4 text-slate-400" />
                <span className="text-slate-600">{ports.length} ports tracked</span>
              </div>
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                className="relative p-2 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <Bell className="w-5 h-5 text-slate-600" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                    {unreadCount}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Notification dropdown */}
      {showNotifications && (
        <div className="fixed inset-0 z-40" onClick={() => setShowNotifications(false)}>
          <div className="absolute right-4 top-16 z-50" onClick={(e) => e.stopPropagation()}>
            <NotificationPanel
              notifications={notifications}
              onMarkAsRead={markAsRead}
              onMarkAllAsRead={markAllAsRead}
              loading={false}
            />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {selectedAssessment && selectedPort ? (
          <PortRiskDetail
            assessment={selectedAssessment}
            onBack={() => setSelectedPortId(null)}
            onRemove={handleRemovePort}
            canRemove={!selectedPort.isDefault}
            onRefresh={handleRefreshDetail}
            refreshing={refreshing}
          />
        ) : (
          <div className="space-y-6">
            {/* Dashboard Summary */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <SummaryCard
                label="Ports Tracked"
                value={ports.length}
                icon={<Globe className="w-5 h-5" />}
                color="blue"
              />
              <SummaryCard
                label="High Risk"
                value={summary.high}
                icon={<AlertTriangle className="w-5 h-5" />}
                color="red"
              />
              <SummaryCard
                label="Medium Risk"
                value={summary.medium}
                icon={<Activity className="w-5 h-5" />}
                color="amber"
              />
              <SummaryCard
                label="Low Risk"
                value={summary.low}
                icon={<Activity className="w-5 h-5" />}
                color="emerald"
              />
            </div>

            {/* Controls Bar */}
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
              <div className="flex-1 w-full max-w-md">
                <PortSearch onAddPort={addPort} existingLocodes={existingLocodes} />
              </div>
              <div className="flex items-center gap-2">
                <VesselClassSelector value={vesselClass} onChange={setVesselClass} />
                <button
                  onClick={handleRefresh}
                  disabled={refreshing || riskLoading}
                  className="flex items-center gap-1.5 text-sm px-3 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`w-4 h-4 text-slate-500 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Port List */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">
                  Monitored Ports
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    Risk evaluated for {vesselClass.replace(/([A-Z])/g, ' $1').replace(/^./, (c) => c.toUpperCase())} class
                  </span>
                </h2>
              </div>
              <PortList
                ports={ports}
                assessments={assessmentMap}
                onSelectPort={handleSelectPort}
                loading={portsLoading || riskLoading}
              />
            </div>

            {/* Footer info */}
            <div className="rounded-lg bg-slate-100 border border-slate-200 p-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-slate-600">
                <div>
                  <div className="font-semibold text-slate-700 mb-1">Evaluation Cycle</div>
                  Risk scores re-evaluated every 6 hours with anti-flapping cooldown logic.
                </div>
                <div>
                  <div className="font-semibold text-slate-700 mb-1">Composite Scoring</div>
                  Weakest-link rule: any sub-risk reaching High elevates the composite to High.
                </div>
                <div>
                  <div className="font-semibold text-slate-700 mb-1">Safety Standards</div>
                  Weather and navigational thresholds follow PIANC Report 121 guidelines.
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  color: 'blue' | 'red' | 'amber' | 'emerald';
}) {
  const colorMap = {
    blue: { bg: 'bg-blue-50', text: 'text-blue-600', icon: 'text-blue-500' },
    red: { bg: 'bg-red-50', text: 'text-red-600', icon: 'text-red-500' },
    amber: { bg: 'bg-amber-50', text: 'text-amber-600', icon: 'text-amber-500' },
    emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600', icon: 'text-emerald-500' },
  };
  const c = colorMap[color];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-4">
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center ${c.bg} ${c.icon}`}>
        {icon}
      </div>
      <div>
        <div className={`text-2xl font-bold ${c.text}`}>{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  );
}
