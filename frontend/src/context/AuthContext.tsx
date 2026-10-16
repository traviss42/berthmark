import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { User } from '@/types';
import { getServices } from '@/services';
import { setAuthToken } from '@/services/apiServices';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const USER_STORAGE_KEY = 'berthmark_auth_user';
const TOKEN_STORAGE_KEY = 'berthmark_auth_token';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const services = getServices();

  useEffect(() => {
    try {
      const storedUser = localStorage.getItem(USER_STORAGE_KEY);
      const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (storedUser && storedToken) {
        const parsed = JSON.parse(storedUser);
        setUser(parsed);
        setAuthToken(storedToken);
      }
    } catch {
      // Ignore parse errors
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(
    async (email: string, password?: string) => {
      setLoading(true);
      try {
        const res = await services.auth.login(email, password);
        setUser(res.user);
        setAuthToken(res.accessToken);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(res.user));
        localStorage.setItem(TOKEN_STORAGE_KEY, res.accessToken);
      } finally {
        setLoading(false);
      }
    },
    [services]
  );

  const logout = useCallback(async () => {
    try {
      await services.auth.logout();
    } finally {
      setUser(null);
      setAuthToken(null);
      localStorage.removeItem(USER_STORAGE_KEY);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }, [services]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
