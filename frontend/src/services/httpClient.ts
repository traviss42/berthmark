import type { ApiError, ErrorResponse } from '@/types';

export const AUTH_TOKEN_KEY = 'berthmark_auth_token';

type UnauthorizedListener = () => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

export function notifyUnauthorized(): void {
  unauthorizedListeners.forEach((listener) => {
    try {
      listener();
    } catch (e) {
      console.error('Error in unauthorized listener:', e);
    }
  });
}

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // Ignore localStorage access errors
  }
}

export function clearStoredToken(): void {
  setStoredToken(null);
}

export function getBaseApiUrl(): string {
  const envUrl = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  if (envUrl) {
    return envUrl.endsWith('/') ? envUrl.slice(0, -1) : envUrl;
  }
  return '/api/v1';
}

export class CustomApiError extends Error implements ApiError {
  error: string;
  statusCode: number;

  constructor(message: string, error: string, statusCode: number) {
    super(message);
    this.name = 'CustomApiError';
    this.error = error;
    this.statusCode = statusCode;
  }
}

export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
}

const PUBLIC_ENDPOINT_PREFIXES = [
  '/auth/login',
  '/ports/default',
  '/ports/search',
  '/vessel-classes',
  '/health',
];

export function isPublicEndpoint(path: string): boolean {
  // Normalize path by stripping query params
  const cleanPath = path.split('?')[0];
  return PUBLIC_ENDPOINT_PREFIXES.some(
    (prefix) => cleanPath === prefix || cleanPath.startsWith(`${prefix}/`)
  );
}

export async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const baseUrl = getBaseApiUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = `${baseUrl}${normalizedPath}`;

  const headers = new Headers(options.headers || {});

  const method = (options.method || 'GET').toUpperCase();
  const isPostOrPatch = ['POST', 'PATCH', 'PUT'].includes(method);

  if (isPostOrPatch && !headers.has('Content-Type') && options.body && typeof options.body === 'string') {
    headers.set('Content-Type', 'application/json');
  }

  // Request interceptor: attach Authorization header if not public and token available
  const isPublic = options.skipAuth || isPublicEndpoint(normalizedPath);
  const token = getStoredToken();

  if (!isPublic && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    method,
    headers,
  });

  // Response interceptor: Handle 401 Unauthorized for protected endpoints
  if (response.status === 401 && !isPublic) {
    clearStoredToken();
    notifyUnauthorized();
  }

  // Check status
  if (!response.ok) {
    let errorCategory = response.statusText || 'Error';
    let errorMessage = `HTTP Error ${response.status}`;

    try {
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        const errorData = (await response.json()) as Partial<ErrorResponse>;
        if (errorData) {
          if (errorData.error) errorCategory = errorData.error;
          if (errorData.message) errorMessage = errorData.message;
        }
      } else {
        const text = await response.text();
        if (text) errorMessage = text;
      }
    } catch {
      // Fallback to defaults
    }

    throw new CustomApiError(errorMessage, errorCategory, response.status);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as unknown as T;
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    const text = await response.text();
    if (!text || !text.trim()) {
      return undefined as unknown as T;
    }
    return JSON.parse(text) as T;
  }

  return (await response.text()) as unknown as T;
}

export const httpClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'GET' });
  },

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });
  },

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });
  },

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: 'DELETE' });
  },
};
