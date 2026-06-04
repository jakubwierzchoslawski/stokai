/**
 * tests/frontend/portfolio/PortfolioCard.test.tsx
 *
 * Tests for the PortfolioCard component.
 * PLAN-F-024 TASK-007
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PortfolioCard, PositionSummary } from '../../../src/frontend/features/portfolio/PortfolioCard';

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const POSITIONS: PositionSummary[] = [
  { position_id: 'pos-1', ticker: 'AAPL', shares: 10, cost_basis: 150 },
  { position_id: 'pos-2', ticker: 'MSFT', shares: 5, cost_basis: 300 },
];

describe('PortfolioCard', () => {
  test('test_portfolio_card_renders_name_and_position_count', () => {
    render(
      <PortfolioCard
        portfolioId="p-1"
        name="My Portfolio"
        positions={POSITIONS}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('portfolio-name')).toHaveTextContent('My Portfolio');
    expect(screen.getByTestId('position-count')).toHaveTextContent('2 positions');
  });

  test('renders total cost basis correctly', () => {
    // AAPL: 10 * 150 = 1500, MSFT: 5 * 300 = 1500, total = 3000
    render(
      <PortfolioCard
        portfolioId="p-1"
        name="My Portfolio"
        positions={POSITIONS}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('total-cost-basis')).toHaveTextContent('$3000.00');
  });

  test('calls onDelete when delete button clicked', async () => {
    const onDelete = jest.fn();
    render(
      <PortfolioCard
        portfolioId="p-1"
        name="My Portfolio"
        positions={POSITIONS}
        onDelete={onDelete}
      />,
      { wrapper }
    );

    await userEvent.click(screen.getByRole('button', { name: /delete portfolio/i }));
    expect(onDelete).toHaveBeenCalledWith('p-1');
  });

  test('renders singular position count for one position', () => {
    render(
      <PortfolioCard
        portfolioId="p-1"
        name="Solo"
        positions={[POSITIONS[0]]}
      />,
      { wrapper }
    );

    expect(screen.getByTestId('position-count')).toHaveTextContent('1 position');
  });
});
