import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PortList } from '@/components/PortList';
import type { Port, RiskAssessment } from '@/types';

const mockPorts: Port[] = [
  {
    id: 'port-1',
    name: 'Port of Rotterdam',
    locode: 'NLRTM',
    country: 'Netherlands',
    lat: 51.9,
    lon: 4.4,
    isDefault: false,
    geofenceRadiusNm: 8,
    addedByUserId: 'user-1',
    vesselClass: 'neoPanamax',
  },
  {
    id: 'port-2',
    name: 'Port of Rotterdam',
    locode: 'NLRTM',
    country: 'Netherlands',
    lat: 51.9,
    lon: 4.4,
    isDefault: false,
    geofenceRadiusNm: 8,
    addedByUserId: 'user-1',
    vesselClass: 'vlcc',
  },
  {
    id: 'port-3',
    name: 'Port of Singapore',
    locode: 'SGSIN',
    country: 'Singapore',
    lat: 1.3,
    lon: 103.8,
    isDefault: false,
    geofenceRadiusNm: 8,
    addedByUserId: 'user-1',
    vesselClass: 'neoPanamax',
  },
];

const mockAssessments = new Map<string, RiskAssessment>();

describe('PortList clustering and active promotion', () => {
  it('clusters subscriptions by vesselClass and pins active vessel class to the top', () => {
    const { container } = render(
      <PortList
        ports={mockPorts}
        assessments={mockAssessments}
        activeVesselClass="neoPanamax"
        onSelectPort={vi.fn()}
        loading={false}
      />
    );

    // Active Focus badge should be displayed on Neo-Panamax
    expect(screen.getByText('Active Focus')).toBeInTheDocument();

    // Check cluster headings appear in order: Neo-Panamax first, then VLCC
    const headings = container.querySelectorAll('h3');
    expect(headings[0].textContent).toContain('Neo-Panamax');
    expect(headings[1].textContent).toContain('VLCC / ULCC');

    // Both subscriptions for Rotterdam should be visible under their respective clusters
    const rotterdams = screen.getAllByText('Port of Rotterdam');
    expect(rotterdams).toHaveLength(2);
  });

  it('promotes newly selected vessel class to the top when activeVesselClass changes to vlcc', () => {
    const { container } = render(
      <PortList
        ports={mockPorts}
        assessments={mockAssessments}
        activeVesselClass="vlcc"
        onSelectPort={vi.fn()}
        loading={false}
      />
    );

    const headings = container.querySelectorAll('h3');
    // VLCC should now be first!
    expect(headings[0].textContent).toContain('VLCC / ULCC');
    expect(headings[1].textContent).toContain('Neo-Panamax');
  });

  it('shows an empty state card for active class if it has no ports yet while other clusters remain visible', () => {
    render(
      <PortList
        ports={mockPorts}
        assessments={mockAssessments}
        activeVesselClass="lng"
        onSelectPort={vi.fn()}
        loading={false}
      />
    );

    // Empty state for LNG
    expect(
      screen.getByText(/No monitored ports for LNG \/ LPG Carriers yet/i)
    ).toBeInTheDocument();

    // But existing subscriptions for Neo-Panamax and VLCC remain listed below!
    expect(screen.getAllByText('Port of Rotterdam')).toHaveLength(2);
    expect(screen.getByText('Port of Singapore')).toBeInTheDocument();
  });
});
