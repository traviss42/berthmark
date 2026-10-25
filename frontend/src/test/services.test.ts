import { describe, it, expect, beforeEach } from 'vitest';
import { MockPortService } from '@/services/mockPortService';
import { MockRiskService } from '@/services/mockRiskService';
import { MockNotificationService } from '@/services/mockNotificationService';
import { DEFAULT_PORTS } from '@/data/mockData';

describe('MockPortService', () => {
  let service: MockPortService;

  beforeEach(() => {
    service = new MockPortService();
  });

  it('returns default ports for a new user', async () => {
    const ports = await service.getPorts('user-1');
    expect(ports.length).toBeGreaterThanOrEqual(DEFAULT_PORTS.length);
    const defaultPorts = ports.filter((p) => p.isDefault);
    expect(defaultPorts.length).toBe(DEFAULT_PORTS.length);
  });

  it('getDefaultPorts returns only defaults', async () => {
    const ports = await service.getDefaultPorts();
    expect(ports).toHaveLength(DEFAULT_PORTS.length);
    ports.forEach((p) => expect(p.isDefault).toBe(true));
  });

  it('searchPorts finds by name', async () => {
    const results = await service.searchPorts('Rotterdam');
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].name).toContain('Rotterdam');
  });

  it('searchPorts finds by LOCODE', async () => {
    const results = await service.searchPorts('SGSIN');
    expect(results.length).toBeGreaterThan(0);
    expect(results[0].locode).toBe('SGSIN');
  });

  it('searchPorts finds by country', async () => {
    const results = await service.searchPorts('Singapore');
    expect(results.length).toBeGreaterThan(0);
  });

  it('searchPorts returns empty for blank query', async () => {
    const results = await service.searchPorts('   ');
    expect(results).toHaveLength(0);
  });

  it('searchPorts returns results for single-character query', async () => {
    const results = await service.searchPorts('S');
    expect(results.length).toBeGreaterThan(0);
  });

  it('addPort creates a private port for the user', async () => {
    const port = await service.addPort(
      { name: 'Test Port', locode: 'XXTST', country: 'TestCountry', lat: 0, lon: 0, geofenceRadiusNm: 5 },
      'user-1'
    );
    expect(port.id).toBeTruthy();
    expect(port.isDefault).toBe(false);
    expect(port.addedByUserId).toBe('user-1');
    expect(port.name).toBe('Test Port');

    const allPorts = await service.getPorts('user-1');
    expect(allPorts.some((p) => p.id === port.id)).toBe(true);
  });

  it('removePort removes user-added port', async () => {
    const port = await service.addPort(
      { name: 'To Remove', locode: 'XXREM', country: 'TC', lat: 0, lon: 0, geofenceRadiusNm: 5 },
      'user-1'
    );
    const before = await service.getPorts('user-1');
    expect(before.some((p) => p.id === port.id)).toBe(true);

    await service.removePort(port.id, 'user-1');
    const after = await service.getPorts('user-1');
    expect(after.some((p) => p.id === port.id)).toBe(false);
  });

  it('user ports are private to each user', async () => {
    await service.addPort(
      { name: 'Private Port', locode: 'XXPRI', country: 'TC', lat: 0, lon: 0, geofenceRadiusNm: 5 },
      'user-A'
    );

    const userAPorts = await service.getPorts('user-A');
    const userBPorts = await service.getPorts('user-B');

    expect(userAPorts.some((p) => p.name === 'Private Port')).toBe(true);
    expect(userBPorts.some((p) => p.name === 'Private Port')).toBe(false);
  });
});

describe('MockRiskService', () => {
  let service: MockRiskService;

  beforeEach(() => {
    service = new MockRiskService();
  });

  it('getRiskAssessment returns a valid assessment', async () => {
    const assessment = await service.getRiskAssessment('port-1', 'Port One', 'panamax');
    expect(assessment.portId).toBe('port-1');
    expect(assessment.portName).toBe('Port One');
    expect(assessment.vesselClass).toBe('panamax');
    expect(assessment.compositeTier).toMatch(/^(low|medium|high)$/);
    expect(assessment.subRisks.congestion).toBeDefined();
  });

  it('getBulkRiskAssessments returns assessment for each port', async () => {
    const ports = [
      { id: 'port-a', name: 'A' },
      { id: 'port-b', name: 'B' },
      { id: 'port-c', name: 'C' },
    ];
    const assessments = await service.getBulkRiskAssessments(ports, 'feeder');
    expect(assessments).toHaveLength(3);
    expect(assessments[0].portId).toBe('port-a');
    expect(assessments[1].portId).toBe('port-b');
    expect(assessments[2].portId).toBe('port-c');
  });

  it('getHistoricalTrend returns multiple data points', async () => {
    const trend = await service.getHistoricalTrend('port-1', 'panamax', 7);
    expect(trend.length).toBeGreaterThan(0);
    expect(trend.length).toBeLessThanOrEqual(40);
  });

  it('historical trend data points are in chronological order', async () => {
    const trend = await service.getHistoricalTrend('port-1', 'feeder', 3);
    for (let i = 1; i < trend.length; i++) {
      expect(new Date(trend[i].timestamp).getTime()).toBeGreaterThan(
        new Date(trend[i - 1].timestamp).getTime()
      );
    }
  });
});

describe('MockNotificationService', () => {
  let service: MockNotificationService;

  beforeEach(() => {
    service = new MockNotificationService();
  });

  it('starts with no notifications', async () => {
    const notifs = await service.getNotifications('mock-user');
    expect(notifs).toHaveLength(0);
  });

  it('generateStateChangeAlert creates and stores a notification', async () => {
    const notif = service.generateStateChangeAlert('port-1', 'Port One', 'high', 'medium');
    expect(notif.type).toBe('stateChange');
    expect(notif.portId).toBe('port-1');
    expect(notif.tier).toBe('high');
    expect(notif.previousTier).toBe('medium');
    expect(notif.read).toBe(false);

    const all = await service.getNotifications('mock-user');
    expect(all).toHaveLength(1);
  });

  it('markAsRead sets read to true', async () => {
    const notif = service.generateStateChangeAlert('port-1', 'Port One', 'medium', 'low');
    await service.markAsRead(notif.id);

    const all = await service.getNotifications('mock-user');
    const found = all.find((n) => n.id === notif.id);
    expect(found?.read).toBe(true);
  });

  it('markAllAsRead marks all notifications', async () => {
    service.generateStateChangeAlert('port-1', 'Port One', 'high', null);
    service.generateStateChangeAlert('port-2', 'Port Two', 'medium', 'low');

    await service.markAllAsRead('mock-user');

    const all = await service.getNotifications('mock-user');
    all.forEach((n) => expect(n.read).toBe(true));
  });

  it('notification message correctly describes tier transition', async () => {
    const notif = service.generateStateChangeAlert('port-1', 'Port One', 'high', 'low');
    expect(notif.message).toContain('Low');
    expect(notif.message).toContain('High');
    expect(notif.title).toContain('High');
  });
});
