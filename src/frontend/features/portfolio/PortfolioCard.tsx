/**
 * features/portfolio/PortfolioCard — displays a portfolio summary card.
 *
 * Shows: name, position count, total cost basis (sum of shares * cost_basis).
 * Actions: Edit name (inline), Delete portfolio.
 *
 * PLAN-F-024 TASK-007
 */
import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { PORTFOLIO_QUERY_KEY } from '../../hooks/usePortfolioContext';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface PositionSummary {
  position_id: string;
  ticker: string;
  shares: number;
  cost_basis: number | null;
}

export interface PortfolioCardProps {
  portfolioId: string;
  name: string;
  positions: PositionSummary[];
  onDelete?: (portfolioId: string) => void;
  onRename?: (portfolioId: string, name: string) => Promise<void>;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function computeTotalCostBasis(positions: PositionSummary[]): number {
  return positions.reduce((sum, p) => {
    if (p.cost_basis === null || p.cost_basis === undefined) return sum;
    return sum + p.shares * p.cost_basis;
  }, 0);
}

// ── Component ──────────────────────────────────────────────────────────────────

export function PortfolioCard({
  portfolioId,
  name,
  positions,
  onDelete,
  onRename,
}: PortfolioCardProps): React.ReactElement {
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState(name);
  const queryClient = useQueryClient();

  const totalCostBasis = computeTotalCostBasis(positions);

  function handleDeleteClick(): void {
    if (onDelete) {
      onDelete(portfolioId);
    }
  }

  async function handleRenameSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (onRename) {
      await onRename(portfolioId, nameValue);
    }
    setEditingName(false);
    queryClient.invalidateQueries({ queryKey: PORTFOLIO_QUERY_KEY });
  }

  return (
    <div data-testid="portfolio-card" data-portfolio-id={portfolioId}>
      {editingName ? (
        <form onSubmit={handleRenameSubmit}>
          <input
            aria-label="Portfolio name"
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            autoFocus
          />
          <button type="submit">Save</button>
          <button type="button" onClick={() => setEditingName(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <h2 data-testid="portfolio-name">{name}</h2>
      )}

      <p data-testid="position-count">
        {positions.length} {positions.length === 1 ? 'position' : 'positions'}
      </p>

      <p data-testid="total-cost-basis">
        Total cost basis: ${totalCostBasis.toFixed(2)}
      </p>

      <div>
        <button
          type="button"
          aria-label="Edit portfolio name"
          onClick={() => setEditingName(true)}
        >
          Edit Name
        </button>
        <button
          type="button"
          aria-label="Delete portfolio"
          onClick={handleDeleteClick}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

export default PortfolioCard;
