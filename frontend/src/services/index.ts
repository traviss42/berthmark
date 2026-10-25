import type { IServices } from '@/services/interfaces';
import { HttpPortService } from '@/services/httpPortService';
import { HttpRiskService } from '@/services/httpRiskService';
import { HttpNotificationService } from '@/services/httpNotificationService';

// ── Service container ──
// Centralizes all backend calls. The app imports from here.
// Defaults to real HTTP services, while setServices() allows mock injection.

let current: IServices | null = null;

export function getServices(): IServices {
  if (!current) {
    current = {
      ports: new HttpPortService(),
      risk: new HttpRiskService(),
      notifications: new HttpNotificationService(),
    };
  }
  return current;
}

export function setServices(services: IServices): void {
  current = services;
}

export { HttpPortService } from '@/services/httpPortService';
export { HttpRiskService } from '@/services/httpRiskService';
export { HttpNotificationService } from '@/services/httpNotificationService';
export { MockPortService } from '@/services/mockPortService';
export { MockRiskService } from '@/services/mockRiskService';
export { MockNotificationService } from '@/services/mockNotificationService';
export { httpClient, AUTH_TOKEN_KEY } from '@/services/httpClient';
export { authService, AuthService } from '@/services/authService';

export type { IServices } from '@/services/interfaces';
export type {
  IPortService,
  IRiskService,
  INotificationService,
} from '@/services/interfaces';
