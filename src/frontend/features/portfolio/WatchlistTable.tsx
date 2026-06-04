/**
 * features/portfolio/WatchlistTable — displays the user's watchlist.
 *
 * Uses TanStack Query to fetch GET /api/v1/watchlist.
 * Empty state: guided prompt with "Add Company" CTA.
 * Non-empty: table showing Ticker, Company Name, Added Date, Remove action.
 * Remove: DELETE /api/v1/watchlist/{company_id}, then invalidates watchlist query.
 *
 * AC-004: Empty watchlist shows guided prompt.
 * PLAN-F-024 TASK-008
 */
import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface WatchlistItem {
  item_id: string;
  company_id: string;
  ticker: string;
  added_at: string;
}

interface WatchlistResponse {
  data: WatchlistItem[];
  meta: Record<string, unknown>;
  error: null | { code: string; message: string };
}

// ── API helpers ────────────────────────────────────────────────────────────────

async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const resp = await fetch('/api/v1/watchlist', {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  if (!resp.ok) throw new Error('Failed to load watchlist');
  const body: WatchlistResponse = await resp.json();
  return body.data;
}

async function removeWatchlistItem(companyId: string): Promise<void> {
  const resp = await fetch(`/api/v1/watchlist/${companyId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!resp.ok && resp.status !== 204) {
    throw new Error('Failed to remove watchlist item');
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

export interface WatchlistTableProps {
  onAddCompanyClick?: () => void;
}

export function WatchlistTable({ onAddCompanyClick }: WatchlistTableProps): React.ReactElement {
  const queryClient = useQueryClient();

  const { data: items = [], isLoading, isError } = useQuery<WatchlistItem[]>({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
  });

  const removeMutation = useMutation<void, Error, string>({
    mutationFn: removeWatchlistItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
  });

  if (isLoading) {
    return <div data-testid="watchlist-loading">Loading watchlist...</div>;
  }

  if (isError) {
    return <div data-testid="watchlist-error">Failed to load watchlist.</div>;
  }

  if (items.length === 0) {
    return (
      <div data-testid="watchlist-empty">
        <p>
          Add companies to see geopolitical events affecting your holdings.
        </p>
        <button
          type="button"
          data-testid="watchlist-add-cta"
          onClick={onAddCompanyClick}
        >
          Add Company
        </button>
      </div>
    );
  }

  return (
    <table data-testid="watchlist-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Company Name</th>
          <th>Added Date</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.item_id} data-testid={`watchlist-row-${item.item_id}`}>
            <td data-testid="watchlist-ticker">{item.ticker}</td>
            <td data-testid="watchlist-company-name">—</td>
            <td data-testid="watchlist-added-date">
              {new Date(item.added_at).toLocaleDateString()}
            </td>
            <td>
              <button
                type="button"
                aria-label={`Remove ${item.ticker} from watchlist`}
                disabled={removeMutation.isPending}
                onClick={() => removeMutation.mutate(item.company_id)}
              >
                Remove
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default WatchlistTable;
