import type { IServices } from '@/services/interfaces';
import {
  createApiServices,
  ApiPortService,
  ApiRiskService,
  ApiNotificationService,
} from '@/services/apiServices';

// ── Service container ──
// Connects exclusively to the real FastAPI backend REST API (/api/v1) backed by
// live UN/LOCODE SQLite database, Open-Meteo Marine/Forecast, and AISStream WebSocket.

let current: IServices | null = null;

export function getServices(): IServices {
  if (!current) {
    current = createApiServices();
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
};

export type { IServices } from '@/services/interfaces';
export type {
  IPortService,
  IRiskService,
  INotificationService,
} from '@/services/interfaces';
