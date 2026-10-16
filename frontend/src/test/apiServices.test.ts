import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  ApiPortService,
  ApiRiskService,
  ApiNotificationService,
  ApiError,
  createApiServices,
} from '@/services/apiServices';
import type { Port, RiskAssessment, Notification } from '@/types';

describe('ApiPortService', () => {
  let service: ApiPortService;
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    service = new ApiPortService('http://test-api:8000');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getPorts fetches /api/v1/ports with user auth header', async () => {
    const mockPorts: Port[] = [
      {
        id: 'port-1',
        name: 'Port of Rotterdam',
        locode: 'NLRTM',
        country: 'Netherlands',
        lat: 51.9,
        lon: 4.4,
        isDefault: true,
        geofenceRadiusNm: 8,
        addedByUserId: null,
      },
    ];

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockPorts,
    });

    const ports = await service.getPorts('user-123');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/ports',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer user-123',
        }),
      })
    );
    expect(ports).toEqual(mockPorts);
  });

  it('searchPorts fetches /api/v1/ports/search?q=query', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [{ id: 'port-rotterdam', name: 'Port of Rotterdam' }],
    });

    const results = await service.searchPorts('Rotterdam');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/ports/search?q=Rotterdam',
      expect.objectContaining({ method: 'GET' })
    );
    expect(results).toHaveLength(1);
  });

  it('searchPorts returns empty array without network call when query is blank', async () => {
    const results = await service.searchPorts('   ');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(results).toEqual([]);
  });

  it('addPort posts to /api/v1/ports with port body', async () => {
    const newPort = {
      name: 'Custom Port',
      locode: 'XXCST',
      country: 'TestCountry',
      lat: 10,
      lon: 20,
      geofenceRadiusNm: 6,
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ ...newPort, id: 'port-new', isDefault: false, addedByUserId: 'user-1' }),
    });

    const created = await service.addPort(newPort, 'user-1');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/ports',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(newPort),
        headers: expect.objectContaining({
          Authorization: 'Bearer user-1',
        }),
      })
    );
    expect(created.id).toBe('port-new');
  });

  it('removePort sends DELETE to /api/v1/ports/{portId}', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
    });

    await service.removePort('port-custom-1', 'user-1');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/ports/port-custom-1',
      expect.objectContaining({
        method: 'DELETE',
        headers: expect.objectContaining({
          Authorization: 'Bearer user-1',
        }),
      })
    );
  });

  it('throws ApiError on HTTP error status', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 409,
      statusText: 'Conflict',
      json: async () => ({ detail: 'Port already exists' }),
    });

    await expect(
      service.addPort(
        { name: 'Duplicate', locode: 'NLRTM', country: 'NL', lat: 0, lon: 0, geofenceRadiusNm: 5 },
        'user-1'
      )
    ).rejects.toThrow('Port already exists');
  });
});

describe('ApiRiskService', () => {
  let service: ApiRiskService;
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    service = new ApiRiskService('http://test-api:8000');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getRiskAssessment requests /api/v1/ports/{id}/risk with vesselClass and portName', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 'risk-1', compositeTier: 'low' }),
    });

    const res = await service.getRiskAssessment('port-rotterdam', 'Port of Rotterdam', 'neoPanamax');

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ports/port-rotterdam/risk?'),
      expect.objectContaining({ method: 'GET' })
    );
    expect(res.compositeTier).toBe('low');
  });

  it('getBulkRiskAssessments posts to /api/v1/risk/bulk-assessments', async () => {
    const mockList = [{ id: 'risk-1' }, { id: 'risk-2' }];
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockList,
    });

    const res = await service.getBulkRiskAssessments(
      [{ id: 'p1', name: 'Port 1' }, { id: 'p2', name: 'Port 2' }],
      'vlcc'
    );

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/risk/bulk-assessments',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          ports: [{ id: 'p1', name: 'Port 1' }, { id: 'p2', name: 'Port 2' }],
          vesselClass: 'vlcc',
        }),
      })
    );
    expect(res).toHaveLength(2);
  });

  it('getBulkRiskAssessments returns empty array if ports array is empty', async () => {
    const res = await service.getBulkRiskAssessments([], 'feeder');
    expect(mockFetch).not.toHaveBeenCalled();
    expect(res).toEqual([]);
  });
});

describe('ApiNotificationService', () => {
  let service: ApiNotificationService;
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch);
    service = new ApiNotificationService('http://test-api:8000');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getNotifications fetches /api/v1/notifications', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => [],
    });

    const res = await service.getNotifications('user-1');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/notifications',
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer user-1',
        }),
      })
    );
    expect(res).toEqual([]);
  });

  it('markAsRead sends PATCH to /api/v1/notifications/{id}/read', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: 'notif-1', read: true }),
    });

    await service.markAsRead('notif-1');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/notifications/notif-1/read',
      expect.objectContaining({ method: 'PATCH' })
    );
  });

  it('markAllAsRead sends POST to /api/v1/notifications/mark-all-read', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
    });

    await service.markAllAsRead('user-1');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/notifications/mark-all-read',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer user-1',
        }),
      })
    );
  });

  it('generateStateChangeAlert returns notification immediately and async posts alert', () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({}),
    });

    const notif = service.generateStateChangeAlert('port-1', 'Port of Rotterdam', 'high', 'medium');

    expect(notif.portId).toBe('port-1');
    expect(notif.tier).toBe('high');
    expect(notif.previousTier).toBe('medium');
    expect(notif.read).toBe(false);

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api:8000/api/v1/notifications/alerts',
      expect.objectContaining({
        method: 'POST',
      })
    );
  });
});

describe('createApiServices factory', () => {
  it('instantiates all required services with API implementations', () => {
    const services = createApiServices('http://localhost:8000');
    expect(services.ports).toBeInstanceOf(ApiPortService);
    expect(services.risk).toBeInstanceOf(ApiRiskService);
    expect(services.notifications).toBeInstanceOf(ApiNotificationService);
  });
});
