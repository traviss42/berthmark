import { Bell, BellOff, Check, CheckCheck, AlertTriangle, Mail, FileText, Info } from 'lucide-react';
import type { Notification } from '@/types';
import { TIER_COLORS, TIER_LABELS, timeAgo } from '@/utils/riskDisplay';
import { isDemoAccount } from '@/utils/demoAccount';

interface Props {
  notifications: Notification[];
  onMarkAsRead: (id: string) => void;
  onMarkAllAsRead: () => void;
  userEmail?: string;
  loading: boolean;
}

const TYPE_ICONS = {
  stateChange: AlertTriangle,
  dailyDigest: FileText,
  inApp: Bell,
};

export function NotificationPanel({
  notifications,
  onMarkAsRead,
  onMarkAllAsRead,
  userEmail,
  loading,
}: Props) {
  const unread = notifications.filter((n) => !n.read);
  const isDemo = isDemoAccount(userEmail);

  return (
    <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white shadow-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-slate-600" />
          <span className="text-sm font-semibold text-slate-800">Notifications</span>
          {unread.length > 0 && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
              {unread.length} new
            </span>
          )}
        </div>
        {unread.length > 0 && (
          <button
            onClick={onMarkAllAsRead}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
          >
            <CheckCheck className="w-3.5 h-3.5" />
            Mark all
          </button>
        )}
      </div>

      {isDemo && (
        <div className="px-3.5 py-2.5 bg-amber-50 border-b border-amber-100 flex items-start gap-2 text-[11px] text-amber-900 leading-tight">
          <Info className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
          <span>
            <strong className="font-semibold">Demo Account:</strong> Email notifications are turned off to prevent bounces. In-app alerts remain active.
          </span>
        </div>
      )}

      <div className="max-h-96 overflow-y-auto">
        {loading ? (
          <div className="px-4 py-8 text-center text-sm text-slate-400">Loading...</div>
        ) : notifications.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <BellOff className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No notifications yet</p>
          </div>
        ) : (
          notifications.map((n) => {
            const colors = TIER_COLORS[n.tier];
            const Icon = TYPE_ICONS[n.type] ?? Bell;
            return (
              <button
                key={n.id}
                onClick={() => !n.read && onMarkAsRead(n.id)}
                className={`w-full text-left px-4 py-3 border-b border-slate-50 last:border-0 hover:bg-slate-50 transition-colors flex items-start gap-3 ${
                  !n.read ? 'bg-blue-50/30' : ''
                }`}
              >
                <div className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${colors.bg}`}>
                  <Icon className={`w-4 h-4 ${colors.text}`} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-800 truncate">{n.title}</div>
                  <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{n.message}</div>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className={`inline-flex items-center gap-1 text-xs font-medium ${colors.text}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
                      {TIER_LABELS[n.tier]}
                    </span>
                    <span className="text-xs text-slate-400">{timeAgo(n.timestamp)}</span>
                    {n.type === 'stateChange' && n.previousTier && (
                      <span className="text-xs text-slate-400">
                        {TIER_LABELS[n.previousTier]} → {TIER_LABELS[n.tier]}
                      </span>
                    )}
                    {n.recipientEmail && (
                      <span className="inline-flex items-center gap-1 text-[10px] text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100">
                        <Mail className="w-2.5 h-2.5" /> {n.recipientEmail}
                      </span>
                    )}
                  </div>
                </div>
                {!n.read && <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0 mt-1.5" />}
              </button>
            );
          })
        )}
      </div>

      <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <Mail className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
          <span className="truncate">
            Alerts sent to: <strong className="text-slate-700">{userEmail || 'login email'}</strong>
          </span>
        </div>
      </div>
    </div>
  );
}
