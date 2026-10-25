import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RiskBadge } from '@/components/RiskBadge';

describe('RiskBadge', () => {
  it('renders the correct label for low tier', () => {
    render(<RiskBadge tier="low" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('renders the correct label for medium tier', () => {
    render(<RiskBadge tier="medium" />);
    expect(screen.getByText('Medium')).toBeInTheDocument();
  });

  it('renders the correct label for high tier', () => {
    render(<RiskBadge tier="high" />);
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('hides label when showLabel is false', () => {
    const { container } = render(<RiskBadge tier="low" showLabel={false} />);
    expect(container.textContent).not.toContain('Low');
  });
});
