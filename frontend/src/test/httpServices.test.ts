import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  HttpPortService,
  HttpRiskService,
  HttpNotificationService,
  getServices,
  setServices,
  MockPortService,
} from '@/services';
import type { Port, RiskAssessment, Notification } from '@/types';

describe('Http Services', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('HttpPortService', () => {
    const service = new HttpPortService();

    it('getPorts sends GET /api/v1/ports', async () => {
      const mockPorts: Port[] = [
        {
          id: 'port-rotterdam',
          name: 'Port of Rotterdam',
          locode: 'NLRTM',
          country: 'Netherlands',
          lat: 51.95,
          lon: 4.13,
          isDefault: true,
          geofenceRadiusNm: 15,
          addedByUserId: null,
        },
      ];

      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/ports');
        return new Response(JSON.stringify(mockPorts), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const result = await service.getPorts();
      expect(result).toHaveLength(1);
      expect(result[0].locode).toBe('NLRTM');
    });

    it('getDefaultPorts sends GET /api/v1/ports/default', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/ports/default');
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const result = await service.getDefaultPorts();
      expect(result).toEqual([]);
    });

    it('searchPorts returns empty array without network request on empty or whitespace query', async () => {
      const fetchSpy = vi.fn();
      globalThis.fetch = fetchSpy;

      const res1 = await service.searchPorts('');
      const res2 = await service.searchPorts('   ');
      expect(res1).toEqual([]);
      expect(res2).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('searchPorts encodes query and queries /api/v1/ports/search', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/ports/search?q=Port%20of%20Rotterdam');
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const result = await service.searchPorts('Port of Rotterdam');
      expect(result).toEqual([]);
    });

    it('addPort sends POST /api/v1/ports with payload and returns created port', async () => {
      const newPort = {
        name: 'Port of Hamburg',
        locode: 'DEHAM',
        country: 'Germany',
        lat: 53.53,
        lon: 9.98,
        geofenceRadiusNm: 10,
      };

      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/ports');
        expect(init?.method).toBe('POST');
        expect(JSON.parse(init?.body as string)).toEqual(newPort);
        return new Response(
          JSON.stringify({ ...newPort, id: 'port-hamburg', isDefault: false, addedByUserId: 'usr-1' }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      });

      const created = await service.addPort(newPort);
      expect(created.id).toBe('port-hamburg');
      expect(created.locode).toBe('DEHAM');
    });

    it('removePort sends DELETE /api/v1/ports/{portId} and resolves on 204', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/ports/port-hamburg');
        expect(init?.method).toBe('DELETE');
        return new Response(null, { status: 204 });
      });

      await expect(service.removePort('port-hamburg')).resolves.toBeUndefined();
    });
  });

  describe('HttpRiskService', () => {
    const service = new HttpRiskService();

    it('getRiskAssessment requests GET /api/v1/ports/{portId}/risk with query parameters', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/ports/port-rotterdam/risk');
        expect(url).toContain('vesselClass=neoPanamax');
        expect(url).toContain('portName=Port+of+Rotterdam');
        return new Response(JSON.stringify({ id: 'risk-1', compositeTier: 'low' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const assessment = await service.getRiskAssessment(
        'port-rotterdam',
        'Port of Rotterdam',
        'neoPanamax'
      );
      expect(assessment.id).toBe('risk-1');
      expect(assessment.compositeTier).toBe('low');
    });

    it('getBulkRiskAssessments sends POST /api/v1/risk/assessments/bulk', async () => {
      const payload = {
        ports: [{ id: 'port-rotterdam', name: 'Rotterdam' }],
        vesselClass: 'ulcv' as const,
      };

      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/risk/assessments/bulk');
        expect(init?.method).toBe('POST');
        expect(JSON.parse(init?.body as string)).toEqual(payload);
        return new Response(JSON.stringify([{ id: 'risk-bulk-1' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const results = await service.getBulkRiskAssessments(payload.ports, payload.vesselClass);
      expect(results).toHaveLength(1);
    });

    it('getHistoricalTrend sends GET /api/v1/ports/{portId}/risk/history', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/ports/port-rotterdam/risk/history');
        expect(url).toContain('days=7');
        expect(url).toContain('vesselClass=capesize');
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const results = await service.getHistoricalTrend('port-rotterdam', 'capesize', 7);
      expect(results).toEqual([]);
    });
  });

  describe('HttpNotificationService', () => {
    const service = new HttpNotificationService();

    it('getNotifications queries GET /api/v1/notifications with query options', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url) => {
        expect(url).toContain('/api/v1/notifications?unreadOnly=true&limit=20');
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      });

      const results = await service.getNotifications(true, 20);
      expect(results).toEqual([]);
    });

    it('markAsRead sends PATCH /api/v1/notifications/{id}/read', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/notifications/notif-1/read');
        expect(init?.method).toBe('PATCH');
        return new Response(null, { status: 204 });
      });

      await expect(service.markAsRead('notif-1')).resolves.toBeUndefined();
    });

    it('markAllAsRead sends POST /api/v1/notifications/mark-all-read', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/notifications/mark-all-read');
        expect(init?.method).toBe('POST');
        return new Response(null, { status: 204 });
      });

      await expect(service.markAllAsRead()).resolves.toBeUndefined();
    });

    it('generateStateChangeAlert sends POST /api/v1/notifications', async () => {
      globalThis.fetch = vi.fn().mockImplementation(async (url, init) => {
        expect(url).toContain('/api/v1/notifications');
        expect(init?.method).toBe('POST');
        const body = JSON.parse(init?.body as string);
        expect(body.portId).toBe('port-1');
        expect(body.newTier).toBe('high');
        expect(body.previousTier).toBe('medium');
        return new Response(
          JSON.stringify({
            id: 'notif-alert-1',
            portId: 'port-1',
            portName: 'Rotterdam',
            tier: 'high',
            previousTier: 'medium',
            title: 'Rotterdam Risk State Change',
            message: 'Port Rotterdam transitioned to HIGH risk.',
            timestamp: new Date().toISOString(),
            read: false,
            type: 'stateChange',
          }),
          {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }
        );
      });

      const alert = await service.generateStateChangeAlert('port-1', 'Rotterdam', 'high', 'medium');
      expect(alert.id).toBe('notif-alert-1');
      expect(alert.tier).toBe('high');
    });
  });

  describe('Service Container getServices() and setServices()', () => {
    it('defaults to providing real HTTP services', () => {
      const services = getServices();
      expect(services.ports).toBeInstanceOf(HttpPortService);
      expect(services.risk).toBeInstanceOf(HttpRiskService);
      expect(services.notifications).toBeInstanceOf(HttpNotificationService);
    });

    it('allows mocking via setServices()', () => {
      const customMock = new MockPortService();
      setServices({
        ports: customMock,
        risk: new HttpRiskService(),
        notifications: new HttpNotificationService(),
      });

      expect(getServices().ports).toBe(customMock);

      // Restore
      setServices({
        ports: new HttpPortService(),
        risk: new HttpRiskService(),
        notifications: new HttpNotificationService(),
      });
    });
  });
});
