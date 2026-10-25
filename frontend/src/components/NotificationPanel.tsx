import React, { useState, useMemo } from 'react';
import {
  Bell,
  BellOff,
  CheckCheck,
  AlertTriangle,
  FileText,
  Mail,
} from 'lucide-react';
import type { Notification } from '@/types';
import { TIER_COLORS, TIER_LABELS, timeAgo } from '@/utils/riskDisplay';

export interface NotificationPanelProps {
  notifications: Notification[];
  onMarkAsRead: (id: string) => void;
  onMarkAllAsRead: () => void;
  loading: boolean;
  className?: string;
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
  loading,
  className = '',
}: NotificationPanelProps) {
  const [filter, setFilter] = useState<'all' | 'unread'>('all');

  const unreadCount = useMemo(
    () => notifications.filter((n) => !n.read).length,
    [notifications]
  );

  // Sort reverse-chronologically (newest first)
  const sortedNotifications = useMemo(() => {
    return [...notifications].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }, [notifications]);

  // Apply tab filter
  const displayedNotifications = useMemo(() => {
    if (filter === 'unread') {
      return sortedNotifications.filter((n) => !n.read);
    }
    return sortedNotifications;
  }, [sortedNotifications, filter]);

  return (
    <div
      role="dialog"
      aria-label="Notification Feed"
      data-testid="notification-panel"
      className={`w-full max-w-sm rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-100 ${className}`}
    >
      {/* ── Header ── */}
      <div className="p-3.5 border-b border-slate-100">
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-slate-700" />
            <h3 className="text-sm font-bold text-slate-800">Notifications</h3>
            {unreadCount > 0 && (
              <span
                data-testid="header-unread-counter"
                className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700"
              >
                {unreadCount} new
              </span>
            )}
          </div>

          <button
            onClick={onMarkAllAsRead}
            disabled={unreadCount === 0}
            data-testid="mark-all-read-btn"
            className={`flex items-center gap-1 text-xs font-medium transition-colors ${
              unreadCount > 0
                ? 'text-blue-600 hover:text-blue-800 cursor-pointer'
                : 'text-slate-300 cursor-not-allowed'
            }`}
          >
            <CheckCheck className="w-3.5 h-3.5" />
            <span>Mark all as read</span>
          </button>
        </div>

        {/* Filter Tabs: All vs Unread */}
        <div className="flex items-center rounded-lg bg-slate-100 p-0.5 text-xs font-semibold">
          <button
            onClick={() => setFilter('all')}
            data-testid="tab-all-notifications"
            className={`flex-1 py-1 rounded-md transition-colors cursor-pointer text-center ${
              filter === 'all'
                ? 'bg-white text-slate-800 shadow-2xs'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            All ({notifications.length})
          </button>
          <button
            onClick={() => setFilter('unread')}
            data-testid="tab-unread-notifications"
            className={`flex-1 py-1 rounded-md transition-colors cursor-pointer text-center ${
              filter === 'unread'
                ? 'bg-white text-slate-800 shadow-2xs'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            Unread ({unreadCount})
          </button>
        </div>
      </div>

      {/* ── Notification Items Feed ── */}
      <div className="max-h-96 overflow-y-auto divide-y divide-slate-100">
        {loading ? (
          <div
            data-testid="notifications-loading"
            className="px-4 py-10 text-center text-xs text-slate-400"
          >
            Loading...
          </div>
        ) : notifications.length === 0 ? (
          <div
            data-testid="empty-notifications"
            className="px-4 py-10 text-center"
          >
            <BellOff className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-xs font-medium text-slate-500">
              No notifications yet
            </p>
          </div>
        ) : displayedNotifications.length === 0 && filter === 'unread' ? (
          <div
            data-testid="empty-unread-notifications"
            className="px-4 py-10 text-center"
          >
            <BellOff className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-xs font-medium text-slate-500">
              No unread notifications
            </p>
          </div>
        ) : (
          displayedNotifications.map((n) => {
            const colors = TIER_COLORS[n.tier] || TIER_COLORS.low;
            const Icon = TYPE_ICONS[n.type] ?? Bell;

            return (
              <div
                key={n.id}
                role="button"
                tabIndex={0}
                data-testid={`notification-item-${n.id}`}
                onClick={() => {
                  if (!n.read) {
                    onMarkAsRead(n.id);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    if (!n.read) onMarkAsRead(n.id);
                  }
                }}
                className={`w-full text-left px-4 py-3 hover:bg-slate-50/80 transition-colors flex items-start gap-3 cursor-pointer ${
                  !n.read ? 'bg-blue-50/30' : 'bg-white'
                }`}
              >
                {/* Icon */}
                <div
                  className={`mt-0.5 w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${colors.bg}`}
                >
                  <Icon className={`w-4 h-4 ${colors.text}`} />
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-1">
                    <span
                      data-testid="notification-port-name"
                      className="text-xs font-bold text-slate-900 truncate"
                    >
                      {n.portName}
                    </span>
                    <span
                      data-testid="notification-timestamp"
                      className="text-[10px] text-slate-400 shrink-0"
                    >
                      {timeAgo(n.timestamp)}
                    </span>
                  </div>

                  <div
                    data-testid="notification-title"
                    className="text-xs font-semibold text-slate-700 mt-0.5 truncate"
                  >
                    {n.title}
                  </div>

                  <div
                    data-testid="notification-message"
                    className="text-xs text-slate-500 mt-1 line-clamp-2 leading-relaxed"
                  >
                    {n.message}
                  </div>

                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    {/* Risk Tier Badge */}
                    <span
                      data-testid="notification-tier-badge"
                      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${colors.bg} ${colors.text} ${colors.border}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
                      {TIER_LABELS[n.tier]}
                    </span>

                    {/* Previous -> New Transition Arrow */}
                    {n.previousTier && (
                      <span
                        data-testid="notification-transition"
                        className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200"
                      >
                        {TIER_LABELS[n.previousTier]} → {TIER_LABELS[n.tier]}
                      </span>
                    )}
                  </div>
                </div>

                {/* Unread indicator dot */}
                {!n.read && (
                  <span
                    data-testid="notification-unread-dot"
                    className="w-2 h-2 rounded-full bg-blue-600 shrink-0 mt-2"
                  />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* ── Footer ── */}
      <div className="px-4 py-2.5 border-t border-slate-100 bg-slate-50/70">
        <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <Mail className="w-3.5 h-3.5" />
          <span>Real-time state change alerts and operational digests</span>
        </div>
      </div>
    </div>
  );
}
