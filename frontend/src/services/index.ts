import type { IServices } from '@/services/interfaces';
import { createApiServices, ApiPortService, ApiRiskService, ApiNotificationService } from '@/services/apiServices';
import { MockPortService } from '@/services/mockPortService';
import { MockRiskService } from '@/services/mockRiskService';
import { MockNotificationService } from '@/services/mockNotificationService';

// ── Service container ──
// Connects to the FastAPI backend REST API (/api/v1).
// To use mock services in offline tests or demos, set VITE_USE_MOCK_SERVICES=true
// or call setServices(createMockServices()).

let current: IServices | null = null;

export function createMockServices(): IServices {
  return {
    ports: new MockPortService(),
    risk: new MockRiskService(),
    notifications: new MockNotificationService(),
  };
}

export function getServices(): IServices {
  if (!current) {
    const useMocks =
      typeof import.meta !== 'undefined' &&
      import.meta.env?.VITE_USE_MOCK_SERVICES === 'true';

    current = useMocks ? createMockServices() : createApiServices();
  }
  return current;
}

export function setServices(services: IServices): void {
  current = services;
}

export {
  createApiServices,
  ApiPortService,
  ApiRiskService,
  ApiNotificationService,
  MockPortService,
  MockRiskService,
  MockNotificationService,
};

export type { IServices } from '@/services/interfaces';
export type {
  IPortService,
  IRiskService,
  INotificationService,
} from '@/services/interfaces';
