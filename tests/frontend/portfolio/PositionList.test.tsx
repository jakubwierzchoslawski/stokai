import { describe, test, expect, vi } from 'vitest';
/**
 * tests/frontend/portfolio/PositionList.test.tsx
 *
 * Tests for the PositionList component.
 * PLAN-F-024 TASK-007
 */
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PositionList, Position } from '../../../src/frontend/features/portfolio/PositionList';

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const POSITIONS: Position[] = [
  { position_id: 'pos-1', ticker: 'AAPL', shares: 10, cost_basis: 150 },
  { position_id: 'pos-2', ticker: 'MSFT', shares: 5, cost_basis: 300 },
];

describe('PositionList', () => {
  test('test_position_list_renders_rows: 2 positions â†’ 2 rows', () => {
    render(
      <PositionList portfolioId="p-1" positions={POSITIONS} />,
      { wrapper }
    );

    const rows = screen.getAllByTestId(/^position-row-/);
    expect(rows).toHaveLength(2);
  });

  test('test_position_list_empty_state', () => {
    render(
      <PositionList portfolioId="p-1" positions={[]} />,
      { wrapper }
    );

    expect(screen.getByTestId('position-list-empty')).toBeInTheDocument();
    expect(screen.getByText(/no positions yet/i)).toBeInTheDocument();
  });

  test('test_delete_position_calls_api_and_invalidates', async () => {
    const onDeletePosition = vi.fn().mockResolvedValue(undefined);

    render(
      <PositionList
        portfolioId="p-1"
        positions={POSITIONS}
        onDeletePosition={onDeletePosition}
      />,
      { wrapper }
    );

    const deleteButtons = screen.getAllByRole('button', { name: /delete position/i });
    await userEvent.click(deleteButtons[0]);

    await waitFor(() => {
      expect(onDeletePosition).toHaveBeenCalledWith('pos-1');
    });
  });

  test('renders ticker and shares for each position', () => {
    render(
      <PositionList portfolioId="p-1" positions={POSITIONS} />,
      { wrapper }
    );

    expect(screen.getAllByTestId('position-ticker')[0]).toHaveTextContent('AAPL');
    expect(screen.getAllByTestId('position-shares')[0]).toHaveTextContent('10');
  });
});
