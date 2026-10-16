import { useState, useMemo, useCallback } from 'react';
import {
  Bell,
  Globe,
  RefreshCw,
  Activity,
  AlertTriangle,
  LogOut,
  Mail,
  User as UserIcon,
} from 'lucide-react';
import type { VesselClass, User } from '@/types';
import { usePorts, useRiskAssessments, useNotifications } from '@/hooks/useServices';
import { useAuth } from '@/context/AuthContext';
import { LoginScreen } from '@/components/LoginScreen';
import { PortList } from '@/components/PortList';
import { PortSearch } from '@/components/PortSearch';
import { PortRiskDetail } from '@/components/PortRiskDetail';
import { VesselClassSelector } from '@/components/VesselClassSelector';
import { NotificationPanel } from '@/components/NotificationPanel';
import { isDemoAccount } from '@/utils/demoAccount';

export default function App() {
  const { user, loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Loading BerthMark...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <LoginScreen />;
  }

  return <Dashboard user={user} />;
}

function Dashboard({ user }: { user: User }) {
  const { logout } = useAuth();
  const {
    ports,
    loading: portsLoading,
    error: portsError,
    addPort,
    removePort,
    toggleNotifications,
    refresh: refreshPorts,
  } = usePorts(user.email);

  const [vesselClass, setVesselClass] = useState<VesselClass>('neoPanamax');
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const {
    assessments,
    loading: riskLoading,
    error: riskError,
    refresh: refreshRisk,
  } = useRiskAssessments(ports, vesselClass);

  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    refresh: refreshNotifications,
  } = useNotifications(user.email);

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
      await refreshRisk(true);
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
      await refreshRisk(true);
    } finally {
      setRefreshing(false);
    }
  }, [refreshRisk, selectedPort]);

  const handleAddPort = useCallback(
    async (port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>) => {
      const created = await addPort(port);
      await refreshNotifications();
      return created;
    },
    [addPort, refreshNotifications]
  );

  const handleRemovePort = useCallback(
    async (portId?: string) => {
      const targetId = portId || selectedPortId;
      if (!targetId) return;
      await removePort(targetId);
      if (selectedPortId === targetId) {
        setSelectedPortId(null);
      }
    },
    [removePort, selectedPortId]
  );

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
                <p className="text-xs text-slate-500 hidden sm:block">BerthMark Decision Support</p>
              </div>
            </div>

            <div className="flex items-center gap-2 sm:gap-3">
              {/* Status pill */}
              <div className="hidden lg:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200">
                <span
                  className={`w-2 h-2 rounded-full ${
                    portsError || riskError ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'
                  }`}
                />
                <span className="text-slate-600 font-medium">
                  {portsError || riskError ? 'FastAPI: Offline/Error' : 'FastAPI: Connected'}
                </span>
              </div>

              {/* Tracked ports count */}
              <div className="hidden md:flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-slate-50 border border-slate-200 text-slate-600">
                <Globe className="w-3.5 h-3.5 text-slate-400" />
                <span>{ports.length} monitored</span>
              </div>

              {/* Notifications bell */}
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                className="relative p-2 rounded-lg hover:bg-slate-100 transition-colors"
                title="Alerts and notifications"
              >
                <Bell className="w-5 h-5 text-slate-600" />
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
                    {unreadCount}
                  </span>
                )}
              </button>

              {/* User Account / Profile Badge */}
              <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
                <div
                  className={`flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs font-medium ${
                    isDemoAccount(user.email)
                      ? 'bg-amber-50 border-amber-200 text-amber-900'
                      : 'bg-blue-50 border-blue-100 text-blue-900'
                  }`}
                  title={
                    isDemoAccount(user.email)
                      ? `Logged in as ${user.email} (Demo account: Real email delivery turned off)`
                      : `Logged in as ${user.email} (Email notifications destination)`
                  }
                >
                  <Mail className={`w-3.5 h-3.5 ${isDemoAccount(user.email) ? 'text-amber-600' : 'text-blue-600'}`} />
                  <span className="max-w-[140px] sm:max-w-[180px] truncate">{user.email}</span>
                  {isDemoAccount(user.email) && (
                    <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-amber-200/80 text-amber-900 uppercase tracking-wider">
                      Demo
                    </span>
                  )}
                </div>

                <button
                  onClick={() => logout()}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
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
              userEmail={user.email}
              loading={false}
            />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Demo Account In-App Notice Banner */}
        {isDemoAccount(user.email) && (
          <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 p-4 flex items-start gap-3.5 shadow-sm">
            <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0 text-amber-700 mt-0.5">
              <Mail className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="text-sm font-semibold text-amber-950">
                  Demo Account Active: Outbound Email Notifications Turned Off
                </h4>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-amber-200/70 text-amber-800">
                  Bounce Protection Active
                </span>
              </div>
              <p className="text-xs text-amber-800/90 mt-1 leading-relaxed">
                You are currently logged in with a demo profile (<span className="font-mono font-medium text-amber-950">{user.email}</span>). Real outbound SMTP email delivery is disabled for demo accounts to prevent bounced emails. In-app alerts, port-call risk profiling, and live telemetry remain fully active. To receive actual email dispatches, configure SMTP and log in with a live recipient address.
              </p>
            </div>
          </div>
        )}

        {(portsError || riskError) && (
          <div className="mb-6 rounded-lg bg-red-50 border border-red-200 p-4 flex items-start justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-semibold text-red-800">FastAPI Backend Communication Issue</h4>
                <p className="text-xs text-red-700 mt-1">{portsError || riskError}</p>
                <p className="text-[11px] text-red-600 mt-1 font-mono">
                  Make sure backend is running: make run-backend (http://localhost:8000)
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                refreshPorts();
                refreshRisk();
              }}
              className="text-xs font-medium px-3 py-1.5 bg-red-100 hover:bg-red-200 text-red-800 rounded-md transition-colors flex-shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {selectedAssessment && selectedPort ? (
          <PortRiskDetail
            assessment={selectedAssessment}
            onBack={() => setSelectedPortId(null)}
            onRemove={() => handleRemovePort(selectedPort.id)}
            canRemove={true}
            onRefresh={handleRefreshDetail}
            refreshing={refreshing}
            notificationsEnabled={selectedPort.notificationsEnabled ?? true}
            onToggleNotifications={(enabled) => toggleNotifications(selectedPort.id, enabled)}
            userEmail={user.email}
          />
        ) : (
          <div className="space-y-6">
            {/* Dashboard Summary */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <SummaryCard
                label="Ports Monitored"
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
                <PortSearch onAddPort={handleAddPort} existingLocodes={existingLocodes} />
              </div>
              <div className="flex items-center gap-2">
                <VesselClassSelector value={vesselClass} onChange={setVesselClass} />
                <button
                  onClick={handleRefresh}
                  disabled={refreshing || riskLoading}
                  className="flex items-center gap-1.5 text-sm px-3 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors"
                  title="Refresh Risk Evaluation"
                >
                  <RefreshCw className={`w-4 h-4 text-slate-500 ${refreshing ? 'animate-spin' : ''}`} />
                </button>
              </div>
            </div>

            {/* Port List */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">
                  Monitored Ports Portfolio
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    Risk evaluated for {vesselClass.replace(/([A-Z])/g, ' $1').replace(/^./, (c) => c.toUpperCase())} class
                  </span>
                </h2>
              </div>
              <PortList
                ports={ports}
                assessments={assessmentMap}
                onSelectPort={handleSelectPort}
                onRemovePort={(id) => handleRemovePort(id)}
                onToggleNotifications={toggleNotifications}
                userEmail={user.email}
                loading={portsLoading || riskLoading}
              />
            </div>

            {/* Footer info */}
            <div className="rounded-lg bg-slate-100 border border-slate-200 p-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-slate-600">
                <div>
                  <div className="font-semibold text-slate-700 mb-1">Email Alert Routing</div>
                  Automated risk alerts are dispatched to{' '}
                  <span className="font-medium text-slate-800">{user.email}</span>. You can opt out
                  per port at any time.
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
