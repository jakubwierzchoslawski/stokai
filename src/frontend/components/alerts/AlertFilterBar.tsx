/**
 * AlertFilterBar — filter controls for the Alerts Center list.
 *
 * Provides: status dropdown, action signal dropdown, date range picker.
 * Calls onFilterChange on any change.
 *
 * PLAN-F-025 TASK-009
 */
import React from 'react';
import type { AlertFilters } from '../../hooks/useAlerts';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'dispatched', label: 'Dispatched' },
  { value: 'suppressed_daily_limit', label: 'Suppressed (daily limit)' },
  { value: 'suppressed_quiet_hours', label: 'Suppressed (quiet hours)' },
  { value: 'suppressed_dedup', label: 'Suppressed (dedup)' },
  { value: 'suppressed_budget', label: 'Suppressed (budget)' },
  { value: 'suppressed_ticker_interval', label: 'Suppressed (ticker interval)' },
];

const ACTION_SIGNAL_OPTIONS = [
  { value: '', label: 'All signals' },
  { value: 'HOLD', label: 'HOLD' },
  { value: 'WATCH', label: 'WATCH' },
  { value: 'BUY_OPP', label: 'BUY_OPP' },
  { value: 'REDUCE_RISK', label: 'REDUCE_RISK' },
  { value: 'HEDGE', label: 'HEDGE' },
  { value: 'CONTRARIAN', label: 'CONTRARIAN' },
];

export interface AlertFilterBarProps {
  filters: AlertFilters;
  onFilterChange: (updated: AlertFilters) => void;
}

export function AlertFilterBar({ filters, onFilterChange }: AlertFilterBarProps): React.ReactElement {
  function handleStatus(e: React.ChangeEvent<HTMLSelectElement>) {
    onFilterChange({ ...filters, status: e.target.value || undefined, page: 1 });
  }

  function handleSignal(e: React.ChangeEvent<HTMLSelectElement>) {
    onFilterChange({ ...filters, action_signal: e.target.value || undefined, page: 1 });
  }

  function handleDateFrom(e: React.ChangeEvent<HTMLInputElement>) {
    onFilterChange({ ...filters, date_from: e.target.value || undefined, page: 1 });
  }

  function handleDateTo(e: React.ChangeEvent<HTMLInputElement>) {
    onFilterChange({ ...filters, date_to: e.target.value || undefined, page: 1 });
  }

  return (
    // Mobile-first: dropdowns use w-full at base (block on mobile) — PLAN-N-014 TASK-007
    <div
      className="alert-filter-bar"
      data-testid="alert-filter-bar"
      style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}
    >
      <label className="alert-filter-bar__label" htmlFor="alert-filter-status">
        Status
      </label>
      {/* w-full at base for mobile layout */}
      <select
        id="alert-filter-status"
        value={filters.status ?? ''}
        onChange={handleStatus}
        data-testid="status-filter"
        style={{ width: '100%' }}
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      <label className="alert-filter-bar__label" htmlFor="alert-filter-signal">
        Action Signal
      </label>
      <select
        id="alert-filter-signal"
        value={filters.action_signal ?? ''}
        onChange={handleSignal}
        data-testid="action-signal-filter"
        style={{ width: '100%' }}
      >
        {ACTION_SIGNAL_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      <label className="alert-filter-bar__label" htmlFor="alert-filter-date-from">
        From
      </label>
      <input
        id="alert-filter-date-from"
        type="datetime-local"
        value={filters.date_from ?? ''}
        onChange={handleDateFrom}
        data-testid="date-from-filter"
        style={{ width: '100%' }}
      />

      <label className="alert-filter-bar__label" htmlFor="alert-filter-date-to">
        To
      </label>
      <input
        id="alert-filter-date-to"
        type="datetime-local"
        value={filters.date_to ?? ''}
        onChange={handleDateTo}
        data-testid="date-to-filter"
        style={{ width: '100%' }}
      />
    </div>
  );
}

export default AlertFilterBar;
