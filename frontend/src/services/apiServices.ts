import type {
  Port,
  RiskAssessment,
  Notification,
  VesselClass,
  RiskTier,
  User,
  AuthResponse,
  StreamStatus,
} from '@/types';
import type {
  IPortService,
  IRiskService,
  INotificationService,
  IAuthService,
  ISystemService,
  IServices,
} from '@/services/interfaces';

export const DEFAULT_API_URL = '';

export function getApiBaseUrl(): string {
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, '');
  }
  return DEFAULT_API_URL;
}

let currentAuthToken: string | null = null;

export function setAuthToken(token: string | null): void {
  currentAuthToken = token;
}

export function getAuthToken(userId?: string): string {
  if (userId) {
    return `Bearer ${userId}`;
  }
  if (currentAuthToken) {
    return `Bearer ${currentAuthToken}`;
  }
  return 'Bearer mock-user';
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
  private searchCache = new Map<string, { timestamp: number; results: Port[] }>();
  private readonly searchCacheTtlMs = 300000; // 5 minutes

  constructor(private baseUrl?: string) {}

  async getPorts(userId: string, vesselClass?: VesselClass): Promise<Port[]> {
    const path = vesselClass
      ? `/api/v1/ports?vesselClass=${encodeURIComponent(vesselClass)}`
      : '/api/v1/ports';
    return request<Port[]>(path, { method: 'GET' }, this.baseUrl, userId);
  }

  async getDefaultPorts(): Promise<Port[]> {
    return request<Port[]>('/api/v1/ports/defaults', { method: 'GET' }, this.baseUrl);
  }

  async searchPorts(query: string): Promise<Port[]> {
    const q = query.trim();
    if (!q) {
      return [];
    }

    const cacheKey = q.toLowerCase();
    const cached = this.searchCache.get(cacheKey);
    const now = Date.now();
    if (cached && now - cached.timestamp < this.searchCacheTtlMs) {
      return cached.results;
    }

    const results = await request<Port[]>(
      `/api/v1/ports/search?q=${encodeURIComponent(q)}`,
      { method: 'GET' },
      this.baseUrl
    );

    this.searchCache.set(cacheKey, { timestamp: now, results });
    return results;
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

  async updatePortNotifications(
    portId: string,
    notificationsEnabled: boolean,
    userId?: string
  ): Promise<Port> {
    return request<Port>(
      `/api/v1/ports/${encodeURIComponent(portId)}/notifications`,
      {
        method: 'PATCH',
        body: JSON.stringify({ notificationsEnabled }),
      },
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
    vesselClass: VesselClass,
    forceRefresh: boolean = false
  ): Promise<RiskAssessment> {
    const params: Record<string, string> = { vesselClass };
    if (portName) params.portName = portName;
    if (forceRefresh) params.forceRefresh = 'true';

    const query = new URLSearchParams(params);
    return request<RiskAssessment>(
      `/api/v1/ports/${encodeURIComponent(portId)}/risk?${query.toString()}`,
      { method: 'GET' },
      this.baseUrl
    );
  }

  async getBulkRiskAssessments(
    ports: { id: string; name: string; vesselClass?: VesselClass }[],
    vesselClass: VesselClass,
    forceRefresh: boolean = false
  ): Promise<RiskAssessment[]> {
    if (ports.length === 0) {
      return [];
    }
    const body: {
      ports: { id: string; name: string; vesselClass?: VesselClass }[];
      vesselClass: VesselClass;
      forceRefresh?: boolean;
    } = {
      ports,
      vesselClass,
    };
    if (forceRefresh) {
      body.forceRefresh = true;
    }
    return request<RiskAssessment[]>(
      '/api/v1/risk/bulk-assessments',
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      this.baseUrl
    );
  }

  async getHistoricalTrend(
    portId: string,
    vesselClass: VesselClass,
    days: number,
    forceRefresh: boolean = false
  ): Promise<RiskAssessment[]> {
    const params: Record<string, string> = {
      vesselClass,
      days: String(days),
    };
    if (forceRefresh) params.forceRefresh = 'true';

    const query = new URLSearchParams(params);
    return request<RiskAssessment[]>(
      `/api/v1/ports/${encodeURIComponent(portId)}/risk/trend?${query.toString()}`,
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

export class ApiAuthService implements IAuthService {
  constructor(private baseUrl?: string) {}

  async login(email: string, password?: string): Promise<AuthResponse> {
    const data = await request<AuthResponse>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      },
      this.baseUrl
    );
    setAuthToken(data.accessToken);
    return data;
  }

  async getCurrentUser(token?: string): Promise<User> {
    return request<User>(
      '/api/v1/auth/me',
      { method: 'GET' },
      this.baseUrl,
      token
    );
  }

  async logout(): Promise<void> {
    await request<void>(
      '/api/v1/auth/logout',
      { method: 'POST' },
      this.baseUrl
    ).catch(() => {});
    setAuthToken(null);
  }
}

export class ApiSystemService implements ISystemService {
  constructor(private baseUrl?: string) {}

  async getStreamStatus(): Promise<StreamStatus> {
    return request<StreamStatus>(
      '/api/v1/system/stream-status',
      { method: 'GET' },
      this.baseUrl
    );
  }
}

export function createApiServices(baseUrl?: string): IServices {
  return {
    ports: new ApiPortService(baseUrl),
    risk: new ApiRiskService(baseUrl),
    notifications: new ApiNotificationService(baseUrl),
    auth: new ApiAuthService(baseUrl),
    system: new ApiSystemService(baseUrl),
  };
}
