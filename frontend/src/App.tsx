import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Bell,
  Globe,
  RefreshCw,
  Activity,
  AlertTriangle,
  LogOut,
  LogIn,
  UserPlus,
  LayoutGrid,
  Map as MapIcon,
  Loader2,
} from 'lucide-react';
import type { VesselClass, RiskAssessment } from '@/types';
import { getServices } from '@/services';
import { usePorts, useRiskAssessments, useNotifications } from '@/hooks/useServices';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { LoginForm } from '@/components/LoginForm';
import { SignUpForm } from '@/components/SignUpForm';
import { PortList } from '@/components/PortList';
import { PortSearch } from '@/components/PortSearch';
import { PortRiskDetail } from '@/components/PortRiskDetail';
import { VesselClassSelector } from '@/components/VesselClassSelector';
import { NotificationPanel } from '@/components/NotificationPanel';
import { InteractiveMap } from '@/components/InteractiveMap';

// ─── Auth Portal (Sign In / Sign Up) ──────────────────────────────────────────

interface AuthPortalProps {
  currentPath: string;
  onNavigate: (path: string) => void;
}

function AuthPortal({ currentPath, onNavigate }: AuthPortalProps) {
  const isSignUp = currentPath === '/signup' || currentPath === '/signup/';
  const [tab, setTab] = useState<'signin' | 'signup'>(isSignUp ? 'signup' : 'signin');

  useEffect(() => {
    setTab(isSignUp ? 'signup' : 'signin');
  }, [isSignUp]);

  const handleSelectTab = (selected: 'signin' | 'signup') => {
    setTab(selected);
    onNavigate(selected === 'signup' ? '/signup' : '/');
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-between">
      {/* Top Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div
              className="flex items-center gap-3 cursor-pointer"
              onClick={() => handleSelectTab('signin')}
              data-testid="header-brand-logo"
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shadow-sm">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-slate-900">Port-Call Risk Tracker</h1>
                <p className="text-xs text-slate-500 hidden sm:block">
                  Maritime Port-Call Intelligence
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                data-testid="header-signin-btn"
                onClick={() => handleSelectTab('signin')}
                className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  tab === 'signin'
                    ? 'bg-slate-100 text-slate-900'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </button>
              <button
                data-testid="header-signup-btn"
                onClick={() => handleSelectTab('signup')}
                className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors cursor-pointer ${
                  tab === 'signup'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'text-white bg-blue-600 hover:bg-blue-700 shadow-xs'
                }`}
              >
                <UserPlus className="w-3.5 h-3.5" />
                <span>Sign Up</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Centered Auth Card Container */}
      <main className="flex-1 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 shadow-sm mb-3">
            <Activity className="w-6 h-6 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
            Port-Call Risk Tracker
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Real-time navigational, weather, and congestion risk intelligence
          </p>

          {/* Toggle Pills */}
          <div className="mt-6 flex rounded-lg bg-slate-200/80 p-1 border border-slate-200 max-w-xs mx-auto">
            <button
              type="button"
              data-testid="auth-tab-signin"
              onClick={() => handleSelectTab('signin')}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                tab === 'signin'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              data-testid="auth-tab-signup"
              onClick={() => handleSelectTab('signup')}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all cursor-pointer ${
                tab === 'signup'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Create Account
            </button>
          </div>
        </div>

        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          {tab === 'signin' ? (
            <LoginForm
              onSuccess={() => onNavigate('/')}
              onSwitchToSignUp={() => handleSelectTab('signup')}
            />
          ) : (
            <SignUpForm
              onSuccess={() => onNavigate('/')}
              onSwitchToLogin={() => handleSelectTab('signin')}
            />
          )}
        </div>
      </main>

      {/* Footer info */}
      <footer className="border-t border-slate-200 bg-white py-4">
        <div className="max-w-7xl mx-auto px-4 text-center text-xs text-slate-500">
          Berthmark Maritime Intelligence Platform &bull; PIANC Report 121 Compliant
        </div>
      </footer>
    </div>
  );
}

// ─── Authenticated Dashboard View ─────────────────────────────────────────────

interface DashboardProps {
  onNavigate: (path: string) => void;
}

function Dashboard({ onNavigate }: DashboardProps) {
  const { user, logout } = useAuth();
  const { ports, loading: portsLoading, addPort, removePort, refresh: refreshPorts } = usePorts();
  const [viewMode, setViewMode] = useState<'grid' | 'map'>('grid');
  const [vesselClass, setVesselClass] = useState<VesselClass>('neoPanamax');
  const [selectedPortId, setSelectedPortId] = useState<string | null>(null);
  const [customDetailAssessment, setCustomDetailAssessment] = useState<RiskAssessment | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const { assessments, loading: riskLoading, refresh: refreshRisk } = useRiskAssessments(
    ports,
    vesselClass
  );
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

  const activeAssessment = useMemo(
    () => (selectedPortId ? assessmentMap.get(selectedPortId) || customDetailAssessment : null),
    [assessmentMap, selectedPortId, customDetailAssessment]
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

  const handleSelectPort = useCallback(
    async (portId: string) => {
      setSelectedPortId(portId);
      const existing = assessmentMap.get(portId);
      if (existing) {
        setCustomDetailAssessment(null);
        return;
      }
      setDetailLoading(true);
      try {
        const assessment = await getServices().risk.getRiskAssessment(portId, '', vesselClass);
        setCustomDetailAssessment(assessment);
      } catch (err) {
        console.error('Failed to load risk assessment for port', portId, err);
      } finally {
        setDetailLoading(false);
      }
    },
    [assessmentMap, vesselClass]
  );

  const handleRefreshDetail = useCallback(async () => {
    if (!selectedPortId) return;
    setRefreshing(true);
    try {
      if (selectedPort) {
        await refreshRisk();
      } else {
        const assessment = await getServices().risk.getRiskAssessment(selectedPortId, '', vesselClass);
        setCustomDetailAssessment(assessment);
      }
    } finally {
      setRefreshing(false);
    }
  }, [refreshRisk, selectedPort, selectedPortId, vesselClass]);

  const handleRemovePort = useCallback(
    async (portId?: string) => {
      const targetId = portId || selectedPortId;
      if (!targetId) return;
      await removePort(targetId);
      if (selectedPortId === targetId) {
        setSelectedPortId(null);
        setCustomDetailAssessment(null);
      }
    },
    [removePort, selectedPortId]
  );

  // Close notification panel on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showNotifications) setShowNotifications(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showNotifications]);

  const existingSubscriptions = useMemo(
    () => ports.map((p) => ({ locode: p.locode, vesselClass: p.vesselClass })),
    [ports]
  );
  const existingLocodes = useMemo(() => ports.map((p) => p.locode), [ports]);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div
              className="flex items-center gap-3 cursor-pointer"
              onClick={() => onNavigate('/')}
              data-testid="header-brand-logo"
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shadow-sm">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-slate-900">Port-Call Risk Tracker</h1>
                <p className="text-xs text-slate-500 hidden sm:block">
                  Maritime Port-Call Intelligence
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-2 text-sm">
                <Globe className="w-4 h-4 text-slate-400" />
                <span className="text-slate-600">{ports.length} ports tracked</span>
              </div>

              <div className="flex items-center gap-2">
                <span
                  data-testid="user-display"
                  className="text-xs font-semibold text-slate-700 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200"
                >
                  {user?.name || user?.email}
                </span>
                <button
                  onClick={logout}
                  aria-label="Sign Out"
                  className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Sign Out</span>
                </button>
              </div>

              <button
                data-testid="notification-bell-btn"
                onClick={() => setShowNotifications((prev) => !prev)}
                className="relative p-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Notifications"
              >
                <Bell className="w-5 h-5 text-slate-600" />
                {unreadCount > 0 && (
                  <span
                    data-testid="notification-badge"
                    className="absolute -top-0.5 -right-0.5 min-w-[18px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center shadow-xs"
                  >
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Notification dropdown */}
      {showNotifications && (
        <div
          data-testid="notification-backdrop"
          className="fixed inset-0 z-40"
          onClick={() => setShowNotifications(false)}
        >
          <div
            className="absolute right-4 top-16 z-50"
            onClick={(e) => e.stopPropagation()}
          >
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
        {detailLoading ? (
          <div data-testid="detail-loading-state" className="flex flex-col items-center justify-center py-24 text-slate-500">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600 mb-3" />
            <span className="text-sm font-medium">Loading port risk summary...</span>
          </div>
        ) : activeAssessment && viewMode !== 'map' ? (
          <PortRiskDetail
            assessment={activeAssessment}
            onBack={() => {
              setSelectedPortId(null);
              setCustomDetailAssessment(null);
            }}
            onRemove={selectedPort ? () => handleRemovePort(selectedPort.id) : undefined}
            canRemove={Boolean(selectedPort)}
            onRefresh={handleRefreshDetail}
            refreshing={refreshing}
            onSelectAlternative={handleSelectPort}
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
                <PortSearch
                  onAddPort={addPort}
                  existingLocodes={existingLocodes}
                  existingSubscriptions={existingSubscriptions}
                  defaultVesselClass={vesselClass}
                />
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {/* View Mode Toggle */}
                <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 shadow-2xs">
                  <button
                    data-testid="toggle-grid-view"
                    onClick={() => setViewMode('grid')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors cursor-pointer ${
                      viewMode === 'grid'
                        ? 'bg-blue-50 text-blue-700 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <LayoutGrid className="w-3.5 h-3.5" />
                    <span>Grid</span>
                  </button>
                  <button
                    data-testid="toggle-map-view"
                    onClick={() => setViewMode('map')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors cursor-pointer ${
                      viewMode === 'map'
                        ? 'bg-blue-50 text-blue-700 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <MapIcon className="w-3.5 h-3.5" />
                    <span>Map</span>
                  </button>
                </div>

                <VesselClassSelector value={vesselClass} onChange={setVesselClass} />
                <button
                  onClick={handleRefresh}
                  disabled={refreshing || riskLoading}
                  className="flex items-center gap-1.5 text-sm px-3 py-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-50 transition-colors cursor-pointer"
                >
                  <RefreshCw
                    className={`w-4 h-4 text-slate-500 ${
                      refreshing ? 'animate-spin' : ''
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Port Display (Grid vs Map View) */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-slate-700">
                  {viewMode === 'map' ? 'Interactive Risk Map' : 'Monitored Ports'}
                  <span className="ml-2 text-xs font-normal text-slate-400">
                    Risk evaluated for{' '}
                    {vesselClass
                      .replace(/([A-Z])/g, ' $1')
                      .replace(/^./, (c) => c.toUpperCase())}{' '}
                    class
                  </span>
                </h2>
              </div>

              {viewMode === 'map' ? (
                <InteractiveMap
                  ports={ports}
                  assessments={assessmentMap}
                  vesselClass={vesselClass}
                  onSelectPort={handleSelectPort}
                  onViewPortDetail={(portId) => {
                    setViewMode('grid');
                    handleSelectPort(portId);
                  }}
                  onAddFirstPort={() => {
                    const input = document.getElementById('port-search-input');
                    input?.focus();
                  }}
                  onAddPort={addPort}
                />
              ) : (
                <PortList
                  ports={ports}
                  assessments={assessmentMap}
                  onSelectPort={handleSelectPort}
                  onRemovePort={handleRemovePort}
                  loading={portsLoading || riskLoading}
                  selectedVesselClass={vesselClass}
                  onAddFirstPort={() => {
                    const input = document.getElementById('port-search-input');
                    input?.focus();
                  }}
                />
              )}
            </div>

            {/* Footer info */}
            <div className="rounded-lg bg-slate-100 border border-slate-200 p-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-slate-600">
                <div>
                  <div className="font-semibold text-slate-700 mb-1">
                    Evaluation Cycle
                  </div>
                  Risk scores re-evaluated every 6 hours with anti-flapping cooldown
                  logic.
                </div>
                <div>
                  <div className="font-semibold text-slate-700 mb-1">
                    Composite Scoring
                  </div>
                  Weakest-link rule: any sub-risk reaching High elevates the composite
                  to High.
                </div>
                <div>
                  <div className="font-semibold text-slate-700 mb-1">
                    Safety Standards
                  </div>
                  Weather and navigational thresholds follow PIANC Report 121
                  guidelines.
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// ─── App Root Component ───────────────────────────────────────────────────────

function AppContent() {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const [currentPath, setCurrentPath] = useState<string>(() =>
    typeof window !== 'undefined' ? window.location.pathname : '/'
  );

  const navigate = useCallback((path: string) => {
    if (typeof window !== 'undefined') {
      window.history.pushState({}, '', path);
      setCurrentPath(path);
    }
  }, []);

  // Listen to popstate for browser navigation (back/forward)
  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(typeof window !== 'undefined' ? window.location.pathname : '/');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Redirect to dashboard if authenticated user navigates to /signup
  useEffect(() => {
    if (isAuthenticated && (currentPath === '/signup' || currentPath === '/signup/')) {
      navigate('/');
    }
  }, [isAuthenticated, currentPath, navigate]);

  if (authLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin" />
          <span className="text-sm font-medium text-slate-500">Loading Berthmark...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthPortal currentPath={currentPath} onNavigate={navigate} />;
  }

  return <Dashboard onNavigate={navigate} />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
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
      <div
        className={`w-11 h-11 rounded-lg flex items-center justify-center ${c.bg} ${c.icon}`}
      >
        {icon}
      </div>
      <div>
        <div className={`text-2xl font-bold ${c.text}`}>{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  );
}
