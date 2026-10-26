import type { AuthResponse, LoginRequest, RegisterRequest, User } from '@/types';
import { httpClient } from './httpClient';

export class AuthService {
  async register(data: RegisterRequest): Promise<AuthResponse> {
    return httpClient.post<AuthResponse>('/auth/register', data, {
      skipAuth: true,
    });
  }

  async login(credentials: LoginRequest): Promise<AuthResponse> {
    return httpClient.post<AuthResponse>('/auth/login', credentials, {
      skipAuth: true,
    });
  }

  async getCurrentUser(): Promise<User> {
    return httpClient.get<User>('/auth/me');
  }
}

export const authService = new AuthService();
