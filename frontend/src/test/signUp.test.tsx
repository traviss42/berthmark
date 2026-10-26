import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider } from '@/context/AuthContext';
import { SignUpForm } from '@/components/SignUpForm';
import { LoginForm } from '@/components/LoginForm';
import App from '@/App';
import { AUTH_TOKEN_KEY } from '@/services/httpClient';

describe('Self-Service User Registration and /signup Route', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    window.history.pushState({}, '', '/');
  });

  describe('SignUpForm Component', () => {
    it('renders all form fields, labels, placeholders, and action buttons', () => {
      const handleSwitch = vi.fn();
      render(
        <AuthProvider>
          <SignUpForm onSwitchToLogin={handleSwitch} />
        </AuthProvider>
      );

      expect(screen.getByText('Create Berthmark Account')).toBeInTheDocument();
      expect(screen.getByTestId('signup-name')).toBeInTheDocument();
      expect(screen.getByTestId('signup-email')).toBeInTheDocument();
      expect(screen.getByTestId('signup-password')).toBeInTheDocument();
      expect(screen.getByTestId('signup-submit')).toBeInTheDocument();
      expect(screen.getByTestId('switch-to-login')).toBeInTheDocument();

      fireEvent.click(screen.getByTestId('switch-to-login'));
      expect(handleSwitch).toHaveBeenCalledTimes(1);
    });

    it('enforces client-side validation when email or password is missing', async () => {
      render(
        <AuthProvider>
          <SignUpForm />
        </AuthProvider>
      );

      fireEvent.click(screen.getByTestId('signup-submit'));

      expect(
        await screen.findByText(/Please enter both email and password/i)
      ).toBeInTheDocument();
    });

    it('successfully registers user, persists token, and triggers onSuccess callback', async () => {
      const onSuccessMock = vi.fn();

      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        if (url.toString().includes('/auth/register')) {
          return new Response(
            JSON.stringify({
              accessToken: 'mocked-jwt-token-777',
              tokenType: 'Bearer',
              user: {
                id: 'usr-fresh-001',
                email: 'firstmate@shipper.org',
                name: 'First Mate Henderson',
              },
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (url.toString().includes('/auth/me')) {
          return new Response(
            JSON.stringify({
              id: 'usr-fresh-001',
              email: 'firstmate@shipper.org',
              name: 'First Mate Henderson',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(null, { status: 404 });
      });

      render(
        <AuthProvider>
          <SignUpForm onSuccess={onSuccessMock} />
        </AuthProvider>
      );

      fireEvent.change(screen.getByTestId('signup-name'), {
        target: { value: 'First Mate Henderson' },
      });
      fireEvent.change(screen.getByTestId('signup-email'), {
        target: { value: 'firstmate@shipper.org' },
      });
      fireEvent.change(screen.getByTestId('signup-password'), {
        target: { value: 'SuperSecureVoyage2026!' },
      });

      fireEvent.click(screen.getByTestId('signup-submit'));

      await waitFor(() => {
        expect(onSuccessMock).toHaveBeenCalledTimes(1);
      });

      expect(localStorage.getItem(AUTH_TOKEN_KEY)).toBe('mocked-jwt-token-777');
    });

    it('displays 409 conflict error when email is already registered', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        if (url.toString().includes('/auth/register')) {
          return new Response(
            JSON.stringify({
              error: 'Conflict',
              message: "User with email 'firstmate@shipper.org' already exists.",
              statusCode: 409,
            }),
            { status: 409, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(null, { status: 404 });
      });

      render(
        <AuthProvider>
          <SignUpForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByTestId('signup-email'), {
        target: { value: 'firstmate@shipper.org' },
      });
      fireEvent.change(screen.getByTestId('signup-password'), {
        target: { value: 'ValidPassword123' },
      });

      fireEvent.click(screen.getByTestId('signup-submit'));

      expect(
        await screen.findByText(/already exists/i)
      ).toBeInTheDocument();
    });

    it('displays connectivity error alert on 500 server error or network exception', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        throw new Error('Connection refused');
      });

      render(
        <AuthProvider>
          <SignUpForm />
        </AuthProvider>
      );

      fireEvent.change(screen.getByTestId('signup-email'), {
        target: { value: 'navigator@sea.com' },
      });
      fireEvent.change(screen.getByTestId('signup-password'), {
        target: { value: 'ValidPassword123' },
      });

      fireEvent.click(screen.getByTestId('signup-submit'));

      expect(
        await screen.findByText(/Connectivity failure. Unable to reach server./i)
      ).toBeInTheDocument();
    });
  });

  describe('LoginForm with SignUp Link', () => {
    it('renders switch to sign up link when onSwitchToSignUp is supplied', () => {
      const handleSwitch = vi.fn();
      render(
        <AuthProvider>
          <LoginForm onSwitchToSignUp={handleSwitch} />
        </AuthProvider>
      );

      const signUpLink = screen.getByTestId('switch-to-signup');
      expect(signUpLink).toBeInTheDocument();
      fireEvent.click(signUpLink);
      expect(handleSwitch).toHaveBeenCalledTimes(1);
    });
  });

  describe('App Routing with /signup Route', () => {
    it('renders SignUpForm directly when browser URL path is /signup', async () => {
      window.history.pushState({}, '', '/signup');

      render(<App />);

      expect(screen.getByText('Create Berthmark Account')).toBeInTheDocument();
      expect(screen.getByTestId('signup-email')).toBeInTheDocument();
    });

    it('navigates from header Sign Up button to /signup', async () => {
      window.history.pushState({}, '', '/');

      render(<App />);

      const signUpBtn = screen.getByTestId('header-signup-btn');
      expect(signUpBtn).toBeInTheDocument();

      fireEvent.click(signUpBtn);

      expect(window.location.pathname).toBe('/signup');
      expect(screen.getByText('Create Berthmark Account')).toBeInTheDocument();
    });

    it('lands newly registered user on the dashboard with user display in header', async () => {
      window.history.pushState({}, '', '/signup');

      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        if (url.toString().includes('/auth/register')) {
          return new Response(
            JSON.stringify({
              accessToken: 'freshly-minted-token',
              tokenType: 'Bearer',
              user: {
                id: 'usr-new-registered',
                email: 'admiral@navy.gov',
                name: 'Admiral Nelson',
              },
            }),
            { status: 201, headers: { 'Content-Type': 'application/json' } }
          );
        }
        if (url.toString().includes('/auth/me')) {
          return new Response(
            JSON.stringify({
              id: 'usr-new-registered',
              email: 'admiral@navy.gov',
              name: 'Admiral Nelson',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } }
          );
        }
        return new Response(null, { status: 404 });
      });

      render(<App />);

      expect(screen.getByText('Create Berthmark Account')).toBeInTheDocument();

      fireEvent.change(screen.getByTestId('signup-name'), {
        target: { value: 'Admiral Nelson' },
      });
      fireEvent.change(screen.getByTestId('signup-email'), {
        target: { value: 'admiral@navy.gov' },
      });
      fireEvent.change(screen.getByTestId('signup-password'), {
        target: { value: 'Trafalgar1805!' },
      });

      fireEvent.click(screen.getByTestId('signup-submit'));

      await waitFor(() => {
        expect(window.location.pathname).toBe('/');
      });

      await waitFor(() => {
        expect(screen.getByTestId('user-display')).toHaveTextContent('Admiral Nelson');
      });
    });
  });
});
