/**
 * AlertsListPanel — main panel for the Alerts Center "Alerts" tab.
 *
 * Composes AlertFilterBar + list of AlertListRows + pagination controls.
 * Shows loading skeleton during fetch; shows empty state when total=0.
 *
 * PLAN-F-025 TASK-009
 */
import React, { useState } from 'react';
import { useAlerts } from '../../hooks/useAlerts';
import type { AlertFilters } from '../../hooks/useAlerts';
import { AlertFilterBar } from './AlertFilterBar';
import { AlertListRow } from './AlertListRow';

const DEFAULT_PAGE_SIZE = 20;

export function AlertsListPanel(): React.ReactElement {
  const [filters, setFilters] = useState<AlertFilters>({
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  });

  const { data, isLoading, isError } = useAlerts(filters);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const page = data?.page ?? filters.page ?? 1;
  const hasNext = data?.has_next ?? false;
  const hasPrev = page > 1;

  function handleFilterChange(updated: AlertFilters) {
    setFilters((prev) => ({ ...prev, ...updated, page: updated.page ?? 1 }));
  }

  function handlePrev() {
    setFilters((prev) => ({ ...prev, page: Math.max(1, (prev.page ?? 1) - 1) }));
  }

  function handleNext() {
    setFilters((prev) => ({ ...prev, page: (prev.page ?? 1) + 1 }));
  }

  return (
    <div className="alerts-list-panel" data-testid="alerts-list-panel">
      <AlertFilterBar filters={filters} onFilterChange={handleFilterChange} />

      {isLoading && (
        <div className="alerts-list-panel__skeleton" data-testid="loading-skeleton">
          <p>Loading alerts…</p>
        </div>
      )}

      {isError && (
        <div className="alerts-list-panel__error" data-testid="error-state">
          <p>Failed to load alerts. Please try again.</p>
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="alerts-list-panel__empty" data-testid="empty-state">
          <p>No alerts found.</p>
        </div>
      )}

      {!isLoading && !isError && items.length > 0 && (
        <table className="alerts-list-panel__table" data-testid="alerts-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Signal</th>
              <th>Confidence</th>
              <th>Channel</th>
              <th>Status</th>
              <th>Report</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <AlertListRow key={item.alert_id} item={item} />
            ))}
          </tbody>
        </table>
      )}

      {!isLoading && total > 0 && (
        <div className="alerts-list-panel__pagination" data-testid="pagination">
          <button
            onClick={handlePrev}
            disabled={!hasPrev}
            data-testid="prev-page"
            aria-label="Previous page"
          >
            Prev
          </button>
          <span className="alerts-list-panel__page-indicator" data-testid="page-indicator">
            Page {page} — {total} total
          </span>
          <button
            onClick={handleNext}
            disabled={!hasNext}
            data-testid="next-page"
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

export default AlertsListPanel;
