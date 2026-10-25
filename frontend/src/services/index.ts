import type { IServices } from '@/services/interfaces';
import { MockPortService } from '@/services/mockPortService';
import { MockRiskService } from '@/services/mockRiskService';
import { MockNotificationService } from '@/services/mockNotificationService';

// ── Service container ──
// Centralizes all backend calls. The app imports from here only.
// Swap mock implementations for real ones by changing this factory.

let current: IServices | null = null;

export function getServices(): IServices {
  if (!current) {
    current = {
      ports: new MockPortService(),
      risk: new MockRiskService(),
      notifications: new MockNotificationService(),
    };
  }
  return current;
}

export function setServices(services: IServices): void {
  current = services;
}

export type { IServices } from '@/services/interfaces';
export type {
  IPortService,
  IRiskService,
  INotificationService,
} from '@/services/interfaces';
