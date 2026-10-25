import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { LoginForm } from '@/components/LoginForm';
import { AUTH_TOKEN_KEY } from '@/services/httpClient';

function TestConsumer() {
  const { user, token, isAuthenticated, loading, error, login, logout } = useAuth();

  return (
    <div>
      <div data-testid="auth-status">{isAuthenticated ? 'AUTHENTICATED' : 'ANONYMOUS'}</div>
      <div data-testid="loading-status">{loading ? 'LOADING' : 'READY'}</div>
      <div data-testid="user-email">{user?.email || 'NO_USER'}</div>
      <div data-testid="token-val">{token || 'NO_TOKEN'}</div>
      <div data-testid="error-val">{error || 'NO_ERROR'}</div>
      <button onClick={() => login('operator@maritimerisk.com', 'SampleSecurePassword123!')}>
        Trigger Login
      </button>
      <button onClick={logout}>Trigger Logout</button>
    </div>
  );
}

describe('AuthContext and LoginForm', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('initializes with unauthenticated state when no token in localStorage', async () => {
    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId('auth-status').textContent).toBe('ANONYMOUS');
    expect(screen.getByTestId('loading-status').textContent).toBe('READY');
    expect(screen.getByTestId('user-email').textContent).toBe('NO_USER');
  });

  it('hydrates user profile on mount if token is found in localStorage', async () => {
    localStorage.setItem(AUTH_TOKEN_KEY, 'valid-token-123');

    globalThis.fetch = vi.fn().mockImplementation(async (url) => {
      if (url.toString().includes('/auth/me')) {
        return new Response(
          JSON.stringify({
            id: 'usr-001',
            email: 'operator@maritimerisk.com',
            name: 'Ship Operations Manager',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(null, { status: 404 });
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status').textContent).toBe('AUTHENTICATED');
    });

    expect(screen.getByTestId('user-email').textContent).toBe('operator@maritimerisk.com');
  });

  it('clears token if initial profile hydration fails with 401', async () => {
    localStorage.setItem(AUTH_TOKEN_KEY, 'expired-token');

    globalThis.fetch = vi.fn().mockImplementation(async (url) => {
      if (url.toString().includes('/auth/me')) {
        return new Response(
          JSON.stringify({
            error: 'Unauthorized',
            message: 'Invalid token',
            statusCode: 401,
          }),
          { status: 401, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(null, { status: 404 });
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading-status').textContent).toBe('READY');
    });

    expect(screen.getByTestId('auth-status').textContent).toBe('ANONYMOUS');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });

  it('login saves token to localStorage and authenticates', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url) => {
      if (url.toString().includes('/auth/login')) {
        return new Response(
          JSON.stringify({
            accessToken: 'new-jwt-token-xyz',
            tokenType: 'Bearer',
            user: {
              id: 'usr-999',
              email: 'operator@maritimerisk.com',
              name: 'Ship Operations Manager',
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(null, { status: 404 });
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    fireEvent.click(screen.getByText('Trigger Login'));

    await waitFor(() => {
      expect(screen.getByTestId('auth-status').textContent).toBe('AUTHENTICATED');
    });

    expect(screen.getByTestId('token-val').textContent).toBe('new-jwt-token-xyz');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('new-jwt-token-xyz');

    // Test logout
    fireEvent.click(screen.getByText('Trigger Logout'));
    expect(screen.getByTestId('auth-status').textContent).toBe('ANONYMOUS');
    expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBeNull();
  });

  it('LoginForm renders inputs and client-side validation', async () => {
    render(
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    );

    const emailInput = screen.getByLabelText(/Email address/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    const submitBtn = screen.getByRole('button', { name: /Sign In/i });

    expect(emailInput).toBeInTheDocument();
    expect(passwordInput).toBeInTheDocument();

    // Click submit with empty fields
    fireEvent.click(submitBtn);

    expect(
      await screen.findByText(/Please enter both email and password/i)
    ).toBeInTheDocument();
  });

  it('LoginForm displays 401 error message when credentials are invalid', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async (url) => {
      if (url.toString().includes('/auth/login')) {
        return new Response(
          JSON.stringify({
            error: 'Unauthorized',
            message: 'Invalid credentials.',
            statusCode: 401,
          }),
          { status: 401, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(null, { status: 404 });
    });

    render(
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    );

    fireEvent.change(screen.getByLabelText(/Email address/i), {
      target: { value: 'bad@operator.com' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'wrongpassword' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    expect(await screen.findByText(/Invalid credentials/i)).toBeInTheDocument();
  });

  it('LoginForm displays connectivity failure when network or 500 error occurs', async () => {
    globalThis.fetch = vi.fn().mockImplementation(async () => {
      throw new Error('Network error');
    });

    render(
      <AuthProvider>
        <LoginForm />
      </AuthProvider>
    );

    fireEvent.change(screen.getByLabelText(/Email address/i), {
      target: { value: 'operator@maritimerisk.com' },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));

    expect(
      await screen.findByText(/Connectivity failure. Unable to reach server./i)
    ).toBeInTheDocument();
  });
});
