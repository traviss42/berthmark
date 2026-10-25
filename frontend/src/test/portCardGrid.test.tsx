import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PortCard } from '@/components/PortCard';
import { PortList } from '@/components/PortList';
import type { Port, RiskAssessment } from '@/types';

const mockPortRotterdam: Port = {
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

const mockAssessmentLow: RiskAssessment = {
  id: 'risk-rotterdam-neopanamax',
  portId: 'port-rotterdam',
  portName: 'Port of Rotterdam',
  vesselClass: 'neoPanamax',
  vesselClassLabel: 'Neo-Panamax',
  timestamp: '2026-10-25T00:00:00Z',
  compositeTier: 'low',
  compositeScore: 25.0,
  subRisks: {
    congestion: {
      category: 'congestion',
      tier: 'low',
      score: 25.0,
      detail: 'Normal congestion',
      factors: [],
    },
    terminalDelays: {
      category: 'terminalDelays',
      tier: 'low',
      score: 25.0,
      detail: 'Normal',
      factors: [],
    },
    weather: {
      category: 'weather',
      tier: 'low',
      score: 25.0,
      detail: 'Clear',
      factors: [],
    },
    navigational: {
      category: 'navigational',
      tier: 'low',
      score: 25.0,
      detail: 'Ample depth',
      factors: [],
    },
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
      windSpeedKnots: 12.5,
      waveHeightM: 1.2,
      swellPeriodSec: 7.0,
      visibilityNm: 10.0,
      gustSpeedKnots: 15.0,
    },
    navigational: {
      underKeelClearanceM: 3.2,
      channelDepthM: 21.5,
      airDraftClearanceM: 45.0,
      pilotageAvailable: true,
      tideHeightM: 1.8,
    },
  },
};

describe('PortCard Component', () => {
  it('renders all required fields: header, risk badge, 4D traffic, depth, and weather', () => {
    render(<PortCard port={mockPortRotterdam} assessment={mockAssessmentLow} />);

    // Header
    expect(screen.getByText('Port of Rotterdam')).toBeInTheDocument();
    expect(screen.getByText('NLRTM')).toBeInTheDocument();
    expect(screen.getByText(/Netherlands/)).toBeInTheDocument();
    expect(screen.getByTestId('vessel-class-badge').textContent).toContain('Neo-Panamax');

    // Risk badge
    expect(screen.getByTestId('risk-badge').textContent).toContain('LOW · 25');

    // 4D traffic breakdown
    expect(screen.getByTestId('anchored-count').textContent).toBe('4');
    expect(screen.getByTestId('underway-count').textContent).toBe('0');
    expect(screen.getByTestId('total-count').textContent).toBe('4');
    // Queue variance: 4 vs 5 baseline = -20%
    expect(screen.getByTestId('queue-variance').textContent).toContain('-20% vs 7-day Avg');

    // Depth & Weather
    expect(screen.getByTestId('channel-depth').textContent).toBe('21.5m');
    expect(screen.getByTestId('ukc-margin').textContent).toBe('+3.2m UKC');
    expect(screen.getByTestId('swell-height').textContent).toBe('1.2m Swell');
    expect(screen.getByTestId('wind-speed').textContent).toBe('12.5 kn Wind');
  });

  it('renders Medium and High risk badges with correct styling and scores', () => {
    const mediumAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      compositeTier: 'medium',
      compositeScore: 60.0,
    };
    const { rerender } = render(
      <PortCard port={mockPortRotterdam} assessment={mediumAssessment} />
    );
    expect(screen.getByTestId('risk-badge').textContent).toContain('MEDIUM · 60');

    const highAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      compositeTier: 'high',
      compositeScore: 90.0,
    };
    rerender(<PortCard port={mockPortRotterdam} assessment={highAssessment} />);
    expect(screen.getByTestId('risk-badge').textContent).toContain('HIGH · 90');
  });

  it('formats positive, negative, and zero queue variance correctly', () => {
    // Increase: 8 anchored vs 4 baseline = +100%
    const increaseAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        congestion: {
          ...mockAssessmentLow.metrics.congestion,
          anchorageQueueCount: 8,
          rolling30dAvgQueue: 4,
        },
      },
    };
    const { rerender } = render(
      <PortCard port={mockPortRotterdam} assessment={increaseAssessment} />
    );
    expect(screen.getByTestId('queue-variance').textContent).toContain('+100% vs 7-day Avg');

    // Unchanged: 4 anchored vs 4 baseline = 0%
    const unchangedAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        congestion: {
          ...mockAssessmentLow.metrics.congestion,
          anchorageQueueCount: 4,
          rolling30dAvgQueue: 4,
        },
      },
    };
    rerender(<PortCard port={mockPortRotterdam} assessment={unchangedAssessment} />);
    expect(screen.getByTestId('queue-variance').textContent).toContain('0% vs 7-day Avg');
  });

  it('handles division-by-zero safely when baseline is 0 or null', () => {
    // Baseline 0 with anchored > 0 -> +100%
    const zeroBaselineAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        congestion: {
          ...mockAssessmentLow.metrics.congestion,
          anchorageQueueCount: 5,
          rolling30dAvgQueue: 0,
        },
      },
    };
    const { rerender } = render(
      <PortCard port={mockPortRotterdam} assessment={zeroBaselineAssessment} />
    );
    expect(screen.getByTestId('queue-variance').textContent).toContain('+100% vs 7-day Avg');

    // Baseline null -> N/A
    const nullBaselineAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        congestion: {
          ...mockAssessmentLow.metrics.congestion,
          anchorageQueueCount: 5,
          rolling30dAvgQueue: null as any,
        },
      },
    };
    rerender(<PortCard port={mockPortRotterdam} assessment={nullBaselineAssessment} />);
    expect(screen.getByTestId('queue-variance').textContent).toContain('N/A — Collecting Baseline');
  });

  it('renders Depth N/A badge when depth is unavailable or missing', () => {
    const missingDepthAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        navigational: {
          ...mockAssessmentLow.metrics.navigational,
          channelDepthM: null as any,
          isDepthAvailable: false,
        } as any,
      },
    };
    render(<PortCard port={mockPortRotterdam} assessment={missingDepthAssessment} />);
    expect(screen.getByTestId('depth-na-badge').textContent).toContain('Depth N/A');
  });

  it('renders negative UKC margin in high-risk red text', () => {
    const draftExceedanceAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      metrics: {
        ...mockAssessmentLow.metrics,
        navigational: {
          ...mockAssessmentLow.metrics.navigational,
          underKeelClearanceM: -0.8,
        },
      },
    };
    render(<PortCard port={mockPortRotterdam} assessment={draftExceedanceAssessment} />);
    const ukc = screen.getByTestId('ukc-margin');
    expect(ukc.textContent).toBe('-0.8m UKC');
    expect(ukc.className).toContain('text-red-600');
  });

  it('renders pulsing cold-start indicator during AIS ping accumulation', () => {
    const coldStartAssessment: RiskAssessment = {
      ...mockAssessmentLow,
      isColdStart: true,
    } as any;
    render(<PortCard port={mockPortRotterdam} assessment={coldStartAssessment} />);
    expect(screen.getByTestId('cold-start-indicator')).toHaveTextContent(
      'Initializing Live Traffic (Collecting AIS Pings)...'
    );
  });
});

describe('PortList Component and Grid Grouping', () => {
  it('renders centered empty state with + Add First Port to Watchlist button', () => {
    const onAddFirstPort = vi.fn();
    render(
      <PortList
        ports={[]}
        assessments={new Map()}
        onSelectPort={vi.fn()}
        loading={false}
        onAddFirstPort={onAddFirstPort}
      />
    );

    expect(screen.getByTestId('empty-port-state')).toBeInTheDocument();
    const btn = screen.getByTestId('add-first-port-button');
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);
    expect(onAddFirstPort).toHaveBeenCalledTimes(1);
  });

  it('groups multiple port cards by vessel class with distinct headers and counts', () => {
    const port1: Port = { ...mockPortRotterdam, id: 'port-1', vesselClass: 'vlcc' } as any;
    const port2: Port = { ...mockPortRotterdam, id: 'port-2', name: 'Port of Singapore', vesselClass: 'vlcc' } as any;
    const port3: Port = { ...mockPortRotterdam, id: 'port-3', name: 'Port of Antwerp', vesselClass: 'neoPanamax' } as any;

    const assessments = new Map<string, RiskAssessment>();
    assessments.set('port-1', { ...mockAssessmentLow, portId: 'port-1', vesselClass: 'vlcc' });
    assessments.set('port-2', { ...mockAssessmentLow, portId: 'port-2', vesselClass: 'vlcc' });
    assessments.set('port-3', { ...mockAssessmentLow, portId: 'port-3', vesselClass: 'neoPanamax' });

    render(
      <PortList
        ports={[port1, port2, port3]}
        assessments={assessments}
        onSelectPort={vi.fn()}
        loading={false}
      />
    );

    // VLCC group
    expect(screen.getByTestId('vessel-group-vlcc')).toBeInTheDocument();
    expect(screen.getByTestId('vessel-group-count-vlcc').textContent).toContain('2 Ports');

    // Neo-Panamax group
    expect(screen.getByTestId('vessel-group-neoPanamax')).toBeInTheDocument();
    expect(screen.getByTestId('vessel-group-count-neoPanamax').textContent).toContain('1 Port');

    // 3 cards in total
    expect(screen.getByTestId('port-card-port-1')).toBeInTheDocument();
    expect(screen.getByTestId('port-card-port-2')).toBeInTheDocument();
    expect(screen.getByTestId('port-card-port-3')).toBeInTheDocument();
  });

  it('renders separate cards for multiple subscriptions to the same port across different vessel classes', () => {
    const subVlcc: Port = { ...mockPortRotterdam, id: 'sub-1', name: 'Port of Rotterdam', vesselClass: 'vlcc' } as any;
    const subHandy: Port = { ...mockPortRotterdam, id: 'sub-2', name: 'Port of Rotterdam', vesselClass: 'handysize' } as any;

    const assessments = new Map<string, RiskAssessment>();
    assessments.set('sub-1', { ...mockAssessmentLow, portId: 'sub-1', vesselClass: 'vlcc' });
    assessments.set('sub-2', { ...mockAssessmentLow, portId: 'sub-2', vesselClass: 'handysize' });

    render(
      <PortList
        ports={[subVlcc, subHandy]}
        assessments={assessments}
        onSelectPort={vi.fn()}
        loading={false}
      />
    );

    expect(screen.getByTestId('vessel-group-vlcc')).toBeInTheDocument();
    expect(screen.getByTestId('vessel-group-handysize')).toBeInTheDocument();

    expect(screen.getByTestId('port-card-sub-1')).toBeInTheDocument();
    expect(screen.getByTestId('port-card-sub-2')).toBeInTheDocument();
  });
});
