import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, renderHook, act } from '@testing-library/react';
import { NotificationPanel } from '@/components/NotificationPanel';
import { useNotifications } from '@/hooks/useServices';
import { setServices } from '@/services';
import App from '@/App';
import type { Notification } from '@/types';

const mockNotifications: Notification[] = [
  {
    id: 'notif-1',
    type: 'stateChange',
    portId: 'port-rotterdam',
    portName: 'Port of Rotterdam',
    title: 'Port of Rotterdam: Risk tier changed to High',
    message: 'Anchorage queue surged by +80% over 7-day average baseline.',
    tier: 'high',
    previousTier: 'medium',
    timestamp: '2026-10-25T03:00:00Z',
    read: false,
  },
  {
    id: 'notif-2',
    type: 'dailyDigest',
    portId: 'port-singapore',
    portName: 'Port of Singapore',
    title: 'Daily Operational Digest: Singapore',
    message: 'Moderate terminal turnaround delays recorded across container berths.',
    tier: 'medium',
    previousTier: null,
    timestamp: '2026-10-25T02:00:00Z',
    read: true,
  },
  {
    id: 'notif-3',
    type: 'inApp',
    portId: 'port-antwerp',
    portName: 'Port of Antwerp-Bruges',
    title: 'Navigational Advisory: Antwerp',
    message: 'Tidal water levels optimal for deep-draft neoPanamax transit.',
    tier: 'low',
    previousTier: 'low',
    timestamp: '2026-10-25T01:00:00Z',
    read: false,
  },
];

describe('NotificationPanel Component', () => {
  it('renders notifications feed in reverse-chronological order with all details', () => {
    render(
      <NotificationPanel
        notifications={mockNotifications}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.getByTestId('header-unread-counter')).toHaveTextContent('2 new');

    // First item should be the newest (notif-1: Rotterdam)
    const items = screen.getAllByTestId(/^notification-item-/);
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent('Port of Rotterdam');
    expect(items[0]).toHaveTextContent('Port of Rotterdam: Risk tier changed to High');
    expect(items[0]).toHaveTextContent('High');
    expect(items[0]).toHaveTextContent('Medium → High');

    // Second item (notif-2: Singapore) without previousTier arrow
    expect(items[1]).toHaveTextContent('Port of Singapore');
    expect(items[1]).toHaveTextContent('Medium');
    expect(items[1].querySelector('[data-testid="notification-transition"]')).toBeNull();
  });

  it('switches between All and Unread filter tabs cleanly', () => {
    render(
      <NotificationPanel
        notifications={mockNotifications}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    // Initial view: All (3 items)
    expect(screen.getAllByTestId(/^notification-item-/)).toHaveLength(3);

    // Click Unread tab
    fireEvent.click(screen.getByTestId('tab-unread-notifications'));

    // Should only show 2 unread items (notif-1 and notif-3)
    const unreadItems = screen.getAllByTestId(/^notification-item-/);
    expect(unreadItems).toHaveLength(2);
    expect(screen.getByTestId('notification-item-notif-1')).toBeInTheDocument();
    expect(screen.getByTestId('notification-item-notif-3')).toBeInTheDocument();
    expect(screen.queryByTestId('notification-item-notif-2')).not.toBeInTheDocument();

    // Click back to All tab
    fireEvent.click(screen.getByTestId('tab-all-notifications'));
    expect(screen.getAllByTestId(/^notification-item-/)).toHaveLength(3);
  });

  it('clicking an unread notification item triggers onMarkAsRead', () => {
    const onMarkAsRead = vi.fn();
    render(
      <NotificationPanel
        notifications={mockNotifications}
        onMarkAsRead={onMarkAsRead}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    // Click unread notif-1
    fireEvent.click(screen.getByTestId('notification-item-notif-1'));
    expect(onMarkAsRead).toHaveBeenCalledTimes(1);
    expect(onMarkAsRead).toHaveBeenCalledWith('notif-1');

    // Click already-read notif-2 (should not trigger onMarkAsRead)
    fireEvent.click(screen.getByTestId('notification-item-notif-2'));
    expect(onMarkAsRead).toHaveBeenCalledTimes(1);
  });

  it('clicking Mark all as read triggers onMarkAllAsRead when unread > 0', () => {
    const onMarkAllAsRead = vi.fn();
    render(
      <NotificationPanel
        notifications={mockNotifications}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={onMarkAllAsRead}
        loading={false}
      />
    );

    const markAllBtn = screen.getByTestId('mark-all-read-btn');
    expect(markAllBtn).not.toBeDisabled();

    fireEvent.click(markAllBtn);
    expect(onMarkAllAsRead).toHaveBeenCalledTimes(1);
  });

  it('disables Mark all as read and hides header pill when unreadCount is 0', () => {
    const allRead = mockNotifications.map((n) => ({ ...n, read: true }));
    render(
      <NotificationPanel
        notifications={allRead}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    expect(screen.queryByTestId('header-unread-counter')).not.toBeInTheDocument();
    expect(screen.getByTestId('mark-all-read-btn')).toBeDisabled();
  });

  it('renders empty state when notifications array is empty', () => {
    render(
      <NotificationPanel
        notifications={[]}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    expect(screen.getByTestId('empty-notifications')).toHaveTextContent(
      'No notifications yet'
    );
  });

  it('renders empty unread state when Unread tab is selected and all are read', () => {
    const allRead = mockNotifications.map((n) => ({ ...n, read: true }));
    render(
      <NotificationPanel
        notifications={allRead}
        onMarkAsRead={vi.fn()}
        onMarkAllAsRead={vi.fn()}
        loading={false}
      />
    );

    fireEvent.click(screen.getByTestId('tab-unread-notifications'));
    expect(screen.getByTestId('empty-unread-notifications')).toHaveTextContent(
      'No unread notifications'
    );
  });
});

describe('Navigation Bell and Alert Feed Dropdown in App', () => {
  it('toggles notification panel dropdown and dismisses on outside click or Escape key', () => {
    render(<App />);

    const bellBtn = screen.getByTestId('notification-bell-btn');
    expect(bellBtn).toBeInTheDocument();
    expect(bellBtn.getAttribute('aria-label')).toBe('Notifications');

    // Initially closed
    expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument();

    // Click bell: open panel
    fireEvent.click(bellBtn);
    expect(screen.getByTestId('notification-panel')).toBeInTheDocument();

    // Press Escape: close panel
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument();

    // Reopen and click backdrop: close panel
    fireEvent.click(bellBtn);
    expect(screen.getByTestId('notification-panel')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('notification-backdrop'));
    expect(screen.queryByTestId('notification-panel')).not.toBeInTheDocument();
  });
});

describe('useNotifications hook polling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls getNotifications every 30 seconds and clears interval on unmount', async () => {
    const getNotificationsSpy = vi.fn().mockResolvedValue([]);
    setServices({
      ports: {} as any,
      risk: {} as any,
      notifications: {
        getNotifications: getNotificationsSpy,
        markAsRead: vi.fn(),
        markAllAsRead: vi.fn(),
        generateStateChangeAlert: vi.fn(),
      },
    });

    const { unmount } = renderHook(() => useNotifications());

    // Initial mount call
    expect(getNotificationsSpy).toHaveBeenCalledTimes(1);

    // Fast-forward 30 seconds
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(getNotificationsSpy).toHaveBeenCalledTimes(2);

    // Fast-forward another 30 seconds
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(getNotificationsSpy).toHaveBeenCalledTimes(3);

    // Unmount hook
    unmount();

    // Advance time again; should not call spy anymore
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(getNotificationsSpy).toHaveBeenCalledTimes(3);
  });
});
