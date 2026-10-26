import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import App from '@/App';
import { setServices } from '@/services';
import { AUTH_TOKEN_KEY } from '@/services/httpClient';
import { authService } from '@/services/authService';
import type { IPortService, IRiskService, INotificationService } from '@/services/interfaces';
import type { Port, RiskAssessment, Notification, VesselClass } from '@/types';

describe('Frontend End-to-End User Journey (Issue 24)', () => {
  let mockPorts: Port[];
  let mockNotifications: Notification[];
  let mockAssessments: Record<string, RiskAssessment>;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(AUTH_TOKEN_KEY, 'mock-operator-jwt-token');
    localStorage.setItem(
      'berthmark_user',
      JSON.stringify({
        id: 'usr-e2e-operator',
        email: 'operator@maritimerisk.com',
        name: 'Ship Operations Manager',
      })
    );
    vi.spyOn(authService, 'getCurrentUser').mockResolvedValue({
      id: 'usr-e2e-operator',
      email: 'operator@maritimerisk.com',
      name: 'Ship Operations Manager',
    });

    mockPorts = [
      {
        id: 'port-rotterdam',
        name: 'Port of Rotterdam',
        locode: 'NLRTM',
        country: 'Netherlands',
        lat: 51.9244,
        lon: 4.4777,
        isDefault: true,
        geofenceRadiusNm: 8.0,
        addedByUserId: null,
        vesselClass: 'vlcc',
      },
      {
        id: 'port-singapore',
        name: 'Port of Singapore',
        locode: 'SGSIN',
        country: 'Singapore',
        lat: 1.2648,
        lon: 103.8408,
        isDefault: true,
        geofenceRadiusNm: 8.0,
        addedByUserId: null,
        vesselClass: 'neoPanamax',
      },
      {
        id: 'port-houston',
        name: 'Port of Houston',
        locode: 'USHOU',
        country: 'United States',
        lat: 29.75,
        lon: -95.28,
        isDefault: true,
        geofenceRadiusNm: 8.0,
        addedByUserId: null,
        vesselClass: 'aframax',
      },
    ];

    mockNotifications = [
      {
        id: 'notif-1',
        type: 'stateChange',
        portId: 'port-rotterdam',
        portName: 'Port of Rotterdam',
        title: 'Risk Escalated to High',
        message: 'Port of Rotterdam risk shifted from Medium to High due to wave swell.',
        tier: 'high',
        previousTier: 'medium',
        timestamp: new Date().toISOString(),
        read: false,
      },
    ];

    mockAssessments = {
      'port-rotterdam': {
        id: 'risk-rotterdam',
        portId: 'port-rotterdam',
        portName: 'Port of Rotterdam',
        vesselClass: 'vlcc',
        vesselClassLabel: 'VLCC',
        timestamp: new Date().toISOString(),
        compositeTier: 'high',
        compositeScore: 90.0,
        subRisks: {
          congestion: { category: 'congestion', tier: 'medium', score: 60.0, detail: 'High anchored count', factors: [] },
          terminalDelays: { category: 'terminalDelays', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
          weather: { category: 'weather', tier: 'high', score: 90.0, detail: 'Heavy swell 2.8m', factors: [] },
          navigational: { category: 'navigational', tier: 'high', score: 90.0, detail: 'UKC depth violation', factors: [] },
        },
        metrics: {
          portId: 'port-rotterdam',
          timestamp: new Date().toISOString(),
          congestion: {
            anchorageQueueCount: 14,
            avgWaitingTimeHours: 12.0,
            berthOccupancyPct: 75.0,
            rolling30dAvgQueue: 10.0,
            rolling30dAvgWaitHours: 8.0,
          },
          terminal: {
            berthTurnaroundHours: 24.0,
            berthToAnchorageWaitRatio: 1.2,
            dwellTimeAnomalyScore: 15,
            rolling30dAvgTurnaround: 20.0,
          },
          weather: {
            windSpeedKnots: 22.0,
            waveHeightM: 2.8,
            swellPeriodSec: 9.0,
            visibilityNm: 8.0,
            gustSpeedKnots: 28.0,
          },
          navigational: {
            underKeelClearanceM: -11.85,
            channelDepthM: 16.5,
            airDraftClearanceM: 40.0,
            pilotageAvailable: true,
            tideHeightM: 1.0,
          },
        },
        alternatives: [
          {
            portId: 'port-wilhelmshaven',
            unlocode: 'DEWVN',
            portName: 'Port of Wilhelmshaven',
            country: 'Germany',
            distanceNm: 140.0,
            channelDepthM: 20.0,
            depthMarginM: 3.28,
            swellHeightM: 1.0,
            riskTier: 'low',
            trafficStatus: '3 anchored / 2 underway',
          },
        ],
      },
      'port-singapore': {
        id: 'risk-singapore',
        portId: 'port-singapore',
        portName: 'Port of Singapore',
        vesselClass: 'neoPanamax',
        vesselClassLabel: 'Neo-Panamax',
        timestamp: new Date().toISOString(),
        compositeTier: 'low',
        compositeScore: 25.0,
        subRisks: {
          congestion: { category: 'congestion', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
          terminalDelays: { category: 'terminalDelays', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
          weather: { category: 'weather', tier: 'low', score: 25.0, detail: 'Calm', factors: [] },
          navigational: { category: 'navigational', tier: 'low', score: 25.0, detail: 'Safe UKC', factors: [] },
        },
        metrics: {
          portId: 'port-singapore',
          timestamp: new Date().toISOString(),
          congestion: {
            anchorageQueueCount: 5,
            avgWaitingTimeHours: 4.0,
            berthOccupancyPct: 50.0,
            rolling30dAvgQueue: 8.0,
            rolling30dAvgWaitHours: 6.0,
          },
          terminal: {
            berthTurnaroundHours: 16.0,
            berthToAnchorageWaitRatio: 0.7,
            dwellTimeAnomalyScore: 5,
            rolling30dAvgTurnaround: 18.0,
          },
          weather: {
            windSpeedKnots: 8.0,
            waveHeightM: 0.5,
            swellPeriodSec: 5.0,
            visibilityNm: 12.0,
            gustSpeedKnots: 10.0,
          },
          navigational: {
            underKeelClearanceM: 1.5,
            channelDepthM: 15.0,
            airDraftClearanceM: 50.0,
            pilotageAvailable: true,
            tideHeightM: 2.0,
          },
        },
        alternatives: [],
      },
      'port-houston': {
        id: 'risk-houston',
        portId: 'port-houston',
        portName: 'Port of Houston',
        vesselClass: 'aframax',
        vesselClassLabel: 'Aframax',
        timestamp: new Date().toISOString(),
        compositeTier: 'medium',
        compositeScore: 60.0,
        subRisks: {
          congestion: { category: 'congestion', tier: 'medium', score: 60.0, detail: 'Moderate traffic', factors: [] },
          terminalDelays: { category: 'terminalDelays', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
          weather: { category: 'weather', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
          navigational: { category: 'navigational', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
        },
        metrics: {
          portId: 'port-houston',
          timestamp: new Date().toISOString(),
          congestion: {
            anchorageQueueCount: 8,
            avgWaitingTimeHours: 8.0,
            berthOccupancyPct: 65.0,
            rolling30dAvgQueue: 9.0,
            rolling30dAvgWaitHours: 7.5,
          },
          terminal: {
            berthTurnaroundHours: 20.0,
            berthToAnchorageWaitRatio: 0.9,
            dwellTimeAnomalyScore: 8,
            rolling30dAvgTurnaround: 22.0,
          },
          weather: {
            windSpeedKnots: 15.0,
            waveHeightM: 1.2,
            swellPeriodSec: 6.0,
            visibilityNm: 9.0,
            gustSpeedKnots: 18.0,
          },
          navigational: {
            underKeelClearanceM: 0.8,
            channelDepthM: 14.0,
            airDraftClearanceM: 42.0,
            pilotageAvailable: true,
            tideHeightM: 0.8,
          },
        },
        alternatives: [],
      },
    };

    const mockPortsService: IPortService = {
      getPorts: vi.fn(async () => [...mockPorts]),
      getDefaultPorts: vi.fn(async () => mockPorts.filter((p) => p.isDefault)),
      searchPorts: vi.fn(async (q: string) => {
        if (!q.trim() || q === 'UNKNOWN_PORT_XYZ') return [];
        return mockPorts.filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
      }),
      addPort: vi.fn(async (port) => {
        const newPort: Port = { ...port, id: `port-custom-${Date.now()}`, isDefault: false };
        mockPorts.push(newPort);
        return newPort;
      }),
      removePort: vi.fn(async (id: string) => {
        mockPorts = mockPorts.filter((p) => p.id !== id);
      }),
    };

    const mockRiskService: IRiskService = {
      getRiskAssessment: vi.fn(async (portId: string) => mockAssessments[portId]),
      getBulkRiskAssessments: vi.fn(async (portsList: { id: string; name: string }[]) => {
        return portsList.map((p) => mockAssessments[p.id] ?? {
          portId: p.id,
          vesselClass: 'neoPanamax' as VesselClass,
          compositeTier: 'low',
          compositeScore: 25.0,
          subRisks: {
            congestion: { category: 'congestion', tier: 'low', score: 25.0, detail: '', factors: [] },
            terminalDelays: { category: 'terminalDelays', tier: 'low', score: 25.0, detail: '', factors: [] },
            weather: { category: 'weather', tier: 'low', score: 25.0, detail: '', factors: [] },
            navigational: { category: 'navigational', tier: 'low', score: 25.0, detail: '', factors: [] },
          },
          metrics: {
            portId: p.id,
            timestamp: new Date().toISOString(),
            congestion: {
              anchorageQueueCount: 0,
              avgWaitingTimeHours: 0,
              berthOccupancyPct: 0,
              rolling30dAvgQueue: 0,
              rolling30dAvgWaitHours: 0,
            },
            terminal: {
              berthTurnaroundHours: 0,
              berthToAnchorageWaitRatio: 0,
              dwellTimeAnomalyScore: 0,
              rolling30dAvgTurnaround: 0,
            },
            weather: {
              windSpeedKnots: 10.0,
              waveHeightM: 1.0,
              swellPeriodSec: 5.0,
              visibilityNm: 10.0,
              gustSpeedKnots: 12.0,
            },
            navigational: {
              underKeelClearanceM: 3.0,
              channelDepthM: 15.0,
              airDraftClearanceM: 40.0,
              pilotageAvailable: true,
              tideHeightM: 1.0,
            },
          },
          alternatives: [],
          lastUpdated: new Date().toISOString(),
        });
      }),
      getHistoricalTrend: vi.fn(async () => []),
    };

    const mockNotificationService: INotificationService = {
      getNotifications: vi.fn(async (_userId, unreadOnly) => {
        return unreadOnly ? mockNotifications.filter((n) => !n.read) : [...mockNotifications];
      }),
      markAsRead: vi.fn(async (id: string) => {
        const target = mockNotifications.find((n) => n.id === id);
        if (target) target.read = true;
      }),
      markAllAsRead: vi.fn(async () => {
        mockNotifications.forEach((n) => { n.read = true; });
      }),
      generateStateChangeAlert: vi.fn((portId, portName, newTier, previousTier) => {
        const notif: Notification = {
          id: `notif-${Date.now()}`,
          type: 'stateChange',
          portId,
          portName,
          title: `Alert: ${portName}`,
          message: `${portName} transitioned to ${newTier}`,
          tier: newTier,
          previousTier,
          timestamp: new Date().toISOString(),
          read: false,
        };
        mockNotifications.push(notif);
        return notif;
      }),
    };

    setServices({
      ports: mockPortsService,
      risk: mockRiskService,
      notifications: mockNotificationService,
    });
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('renders application header, tracked port count, and high-density card grid', async () => {
    render(<App />);

    // Header title and count
    expect(screen.getByText('Port-Call Risk Tracker')).toBeInTheDocument();
    expect(await screen.findByText(/3 ports tracked/i)).toBeInTheDocument();

    // High density grid renders monitored ports
    expect(await screen.findByText('Port of Singapore')).toBeInTheDocument();
    expect(screen.getByText('Port of Houston')).toBeInTheDocument();
    expect(screen.getByText('Port of Rotterdam')).toBeInTheDocument();
  });

  it('displays high-risk tier and inline alternative port diversion recommendations without drawers', async () => {
    render(<App />);

    // Wait until risk assessments settle and render inline diversion recommendations on the card
    const rtmCard = await waitFor(() => {
      const card = screen.getByTestId('port-card-port-rotterdam');
      expect(within(card).getByText(/Alternative Port Recommendations/i)).toBeInTheDocument();
      return card;
    });

    // Verify HIGH risk badge
    expect(within(rtmCard).getByText(/HIGH/i)).toBeInTheDocument();

    // Verify inline alternative port recommendation (Wilhelmshaven - DEWVN - 140.0 NM)
    expect(within(rtmCard).getByText(/Port of Wilhelmshaven/i)).toBeInTheDocument();
    expect(within(rtmCard).getByText(/140.0 NM/i)).toBeInTheDocument();
  });

  it('toggles to interactive map view and displays direct popups without slide-out drawers', async () => {
    render(<App />);

    // Switch to Map View via view toggle button
    const mapToggleBtn = screen.getByTestId('toggle-map-view');
    fireEvent.click(mapToggleBtn);

    // Interactive map renders
    const mapContainer = await screen.findByTestId('interactive-map-container');
    expect(mapContainer).toBeInTheDocument();

    // SVG pins are rendered for tracked ports
    const pins = screen.getAllByTestId(/^map-pin-/);
    expect(pins.length).toBeGreaterThanOrEqual(3);

    // Click Rotterdam pin to trigger direct popup
    const rtmPin = screen.getByTestId('map-pin-port-rotterdam');
    fireEvent.click(rtmPin);

    // Direct popup window renders on map
    const popup = await screen.findByTestId('map-popup');
    expect(popup).toBeInTheDocument();
    expect(popup).toHaveTextContent('NLRTM');
    expect(popup).toHaveTextContent('16.5m'); // Controlling depth
    expect(popup).toHaveTextContent('2.8m');  // Swell height
  });

  it('interacts with notification bell badge and dismisses unread alert', async () => {
    render(<App />);

    // Bell badge shows 1 unread notification
    const badge = await screen.findByTestId('notification-badge');
    expect(badge).toHaveTextContent('1');

    // Click bell button to open notification feed
    const bellBtn = screen.getByTestId('notification-bell-btn');
    fireEvent.click(bellBtn);

    // Panel is opened
    expect(await screen.findByText(/Risk Escalated to High/i)).toBeInTheDocument();
    const panel = screen.getByTestId('notification-panel');
    expect(within(panel).getByTestId('notification-port-name')).toHaveTextContent('Port of Rotterdam');

    // Click notification item to mark as read
    const notifItem = screen.getByTestId('notification-item-notif-1');
    fireEvent.click(notifItem);

    // Unread count decrements to 0 and badge disappears
    await waitFor(() => {
      expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
    });
  });
});
