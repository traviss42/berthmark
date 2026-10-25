import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  httpClient,
  getBaseApiUrl,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
  onUnauthorized,
  AUTH_TOKEN_KEY,
  CustomApiError,
  isPublicEndpoint,
} from '@/services/httpClient';

describe('httpClient', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('resolves base API URL properly', () => {
    const url = getBaseApiUrl();
    expect(url).toBe('/api/v1');
  });

  it('correctly identifies public and protected endpoints', () => {
    expect(isPublicEndpoint('/auth/login')).toBe(true);
    expect(isPublicEndpoint('/ports/default')).toBe(true);
    expect(isPublicEndpoint('/ports/search?q=rotterdam')).toBe(true);
    expect(isPublicEndpoint('/vessel-classes')).toBe(true);
    expect(isPublicEndpoint('/ports')).toBe(false);
    expect(isPublicEndpoint('/notifications')).toBe(false);
    expect(isPublicEndpoint('/auth/me')).toBe(false);
  });

  it('stores and retrieves auth tokens in localStorage', () => {
    setStoredToken('test-jwt-token');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('test-jwt-token');
    expect(getStoredToken()).toBe('test-jwt-token');

    clearStoredToken();
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
    expect(getStoredToken()).toBeNull();
  });

  it('attaches Content-Type: application/json for POST and PATCH requests with payloads', async () => {
    let capturedHeaders: Headers | undefined;
    let capturedBody: any;

    globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
      capturedHeaders = init?.headers as Headers;
      capturedBody = init?.body;
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    const data = await httpClient.post<{ ok: boolean }>('/test', { foo: 'bar' });
    expect(data.ok).toBe(true);
    expect(capturedHeaders?.get('Content-Type')).toBe('application/json');
    expect(capturedBody).toBe(JSON.stringify({ foo: 'bar' }));
  });

  it('attaches Authorization Bearer token to protected requests when token is present', async () => {
    setStoredToken('mock-secret-token');
    let capturedHeaders: Headers | undefined;

    globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
      capturedHeaders = init?.headers as Headers;
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    await httpClient.get('/ports');
    expect(capturedHeaders?.get('Authorization')).toBe('Bearer mock-secret-token');
  });

  it('omits Authorization header for public endpoints even when token exists', async () => {
    setStoredToken('mock-secret-token');
    let capturedHeaders: Headers | undefined;

    globalThis.fetch = vi.fn().mockImplementation(async (_url, init) => {
      capturedHeaders = init?.headers as Headers;
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });

    await httpClient.get('/ports/default');
    expect(capturedHeaders?.get('Authorization')).toBeNull();
  });

  it('cleanly handles HTTP 204 No Content without JSON parsing errors', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      return new Response(null, {
        status: 204,
      });
    });

    const result = await httpClient.delete('/ports/port-rotterdam');
    expect(result).toBeUndefined();
  });

  it('rejects non-2xx responses with typed CustomApiError matching ErrorResponse schema', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      return new Response(
        JSON.stringify({
          error: 'BadRequest',
          message: 'Invalid vessel class provided.',
          statusCode: 400,
        }),
        {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    });

    await expect(httpClient.get('/ports/invalid/risk')).rejects.toThrow(
      'Invalid vessel class provided.'
    );

    try {
      await httpClient.get('/ports/invalid/risk');
    } catch (e: any) {
      expect(e).toBeInstanceOf(CustomApiError);
      expect(e.error).toBe('BadRequest');
      expect(e.message).toBe('Invalid vessel class provided.');
      expect(e.statusCode).toBe(400);
    }
  });

  it('clears stored token and triggers onUnauthorized callback when protected call returns 401', async () => {
    setStoredToken('expired-token');
    const unauthorizedSpy = vi.fn();
    const unsubscribe = onUnauthorized(unauthorizedSpy);

    globalThis.fetch = vi.fn().mockImplementation(async () => {
      return new Response(
        JSON.stringify({
          error: 'Unauthorized',
          message: 'Could not validate credentials.',
          statusCode: 401,
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    });

    await expect(httpClient.get('/ports')).rejects.toThrow();

    expect(getStoredToken()).toBeNull();
    expect(unauthorizedSpy).toHaveBeenCalledTimes(1);

    unsubscribe();
  });
});
