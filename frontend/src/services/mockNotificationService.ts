import type { Notification } from '@/types';
import type { INotificationService } from '@/services/interfaces';
import type { RiskTier } from '@/types';

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const TIER_LABELS: Record<RiskTier, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
};

export class MockNotificationService implements INotificationService {
  private store: Map<string, Notification[]> = new Map();

  async getNotifications(userId: string): Promise<Notification[]> {
    await delay(200);
    return (this.store.get(userId) ?? []).slice().reverse();
  }

  async markAsRead(notificationId: string): Promise<void> {
    await delay(50);
    for (const [, notifs] of this.store) {
      const n = notifs.find((x) => x.id === notificationId);
      if (n) {
        n.read = true;
        break;
      }
    }
  }

  async markAllAsRead(userId: string): Promise<void> {
    await delay(100);
    const notifs = this.store.get(userId) ?? [];
    notifs.forEach((n) => (n.read = true));
  }

  generateStateChangeAlert(
    portId: string,
    portName: string,
    newTier: RiskTier,
    previousTier: RiskTier | null
  ): Notification {
    const notification: Notification = {
      id: `notif-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: 'stateChange',
      portId,
      portName,
      title: `${portName}: Risk tier changed to ${TIER_LABELS[newTier]}`,
      message:
        previousTier !== null
          ? `${portName} risk status shifted from ${TIER_LABELS[previousTier]} to ${TIER_LABELS[newTier]}.`
          : `${portName} initial risk assessment: ${TIER_LABELS[newTier]}.`,
      tier: newTier,
      previousTier,
      timestamp: new Date().toISOString(),
      read: false,
    };

    // Store under a default user key — in a real app this would be the actual userId
    const userId = 'mock-user';
    const existing = this.store.get(userId) ?? [];
    this.store.set(userId, [...existing, notification]);

    return notification;
  }
}
