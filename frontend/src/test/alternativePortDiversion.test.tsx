import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AlternativePortDiversion } from '@/components/AlternativePortDiversion';
import type { AlternativePortRecommendation } from '@/types';

const mockCandidates: AlternativePortRecommendation[] = [
  {
    portId: 'port-wilhelmshaven',
    unlocode: 'DEWVN',
    portName: 'Port of Wilhelmshaven',
    country: 'Germany',
    distanceNm: 140.0,
    channelDepthM: 18.5,
    depthMarginM: 3.0,
    swellHeightM: 1.2,
    riskTier: 'low',
    trafficStatus: '4 anchored / 2 underway',
  },
  {
    portId: 'port-antwerp',
    unlocode: 'BEANR',
    portName: 'Port of Antwerp-Bruges',
    country: 'Belgium',
    distanceNm: 60.0,
    channelDepthM: 16.0,
    depthMarginM: 0.5,
    swellHeightM: 0.8,
    riskTier: 'medium',
  },
  {
    portId: 'port-zeebrugge',
    unlocode: 'BEZEE',
    portName: 'Port of Zeebrugge',
    country: 'Belgium',
    distanceNm: 75.0,
    channelDepthM: 17.0,
    depthMarginM: 1.5,
    swellHeightM: 1.0,
    riskTier: 'low',
  },
  {
    portId: 'port-hamburg',
    unlocode: 'DEHAM',
    portName: 'Port of Hamburg',
    country: 'Germany',
    distanceNm: 220.0,
    channelDepthM: 15.5,
    depthMarginM: 0.0,
    swellHeightM: 1.5,
    riskTier: 'medium',
  },
  {
    portId: 'port-bremerhaven',
    unlocode: 'DEBRV',
    portName: 'Port of Bremerhaven',
    country: 'Germany',
    distanceNm: 190.0,
    channelDepthM: 16.5,
    depthMarginM: 1.0,
    swellHeightM: 1.4,
    riskTier: 'low',
  },
];

describe('AlternativePortDiversion Component', () => {
  it('returns null / is completely hidden when compositeTier is low', () => {
    const { container } = render(
      <AlternativePortDiversion compositeTier="low" alternatives={mockCandidates} />
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('alternative-port-diversion')).not.toBeInTheDocument();
  });

  it('returns null / is completely hidden when compositeTier is medium', () => {
    const { container } = render(
      <AlternativePortDiversion compositeTier="medium" alternatives={mockCandidates} />
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('alternative-port-diversion')).not.toBeInTheDocument();
  });

  it('renders inline alternative diversion section when compositeTier is high', () => {
    render(
      <AlternativePortDiversion compositeTier="high" alternatives={mockCandidates} />
    );
    expect(screen.getByTestId('alternative-port-diversion')).toBeInTheDocument();
    expect(
      screen.getByText(/Alternative Port Recommendations/i)
    ).toBeInTheDocument();
  });

  it('strictly caps candidate list at top 3 sorted by proximity distance ascending', () => {
    render(
      <AlternativePortDiversion compositeTier="high" alternatives={mockCandidates} />
    );

    // Candidates in order of distance should be: Antwerp (60nm), Zeebrugge (75nm), Wilhelmshaven (140nm)
    expect(screen.getByTestId('alternative-candidate-port-antwerp')).toBeInTheDocument();
    expect(screen.getByTestId('alternative-candidate-port-zeebrugge')).toBeInTheDocument();
    expect(screen.getByTestId('alternative-candidate-port-wilhelmshaven')).toBeInTheDocument();

    // 4th and 5th candidates (Bremerhaven 190nm, Hamburg 220nm) must be excluded by top-3 cap
    expect(
      screen.queryByTestId('alternative-candidate-port-bremerhaven')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('alternative-candidate-port-hamburg')
    ).not.toBeInTheDocument();
  });

  it('correctly displays candidate port attributes, formatting, and unit labels', () => {
    render(
      <AlternativePortDiversion
        compositeTier="high"
        alternatives={[mockCandidates[0]]}
      />
    );

    // Name & UN/LOCODE
    expect(
      screen.getByText('Port of Wilhelmshaven (DEWVN)')
    ).toBeInTheDocument();

    // Proximity Distance
    expect(screen.getByTestId('candidate-distance')).toHaveTextContent('140.0 NM');

    // Risk badge
    expect(screen.getByTestId('candidate-risk-badge')).toHaveTextContent('LOW RISK');

    // Channel depth and margin
    const depthMargin = screen.getByTestId('candidate-depth-margin');
    expect(depthMargin).toHaveTextContent('18.5m Depth / +3.0m Margin');

    // Swell height
    expect(screen.getByTestId('candidate-swell')).toHaveTextContent('1.2m Swell');

    // Traffic status
    expect(screen.getByTestId('candidate-traffic')).toHaveTextContent(
      '4 anchored / 2 underway'
    );
  });

  it('styles negative depth margin in high-risk red text and formats zero margin with +', () => {
    const candidateNegativeMargin: AlternativePortRecommendation = {
      portId: 'port-shallow',
      unlocode: 'XXSHA',
      portName: 'Port of Shallow Water',
      country: 'Testland',
      distanceNm: 50.0,
      channelDepthM: 14.0,
      depthMarginM: -0.5,
      swellHeightM: 1.0,
      riskTier: 'medium',
    };

    const { rerender } = render(
      <AlternativePortDiversion
        compositeTier="high"
        alternatives={[candidateNegativeMargin]}
      />
    );

    const marginElem = screen.getByText('-0.5m Margin');
    expect(marginElem).toBeInTheDocument();
    expect(marginElem.className).toContain('text-red-600');

    // Test zero margin
    const candidateZeroMargin: AlternativePortRecommendation = {
      ...candidateNegativeMargin,
      depthMarginM: 0.0,
    };
    rerender(
      <AlternativePortDiversion
        compositeTier="high"
        alternatives={[candidateZeroMargin]}
      />
    );

    expect(screen.getByText('+0.0m Margin')).toBeInTheDocument();
  });

  it('renders gracefully when exactly 1 or 2 candidates are provided', () => {
    const twoCandidates = mockCandidates.slice(0, 2);
    render(
      <AlternativePortDiversion compositeTier="high" alternatives={twoCandidates} />
    );

    expect(
      screen.getByTestId('alternative-candidate-port-antwerp')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('alternative-candidate-port-wilhelmshaven')
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('no-alternatives-alert')
    ).not.toBeInTheDocument();
  });

  it('renders empty advisory badge when alternatives is empty []', () => {
    render(<AlternativePortDiversion compositeTier="high" alternatives={[]} />);

    const alert = screen.getByTestId('no-alternatives-alert');
    expect(alert).toBeInTheDocument();
    expect(alert.textContent).toBe(
      'No viable alternative ports found in region meeting vessel draft requirements'
    );
  });

  it('renders empty advisory badge when alternatives is null or undefined', () => {
    const { rerender } = render(
      <AlternativePortDiversion compositeTier="high" alternatives={null} />
    );
    expect(screen.getByTestId('no-alternatives-alert')).toHaveTextContent(
      'No viable alternative ports found in region meeting vessel draft requirements'
    );

    rerender(
      <AlternativePortDiversion compositeTier="high" alternatives={undefined} />
    );
    expect(screen.getByTestId('no-alternatives-alert')).toHaveTextContent(
      'No viable alternative ports found in region meeting vessel draft requirements'
    );
  });

  it('invokes onSelectAlternative callback when a candidate card is clicked', () => {
    const onSelect = vi.fn();
    render(
      <AlternativePortDiversion
        compositeTier="high"
        alternatives={[mockCandidates[0]]}
        onSelectAlternative={onSelect}
      />
    );

    fireEvent.click(
      screen.getByTestId('alternative-candidate-port-wilhelmshaven')
    );
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('port-wilhelmshaven');
  });

  it('ensures no drawer or flyout panel elements are present in the DOM', () => {
    const { container } = render(
      <AlternativePortDiversion compositeTier="high" alternatives={mockCandidates} />
    );

    // Verify no drawer or modal backdrop elements
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector('.drawer')).toBeNull();
    expect(container.querySelector('.flyout')).toBeNull();
    expect(container.querySelector('.modal')).toBeNull();
  });
});
