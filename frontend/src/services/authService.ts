import type { AuthResponse, LoginRequest, User } from '@/types';
import { httpClient } from './httpClient';

export class AuthService {
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
