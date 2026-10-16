import React, { useState } from 'react';
import { Activity, Mail, ArrowRight, ShieldCheck, Bell, AlertCircle } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const DEMO_EMAILS = [
  'operations@pacific-shipping.com',
  'captain@rotterdam-logistics.nl',
  'risk-desk@globalmaritime.org',
];

export function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = email.trim().toLowerCase();
    if (!clean) {
      setError('Please enter your email address.');
      return;
    }
    if (!clean.includes('@') || !clean.includes('.')) {
      setError('Please enter a valid email address (e.g. captain@maritime.com).');
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await login(clean);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Please check backend connection.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickLogin = (demoEmail: string) => {
    setEmail(demoEmail);
    setError(null);
    setSubmitting(true);
    login(demoEmail).catch((err) => {
      setError(err instanceof Error ? err.message : 'Login failed.');
      setSubmitting(false);
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-blue-950 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-500 shadow-lg shadow-blue-500/30 mb-4">
          <Activity className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
          Berthmark
        </h1>
        <p className="text-sm text-cyan-200 mt-1 font-medium">
          Port-Call Risk Intelligence & Operational Monitoring
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white rounded-2xl shadow-2xl border border-slate-100 p-6 sm:p-8">
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-900">Sign In to Dashboard</h2>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Your login email is where real-time risk alerts and port disruption notices will be dispatched.
            </p>
          </div>

          {error && (
            <div className="mb-5 rounded-lg bg-red-50 border border-red-200 p-3.5 flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-xs text-red-700 font-medium">{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1.5">
                Work Email Address
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  id="email"
                  type="email"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. operations@maritime.com"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500 text-sm text-slate-900 placeholder:text-slate-400 transition-all"
                />
              </div>
            </div>

            <div className="rounded-xl bg-blue-50/70 border border-blue-100 p-3 flex items-start gap-2.5">
              <Bell className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
              <p className="text-[11px] text-blue-800 leading-relaxed">
                <span className="font-semibold">Notification default:</span> All monitored ports are automatically opted in to email alerts. You can toggle or opt out per port at any time.
              </p>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold shadow-md shadow-blue-600/20 disabled:opacity-50 transition-all cursor-pointer"
            >
              {submitting ? (
                <span>Signing in...</span>
              ) : (
                <>
                  <span>Continue to Dashboard</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Quick Demo Logins */}
          <div className="mt-6 pt-5 border-t border-slate-100">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
              Quick Demo Accounts
            </div>
            <div className="space-y-1.5">
              {DEMO_EMAILS.map((demo) => (
                <button
                  key={demo}
                  type="button"
                  onClick={() => handleQuickLogin(demo)}
                  disabled={submitting}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs font-mono text-slate-600 bg-slate-50 hover:bg-blue-50 hover:text-blue-700 border border-slate-200/80 transition-colors flex items-center justify-between group"
                >
                  <span className="truncate">{demo}</span>
                  <span className="text-[10px] text-slate-400 group-hover:text-blue-600 font-sans">Use &rarr;</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-6 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
            <span>Private multi-tenant portfolio isolation enabled</span>
          </div>
        </div>
      </div>
    </div>
  );
}
