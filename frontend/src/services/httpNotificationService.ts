import type { Notification } from '@/types';
import type { INotificationService } from './interfaces';
import { httpClient } from './httpClient';

export class HttpNotificationService implements INotificationService {
  async getNotifications(
    userIdOrUnreadOnly?: string | boolean,
    unreadOnlyOrLimit?: boolean | number,
    limitParam?: number
  ): Promise<Notification[]> {
    let unreadOnly: boolean | undefined;
    let limit: number | undefined;

    if (typeof userIdOrUnreadOnly === 'boolean') {
      unreadOnly = userIdOrUnreadOnly;
      if (typeof unreadOnlyOrLimit === 'number') {
        limit = unreadOnlyOrLimit;
      }
    } else if (typeof userIdOrUnreadOnly === 'string') {
      if (typeof unreadOnlyOrLimit === 'boolean') {
        unreadOnly = unreadOnlyOrLimit;
      }
      if (typeof limitParam === 'number') {
        limit = limitParam;
      }
    }

    const params = new URLSearchParams();
    if (unreadOnly !== undefined) {
      params.set('unreadOnly', String(unreadOnly));
    }
    if (limit !== undefined) {
      params.set('limit', String(limit));
    }

    const query = params.toString();
    const endpoint = query ? `/notifications?${query}` : '/notifications';
    return httpClient.get<Notification[]>(endpoint);
  }

  async markAsRead(notificationId: string): Promise<void> {
    await httpClient.patch<void>(
      `/notifications/${encodeURIComponent(notificationId)}/read`
    );
  }

  async markAllAsRead(_userId?: string): Promise<void> {
    await httpClient.post<void>('/notifications/mark-all-read');
  }

  async generateStateChangeAlert(
    portId: string,
    portName: string,
    newTier: Notification['tier'],
    previousTier: Notification['tier'] | null
  ): Promise<Notification> {
    return httpClient.post<Notification>('/notifications', {
      portId,
      portName,
      newTier,
      previousTier,
      title: `${portName} Risk State Change`,
      message: `Port ${portName} transitioned to ${newTier.toUpperCase()} risk.`,
    });
  }
}
