import type {
  Port,
  RiskAssessment,
  Notification,
  VesselClass,
  RiskTier,
} from '@/types';
import type {
  IPortService,
  IRiskService,
  INotificationService,
  IServices,
} from '@/services/interfaces';

export const DEFAULT_API_URL = 'http://localhost:8000';

export function getApiBaseUrl(): string {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '');
  }
  return DEFAULT_API_URL;
}

export function getAuthToken(userId?: string): string {
  return userId ? `Bearer ${userId}` : 'Bearer mock-user';
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  baseUrl?: string,
  userId?: string
): Promise<T> {
  const base = (baseUrl !== undefined ? baseUrl : getApiBaseUrl()).replace(/\/+$/, '');
  const url = `${base}${path}`;
  const authHeader = options.headers && 'Authorization' in (options.headers as Record<string, string>)
    ? {}
    : { Authorization: getAuthToken(userId) };

  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader,
      ...((options.headers as Record<string, string>) || {}),
    },
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    const message =
      (errorBody && (errorBody.detail || errorBody.message)) ||
      `API request failed with status ${res.status}: ${res.statusText}`;
    throw new ApiError(res.status, message, errorBody);
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return (await res.json()) as T;
}

export class ApiPortService implements IPortService {
  constructor(private baseUrl?: string) {}

  async getPorts(userId: string): Promise<Port[]> {
    return request<Port[]>('/api/v1/ports', { method: 'GET' }, this.baseUrl, userId);
  }

  async getDefaultPorts(): Promise<Port[]> {
    return request<Port[]>('/api/v1/ports/defaults', { method: 'GET' }, this.baseUrl);
  }

  async searchPorts(query: string): Promise<Port[]> {
    const q = query.trim();
    if (!q) {
      return [];
    }
    return request<Port[]>(
      `/api/v1/ports/search?q=${encodeURIComponent(q)}`,
      { method: 'GET' },
      this.baseUrl
    );
  }

  async addPort(
    port: Omit<Port, 'id' | 'isDefault' | 'addedByUserId'>,
    userId: string
  ): Promise<Port> {
    return request<Port>(
      '/api/v1/ports',
      {
        method: 'POST',
        body: JSON.stringify(port),
      },
      this.baseUrl,
      userId
    );
  }

  async removePort(portId: string, userId: string): Promise<void> {
    return request<void>(
      `/api/v1/ports/${encodeURIComponent(portId)}`,
      { method: 'DELETE' },
      this.baseUrl,
      userId
    );
  }
}

export class ApiRiskService implements IRiskService {
  constructor(private baseUrl?: string) {}

  async getRiskAssessment(
    portId: string,
    portName: string,
    vesselClass: VesselClass
  ): Promise<RiskAssessment> {
    const query = new URLSearchParams({
      vesselClass,
      ...(portName ? { portName } : {}),
    });
    return request<RiskAssessment>(
      `/api/v1/ports/${encodeURIComponent(portId)}/risk?${query.toString()}`,
      { method: 'GET' },
      this.baseUrl
    );
  }

  async getBulkRiskAssessments(
    ports: { id: string; name: string }[],
    vesselClass: VesselClass
  ): Promise<RiskAssessment[]> {
    if (ports.length === 0) {
      return [];
    }
    return request<RiskAssessment[]>(
      '/api/v1/risk/bulk-assessments',
      {
        method: 'POST',
        body: JSON.stringify({ ports, vesselClass }),
      },
      this.baseUrl
    );
  }

  async getHistoricalTrend(
    portId: string,
    vesselClass: VesselClass,
    days: number
  ): Promise<RiskAssessment[]> {
    return request<RiskAssessment[]>(
      `/api/v1/ports/${encodeURIComponent(portId)}/risk/trend?vesselClass=${encodeURIComponent(vesselClass)}&days=${days}`,
      { method: 'GET' },
      this.baseUrl
    );
  }
}

export class ApiNotificationService implements INotificationService {
  constructor(private baseUrl?: string) {}

  async getNotifications(userId: string): Promise<Notification[]> {
    return request<Notification[]>(
      '/api/v1/notifications',
      { method: 'GET' },
      this.baseUrl,
      userId
    );
  }

  async markAsRead(notificationId: string): Promise<void> {
    return request<void>(
      `/api/v1/notifications/${encodeURIComponent(notificationId)}/read`,
      { method: 'PATCH' },
      this.baseUrl
    );
  }

  async markAllAsRead(userId: string): Promise<void> {
    return request<void>(
      '/api/v1/notifications/mark-all-read',
      { method: 'POST' },
      this.baseUrl,
      userId
    );
  }

  generateStateChangeAlert(
    portId: string,
    portName: string,
    newTier: RiskTier,
    previousTier: RiskTier | null
  ): Notification {
    const notif: Notification = {
      id: `notif-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      type: 'stateChange',
      portId,
      portName,
      title: `${portName}: Risk tier changed to ${newTier.toUpperCase()}`,
      message: `${portName} risk status shifted from ${previousTier ? previousTier.toUpperCase() : 'UNKNOWN'} to ${newTier.toUpperCase()}.`,
      tier: newTier,
      previousTier,
      timestamp: new Date().toISOString(),
      read: false,
    };

    // Asynchronously notify backend server
    const base = (this.baseUrl !== undefined ? this.baseUrl : getApiBaseUrl()).replace(/\/+$/, '');
    fetch(`${base}/api/v1/notifications/alerts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: getAuthToken(),
      },
      body: JSON.stringify({
        portId,
        portName,
        newTier,
        previousTier,
      }),
    }).catch((err) => {
      console.warn('[Berthmark API] Failed to record alert on backend:', err);
    });

    return notif;
  }
}

export function createApiServices(baseUrl?: string): IServices {
  return {
    ports: new ApiPortService(baseUrl),
    risk: new ApiRiskService(baseUrl),
    notifications: new ApiNotificationService(baseUrl),
  };
}
