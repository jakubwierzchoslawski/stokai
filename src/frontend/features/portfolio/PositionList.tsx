/**
 * features/portfolio/PositionList — displays positions for a portfolio.
 *
 * Shows: Ticker, Shares, Avg Cost, Current Value (—), P&L (—).
 * Each row has a Delete action that invalidates the portfolio query.
 * Empty state: "No positions yet. Add your first holding."
 *
 * PLAN-F-024 TASK-007
 */
import React from 'react';
import { useMutation } from '@tanstack/react-query';

import { usePortfolioContext } from '../../hooks/usePortfolioContext';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Position {
  position_id: string;
  ticker: string;
  shares: number;
  cost_basis: number | null;
}

export interface PositionListProps {
  portfolioId: string;
  positions: Position[];
  onDeletePosition?: (positionId: string) => Promise<void>;
}

// ── Component ──────────────────────────────────────────────────────────────────

export function PositionList({
  portfolioId,
  positions,
  onDeletePosition,
}: PositionListProps): React.ReactElement {
  const invalidatePortfolioContext = usePortfolioContext();

  async function handleDelete(positionId: string): Promise<void> {
    if (onDeletePosition) {
      await onDeletePosition(positionId);
    }
    invalidatePortfolioContext();
  }

  if (positions.length === 0) {
    return (
      <div data-testid="position-list-empty">
        <p>No positions yet. Add your first holding.</p>
      </div>
    );
  }

  return (
    <table data-testid="position-list">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Shares</th>
          <th>Avg Cost</th>
          <th>Current Value</th>
          <th>P&amp;L</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((position) => (
          <tr key={position.position_id} data-testid={`position-row-${position.position_id}`}>
            <td data-testid="position-ticker">{position.ticker}</td>
            <td data-testid="position-shares">{position.shares}</td>
            <td data-testid="position-cost">
              {position.cost_basis !== null && position.cost_basis !== undefined
                ? `$${position.cost_basis.toFixed(2)}`
                : '—'}
            </td>
            <td data-testid="position-current-value">—</td>
            <td data-testid="position-pnl">—</td>
            <td>
              <button
                type="button"
                aria-label={`Delete position ${position.ticker}`}
                onClick={() => handleDelete(position.position_id)}
              >
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default PositionList;
