import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { InteractiveMap } from '@/components/InteractiveMap';
import { AUTH_TOKEN_KEY } from '@/services/httpClient';
import App from '@/App';
import type { Port, RiskAssessment } from '@/types';

const mockPort1: Port = {
  id: 'port-rotterdam',
  name: 'Port of Rotterdam',
  locode: 'NLRTM',
  country: 'Netherlands',
  lat: 51.95,
  lon: 4.13,
  isDefault: true,
  geofenceRadiusNm: 15,
  addedByUserId: null,
};

const mockPort2: Port = {
  id: 'port-singapore',
  name: 'Port of Singapore',
  locode: 'SGSIN',
  country: 'Singapore',
  lat: 1.29,
  lon: 103.85,
  isDefault: true,
  geofenceRadiusNm: 20,
  addedByUserId: null,
};

const mockPort3: Port = {
  id: 'port-houston',
  name: 'Port of Houston',
  locode: 'USHOU',
  country: 'United States',
  lat: 29.76,
  lon: -95.36,
  isDefault: false,
  geofenceRadiusNm: 18,
  addedByUserId: 'usr-1',
};

const mockAssessmentRotterdamLow: RiskAssessment = {
  id: 'risk-rotterdam',
  portId: 'port-rotterdam',
  portName: 'Port of Rotterdam',
  vesselClass: 'neoPanamax',
  vesselClassLabel: 'Neo-Panamax',
  timestamp: '2026-10-25T00:00:00Z',
  compositeTier: 'low',
  compositeScore: 25.0,
  subRisks: {
    congestion: { category: 'congestion', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
    weather: { category: 'weather', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
    navigational: { category: 'navigational', tier: 'low', score: 25.0, detail: 'Normal', factors: [] },
  },
  metrics: {
    portId: 'port-rotterdam',
    timestamp: '2026-10-25T00:00:00Z',
    congestion: {
      anchorageQueueCount: 4,
      avgWaitingTimeHours: 6.0,
      berthOccupancyPct: 55.0,
      rolling30dAvgQueue: 5.0,
      rolling30dAvgWaitHours: 7.0,
    },
    terminal: {
      berthTurnaroundHours: 18.0,
      berthToAnchorageWaitRatio: 0.8,
      dwellTimeAnomalyScore: 10,
      rolling30dAvgTurnaround: 20.0,
    },
    weather: {
      windSpeedKnots: 12.0,
      waveHeightM: 1.1,
      swellPeriodSec: 7.0,
      visibilityNm: 10.0,
      gustSpeedKnots: 15.0,
    },
    navigational: {
      underKeelClearanceM: 3.5,
      channelDepthM: 21.0,
      airDraftClearanceM: 45.0,
      pilotageAvailable: true,
      tideHeightM: 1.5,
    },
  },
};

const mockAssessmentSingaporeMedium: RiskAssessment = {
  ...mockAssessmentRotterdamLow,
  id: 'risk-singapore',
  portId: 'port-singapore',
  portName: 'Port of Singapore',
  compositeTier: 'medium',
  compositeScore: 60.0,
};

const mockAssessmentHoustonHigh: RiskAssessment = {
  ...mockAssessmentRotterdamLow,
  id: 'risk-houston',
  portId: 'port-houston',
  portName: 'Port of Houston',
  compositeTier: 'high',
  compositeScore: 90.0,
  metrics: {
    ...mockAssessmentRotterdamLow.metrics,
    navigational: {
      ...mockAssessmentRotterdamLow.metrics.navigational,
      underKeelClearanceM: -0.6,
      channelDepthM: 13.5,
    },
  },
  alternatives: [
    {
      portId: 'port-corpus-christi',
      unlocode: 'USCRP',
      portName: 'Port of Corpus Christi',
      country: 'United States',
      distanceNm: 150.0,
      channelDepthM: 16.5,
      depthMarginM: 2.0,
      swellHeightM: 1.0,
      riskTier: 'low',
      lat: 27.81,
      lon: -97.40,
    },
  ],
};

describe('InteractiveMap Component', () => {
  const assessmentsMap = new Map<string, RiskAssessment>();
  assessmentsMap.set('port-rotterdam', mockAssessmentRotterdamLow);
  assessmentsMap.set('port-singapore', mockAssessmentSingaporeMedium);
  assessmentsMap.set('port-houston', mockAssessmentHoustonHigh);

  it('renders pins for all monitored ports with exact coordinate markers', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    expect(screen.getByTestId('map-pin-port-rotterdam')).toBeInTheDocument();
    expect(screen.getByTestId('map-pin-port-singapore')).toBeInTheDocument();
    expect(screen.getByTestId('map-pin-port-houston')).toBeInTheDocument();
  });

  it('applies risk tier color coding across Low, Medium, and High pins', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    const pinLow = screen.getByTestId('map-pin-port-rotterdam');
    const pinMedium = screen.getByTestId('map-pin-port-singapore');
    const pinHigh = screen.getByTestId('map-pin-port-houston');

    // Accessibility ARIA labels
    expect(pinLow.getAttribute('aria-label')).toBe('Port of Rotterdam - LOW Risk');
    expect(pinMedium.getAttribute('aria-label')).toBe('Port of Singapore - MEDIUM Risk');
    expect(pinHigh.getAttribute('aria-label')).toBe('Port of Houston - HIGH Risk');

    // Check SVG circle fill
    const circleLow = pinLow.querySelectorAll('circle')[0];
    const circleMedium = pinMedium.querySelectorAll('circle')[0];
    const circleHigh = pinHigh.querySelectorAll('circle')[0];

    expect(circleLow.getAttribute('fill')).toBe('#10B981'); // emerald
    expect(circleMedium.getAttribute('fill')).toBe('#F59E0B'); // amber
    expect(circleHigh.getAttribute('fill')).toBe('#EF4444'); // red
  });

  it('clicking a pin opens the direct map popup displaying full operational telemetry', () => {
    const onSelectPort = vi.fn();
    render(
      <InteractiveMap
        ports={[mockPort1]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
        onSelectPort={onSelectPort}
      />
    );

    // Initial state: popup closed
    expect(screen.queryByTestId('map-popup')).not.toBeInTheDocument();

    // Click pin
    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));

    expect(onSelectPort).toHaveBeenCalledWith('port-rotterdam');
    expect(screen.getByTestId('map-popup')).toBeInTheDocument();

    // Popup content
    const popup = screen.getByTestId('map-popup');
    expect(popup).toHaveTextContent('Port of Rotterdam');
    expect(popup).toHaveTextContent('NLRTM');
    expect(screen.getByTestId('popup-risk-badge')).toHaveTextContent('LOW · 25');
    expect(screen.getByTestId('popup-anchored-count')).toHaveTextContent('4');
    expect(screen.getByTestId('popup-channel-depth')).toHaveTextContent('21.0m');
    expect(screen.getByTestId('popup-ukc-margin')).toHaveTextContent('+3.5m UKC');
    expect(screen.getByTestId('popup-swell')).toHaveTextContent('1.1m Swell');
    expect(screen.getByTestId('popup-wind')).toHaveTextContent('12.0 kn Wind');
  });

  it('high-risk port popup displays inline alternative recommendations, low-risk omits them', () => {
    const { rerender } = render(
      <InteractiveMap
        ports={[mockPort1, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    // Click Low Risk pin
    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));
    expect(screen.queryByTestId('alternative-port-diversion')).not.toBeInTheDocument();

    // Click High Risk pin
    fireEvent.click(screen.getByTestId('map-pin-port-houston'));
    expect(screen.getByTestId('alternative-port-diversion')).toBeInTheDocument();
    expect(screen.getByText('Port of Corpus Christi (USCRP)')).toBeInTheDocument();
    expect(screen.getByText('150.0 NM')).toBeInTheDocument();
  });

  it('dismisses popup via close button, escape key, or map backdrop click', () => {
    render(
      <InteractiveMap
        ports={[mockPort1]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    // Open popup
    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));
    expect(screen.getByTestId('map-popup')).toBeInTheDocument();

    // Dismiss via close button
    fireEvent.click(screen.getByRole('button', { name: /Close/i }));
    expect(screen.queryByTestId('map-popup')).not.toBeInTheDocument();

    // Reopen and dismiss via Escape key
    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));
    expect(screen.getByTestId('map-popup')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('map-popup')).not.toBeInTheDocument();

    // Reopen and dismiss via backdrop click
    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));
    expect(screen.getByTestId('map-popup')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('interactive-map-container').querySelector('svg')!);
    expect(screen.queryByTestId('map-popup')).not.toBeInTheDocument();
  });

  it('enforces drawer-free architecture: confirms no drawer elements exist', () => {
    const { container } = render(
      <InteractiveMap
        ports={[mockPort1]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    fireEvent.click(screen.getByTestId('map-pin-port-rotterdam'));

    expect(container.querySelector('.drawer')).toBeNull();
    expect(container.querySelector('.flyout')).toBeNull();
    expect(container.querySelector('.slide-out')).toBeNull();
    expect(container.querySelector('[data-drawer]')).toBeNull();
  });

  it('renders centered empty state with + Add First Port to Watchlist when ports array is empty', () => {
    const onAddFirstPort = vi.fn();
    render(
      <InteractiveMap
        ports={[]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
        onAddFirstPort={onAddFirstPort}
      />
    );

    expect(screen.getByTestId('map-empty-state')).toBeInTheDocument();
    const btn = screen.getByTestId('map-add-first-port');
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    expect(onAddFirstPort).toHaveBeenCalledTimes(1);
  });

  it('zoom and reset controls function cleanly without errors', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    const zoomInBtn = screen.getByRole('button', { name: /Zoom In/i });
    const zoomOutBtn = screen.getByRole('button', { name: /Zoom Out/i });
    const resetBtn = screen.getByRole('button', { name: /Reset View/i });

    fireEvent.click(zoomInBtn);
    fireEvent.click(zoomOutBtn);
    fireEvent.click(resetBtn);
  });

  it('filters displayed port pins according to selected vesselClass', () => {
    const portPanamax: Port = { ...mockPort1, id: 'port-panamax', vesselClass: 'panamax' };
    const portVlcc: Port = { ...mockPort2, id: 'port-vlcc', vesselClass: 'vlcc' };
    const portNeoPanamax: Port = { ...mockPort3, id: 'port-neopanamax', vesselClass: 'neoPanamax' };

    const { rerender } = render(
      <InteractiveMap
        ports={[portPanamax, portVlcc, portNeoPanamax]}
        assessments={new Map()}
        vesselClass="neoPanamax"
      />
    );

    // Only neoPanamax should be visible
    expect(screen.getByTestId('map-pin-port-neopanamax')).toBeInTheDocument();
    expect(screen.queryByTestId('map-pin-port-panamax')).not.toBeInTheDocument();
    expect(screen.queryByTestId('map-pin-port-vlcc')).not.toBeInTheDocument();
    expect(screen.getByText('(1 of 3 ports)')).toBeInTheDocument();

    // Rerender with 'vlcc'
    rerender(
      <InteractiveMap
        ports={[portPanamax, portVlcc, portNeoPanamax]}
        assessments={new Map()}
        vesselClass="vlcc"
      />
    );

    expect(screen.getByTestId('map-pin-port-vlcc')).toBeInTheDocument();
    expect(screen.queryByTestId('map-pin-port-neopanamax')).not.toBeInTheDocument();
    expect(screen.queryByTestId('map-pin-port-panamax')).not.toBeInTheDocument();
    expect(screen.getByText('(1 of 3 ports)')).toBeInTheDocument();
  });

  it('displays no-vessel-ports-alert banner when no ports match selected vesselClass', () => {
    const portPanamax: Port = { ...mockPort1, id: 'port-panamax', vesselClass: 'panamax' };

    render(
      <InteractiveMap
        ports={[portPanamax]}
        assessments={new Map()}
        vesselClass="capesize"
      />
    );

    expect(screen.queryByTestId('map-pin-port-panamax')).not.toBeInTheDocument();
    expect(screen.getByTestId('no-vessel-ports-alert')).toBeInTheDocument();
    expect(screen.getByText('(0 of 1 ports)')).toBeInTheDocument();
  });

  it('changing vessel class filter does not resize or recenter the map view', () => {
    const portPanamax: Port = { ...mockPort1, id: 'port-panamax', vesselClass: 'panamax' };
    const portVlcc: Port = { ...mockPort2, id: 'port-vlcc', vesselClass: 'vlcc' };

    const { rerender } = render(
      <InteractiveMap
        ports={[portPanamax, portVlcc]}
        assessments={new Map()}
        vesselClass="panamax"
      />
    );

    const mapGroup = screen.getByTestId('interactive-map-container').querySelector('svg > g');
    expect(mapGroup?.getAttribute('transform')).toBe('translate(0, 0) scale(1)');

    // Zoom in
    const zoomInBtn = screen.getByRole('button', { name: /Zoom In/i });
    fireEvent.click(zoomInBtn);
    const zoomedTransform = mapGroup?.getAttribute('transform');
    expect(zoomedTransform).toContain('scale(1.5)');

    // Change vessel class to vlcc
    rerender(
      <InteractiveMap
        ports={[portPanamax, portVlcc]}
        assessments={new Map()}
        vesselClass="vlcc"
      />
    );

    // Transform remains exactly the same! No jumping or resizing to the top-left!
    expect(mapGroup?.getAttribute('transform')).toBe(zoomedTransform);
  });

  it('allows extended deep zoom up to 512x and displays the zoom level badge', () => {
    render(
      <InteractiveMap
        ports={[mockPort1]}
        assessments={new Map()}
        vesselClass="neoPanamax"
      />
    );

    const zoomInBtn = screen.getByRole('button', { name: /Zoom In/i });
    const zoomLevelBadge = screen.getByTestId('map-zoom-level');
    expect(zoomLevelBadge).toHaveTextContent('1.0x');

    // Click zoom in 10 times to reach high zoom beyond previous 24x cap
    for (let i = 0; i < 10; i++) {
      fireEvent.click(zoomInBtn);
    }
    expect(zoomLevelBadge).toHaveTextContent('57.8x');

    // Click additional times to reach maximum deep zoom (512x)
    for (let i = 0; i < 10; i++) {
      fireEvent.click(zoomInBtn);
    }
    expect(zoomLevelBadge).toHaveTextContent('512.0x');
    const mapGroup = screen.getByTestId('interactive-map-container').querySelector('svg > g');
    expect(mapGroup?.getAttribute('transform')).toContain('scale(512)');
  });

  it('clicking a port pin automatically zooms into the region to differentiate nearby ports', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    const mapGroup = screen.getByTestId('interactive-map-container').querySelector('svg > g');
    expect(mapGroup?.getAttribute('transform')).toBe('translate(0, 0) scale(1)');

    // Click Houston pin from initial global zoom 1
    const houstonPin = screen.getByTestId('map-pin-port-houston');
    fireEvent.click(houstonPin);

    // Camera zooms in to at least 6x to clearly differentiate Corpus Christi (150 NM)
    expect(mapGroup?.getAttribute('transform')).toContain('scale(6)');
    expect(screen.getByTestId('map-zoom-level')).toHaveTextContent('6.0x');
  });

  it('clicking "Zoom into Port & Alternatives" button in popup focuses camera to 8x', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    const houstonPin = screen.getByTestId('map-pin-port-houston');
    fireEvent.click(houstonPin);

    const focusBtn = screen.getByTestId('popup-focus-port');
    expect(focusBtn).toBeInTheDocument();
    fireEvent.click(focusBtn);

    const mapGroup = screen.getByTestId('interactive-map-container').querySelector('svg > g');
    expect(mapGroup?.getAttribute('transform')).toContain('scale(8)');
    expect(screen.getByTestId('map-zoom-level')).toHaveTextContent('8.0x');
  });

  it('renders alternative safe haven pins and diversion route vectors on map for high-risk ports', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    // Corpus Christi is an alternative for Houston (which is high risk)
    expect(screen.getByTestId('map-alt-pin-port-corpus-christi')).toBeInTheDocument();
    expect(screen.getByTestId('map-diversion-line-port-corpus-christi')).toBeInTheDocument();
    expect(screen.getByTestId('map-diversion-badge-port-corpus-christi')).toBeInTheDocument();
    expect(screen.getByText('150 NM')).toBeInTheDocument();
  });

  it('clicking an alternative safe haven pin opens on-map detail popup with depth margin and diversion stats', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    const altPin = screen.getByTestId('map-alt-pin-port-corpus-christi');
    fireEvent.click(altPin);

    // On-map alternative popup displays
    expect(screen.getByTestId('map-alt-popup')).toBeInTheDocument();
    expect(screen.getByTestId('alt-popup-title')).toHaveTextContent('Port of Corpus Christi');
    expect(screen.getByTestId('alt-popup-locode')).toHaveTextContent('USCRP');
    expect(screen.getByTestId('alt-popup-ukc-margin')).toHaveTextContent('+2.0m');
    expect(screen.getByTestId('alt-popup-channel-depth')).toHaveTextContent('16.5m');
    expect(screen.getByTestId('alt-popup-diversion')).toHaveTextContent('150.0 NM diversion');
  });

  it('1-click + Add to Watchlist button adds the alternative port with its dynamic coordinates', async () => {
    const handleAddPort = vi.fn().mockResolvedValue({ id: 'port-new' });

    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
        onAddPort={handleAddPort}
      />
    );

    const altPin = screen.getByTestId('map-alt-pin-port-corpus-christi');
    fireEvent.click(altPin);

    const addBtn = screen.getByTestId('add-alt-to-watchlist');
    expect(addBtn).toBeInTheDocument();
    fireEvent.click(addBtn);

    expect(handleAddPort).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Port of Corpus Christi',
        locode: 'USCRP',
        country: 'United States',
        lat: 27.81,
        lon: -97.40,
        vesselClass: 'neoPanamax',
      })
    );
  });

  it('clicking alternative candidate inside port detail popup opens safe haven popup', () => {
    render(
      <InteractiveMap
        ports={[mockPort1, mockPort2, mockPort3]}
        assessments={assessmentsMap}
        vesselClass="neoPanamax"
      />
    );

    // Open Houston primary port popup
    const houstonPin = screen.getByTestId('map-pin-port-houston');
    fireEvent.click(houstonPin);

    // Primary popup opens with AlternativePortDiversion
    expect(screen.getByTestId('map-popup')).toBeInTheDocument();
    const altCandidateCard = screen.getByTestId('alternative-candidate-port-corpus-christi');
    expect(altCandidateCard).toBeInTheDocument();

    // Click candidate card inside popup
    fireEvent.click(altCandidateCard);

    // Safe haven alternative popup opens
    expect(screen.getByTestId('map-alt-popup')).toBeInTheDocument();
    expect(screen.getByTestId('alt-popup-title')).toHaveTextContent('Port of Corpus Christi');
  });
});

describe('Dashboard Grid vs Map View Toggle in App', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(AUTH_TOKEN_KEY, 'test-jwt-token');
    localStorage.setItem(
      'berthmark_user',
      JSON.stringify({
        id: 'usr-test-1',
        email: 'captain@fleet.com',
        name: 'Captain Aubrey',
      })
    );
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('toggles between Card Grid and Map View seamlessly', () => {
    render(<App />);

    const gridToggle = screen.getByTestId('toggle-grid-view');
    const mapToggle = screen.getByTestId('toggle-map-view');

    expect(gridToggle).toBeInTheDocument();
    expect(mapToggle).toBeInTheDocument();

    // Default view: Grid mode
    expect(screen.queryByTestId('interactive-map-container')).not.toBeInTheDocument();

    // Switch to Map View
    fireEvent.click(mapToggle);
    expect(screen.getByTestId('interactive-map-container')).toBeInTheDocument();

    // Switch back to Grid View
    fireEvent.click(gridToggle);
    expect(screen.queryByTestId('interactive-map-container')).not.toBeInTheDocument();
  });
});
