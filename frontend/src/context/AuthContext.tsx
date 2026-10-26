import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from 'react';
import type { User, LoginRequest, AuthResponse } from '@/types';
import {
  AUTH_TOKEN_KEY,
  getStoredToken,
  setStoredToken,
  clearStoredToken,
  onUnauthorized,
} from '@/services/httpClient';
import { authService } from '@/services/authService';

export interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (name: string, email: string, password: string) => Promise<AuthResponse>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export interface AuthProviderProps {
  children: React.ReactNode;
}

const USER_STORAGE_KEY = 'berthmark_user';

const getStoredUser = (): User | null => {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(() => getStoredToken());
  const [user, setUser] = useState<User | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => !!getStoredToken());
  const [loading, setLoading] = useState<boolean>(() => !!getStoredToken() && !getStoredUser());
  const [error, setError] = useState<string | null>(null);

  // Logout handler
  const logout = useCallback(() => {
    clearStoredToken();
    try {
      localStorage.removeItem(USER_STORAGE_KEY);
    } catch {
      // ignore storage errors
    }
    setTokenState(null);
    setUser(null);
    setIsAuthenticated(false);
    setError(null);
  }, []);

  // Hydrate user on mount if token is present
  useEffect(() => {
    let isMounted = true;
    const initialToken = getStoredToken();

    if (!initialToken) {
      setLoading(false);
      return;
    }

    setTokenState(initialToken);

    authService
      .getCurrentUser()
      .then((userData) => {
        if (!isMounted) return;
        try {
          localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
        } catch {
          // ignore storage errors
        }
        setUser(userData);
        setIsAuthenticated(true);
      })
      .catch(() => {
        if (!isMounted) return;
        // If 401 or network failure, clear token and mark unauthenticated
        clearStoredToken();
        try {
          localStorage.removeItem(USER_STORAGE_KEY);
        } catch {
          // ignore
        }
        setTokenState(null);
        setUser(null);
        setIsAuthenticated(false);
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Listen for 401 unauthorized notifications from HTTP client interceptor
  useEffect(() => {
    const unsubscribe = onUnauthorized(() => {
      logout();
    });
    return unsubscribe;
  }, [logout]);

  // Login action
  const login = useCallback(
    async (email: string, password: string): Promise<AuthResponse> => {
      setLoading(true);
      setError(null);
      try {
        const authData = await authService.login({ email, password });
        setStoredToken(authData.accessToken);
        setTokenState(authData.accessToken);
        try {
          localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(authData.user));
        } catch {
          // ignore
        }
        setUser(authData.user);
        setIsAuthenticated(true);
        return authData;
      } catch (err: unknown) {
        let msg = 'Invalid email or password';
        if (err && typeof err === 'object' && 'message' in err && typeof (err as any).message === 'string') {
          msg = (err as any).message;
        }
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Register action
  const register = useCallback(
    async (name: string, email: string, password: string): Promise<AuthResponse> => {
      setLoading(true);
      setError(null);
      try {
        const authData = await authService.register({ name, email, password });
        setStoredToken(authData.accessToken);
        setTokenState(authData.accessToken);
        try {
          localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(authData.user));
        } catch {
          // ignore
        }
        setUser(authData.user);
        setIsAuthenticated(true);
        return authData;
      } catch (err: unknown) {
        let msg = 'Registration failed';
        if (err && typeof err === 'object' && 'message' in err && typeof (err as any).message === 'string') {
          msg = (err as any).message;
        }
        setError(msg);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const value: AuthContextType = {
    user,
    token,
    isAuthenticated,
    loading,
    error,
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
