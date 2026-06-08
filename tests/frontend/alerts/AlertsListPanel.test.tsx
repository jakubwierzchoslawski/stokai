import { describe, it, expect, vi } from 'vitest';
/**
 * Tests for AlertsListPanel, AlertListRow, AlertFilterBar.
 *
 * PLAN-F-025 TASK-009
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { AlertListRow } from '../../../src/frontend/components/alerts/AlertListRow';
import { AlertFilterBar } from '../../../src/frontend/components/alerts/AlertFilterBar';
import { AlertsListPanel } from '../../../src/frontend/components/alerts/AlertsListPanel';

// Mock useAlerts hook
vi.mock('../../../src/frontend/hooks/useAlerts', () => ({
  useAlerts: vi.fn(),
}));


// Mock TanStack Query
vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
  useMutation: vi.fn(),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  QueryClient: vi.fn(),
  QueryClientProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// â”€â”€ buildEventLink â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import { buildEventLink } from '../../../src/frontend/lib/alertDeepLink';

describe('buildEventLink', () => {
  it('returns correct URL for given event_id, lat, lon', () => {
    expect(buildEventLink('abc', 1.0, 2.0)).toBe('/map?event=abc&lat=1&lon=2');
  });
});

// â”€â”€ AlertListRow â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const baseItem = {
  alert_id: 'a1',
  occurred_at: '2026-01-10T09:00:00Z',
  event_title: 'US Trade Policy Shift',
  action_signal: 'BUY_OPP',
  confidence: 0.82,
  channel: 'email',
  status: 'dispatched',
  event_link: '/map?event=e1&lat=38.9&lon=-77.0',
  report_link: null,
};

describe('AlertListRow', () => {
  it('renders event title as link with correct href', () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={baseItem} />
        </tbody>
      </table>
    );
    const link = screen.getByTestId('event-link');
    expect(link).toHaveAttribute('href', '/map?event=e1&lat=38.9&lon=-77.0');
    expect(link).toHaveTextContent('US Trade Policy Shift');
  });

  it('shows report_link anchor when report_link is non-null', () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={{ ...baseItem, report_link: '/reports/r1' }} />
        </tbody>
      </table>
    );
    const reportLink = screen.getByTestId('report-link');
    expect(reportLink).toBeInTheDocument();
    expect(reportLink).toHaveAttribute('href', '/reports/r1');
  });

  it('does not render report link when report_link is null', () => {
    render(
      <table>
        <tbody>
          <AlertListRow item={{ ...baseItem, report_link: null }} />
        </tbody>
      </table>
    );
    expect(screen.queryByTestId('report-link')).toBeNull();
  });
});

// â”€â”€ AlertFilterBar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('AlertFilterBar', () => {
  it('calls onFilterChange when status dropdown changes', () => {
    const onFilterChange = vi.fn();
    render(
      <AlertFilterBar filters={{}} onFilterChange={onFilterChange} />
    );
    const select = screen.getByTestId('status-filter');
    fireEvent.change(select, { target: { value: 'dispatched' } });
    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'dispatched' })
    );
  });

  it('calls onFilterChange when action signal dropdown changes', () => {
    const onFilterChange = vi.fn();
    render(
      <AlertFilterBar filters={{}} onFilterChange={onFilterChange} />
    );
    const select = screen.getByTestId('action-signal-filter');
    fireEvent.change(select, { target: { value: 'WATCH' } });
    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ action_signal: 'WATCH' })
    );
  });
});

// â”€â”€ AlertsListPanel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('AlertsListPanel', () => {
  it('shows loading skeleton while useAlerts is loading', () => {
    useAlerts.mockReturnValue({ isLoading: true, isError: false, data: undefined });
    render(<AlertsListPanel />);
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument();
  });

  it('shows empty-state message when items is empty', () => {
    useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0, page: 1, page_size: 20, has_next: false },
    });
    render(<AlertsListPanel />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  it('renders one AlertListRow per item in the response', () => {
    useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          { ...baseItem, alert_id: 'a1' },
          { ...baseItem, alert_id: 'a2' },
          { ...baseItem, alert_id: 'a3' },
        ],
        total: 3,
        page: 1,
        page_size: 20,
        has_next: false,
      },
    });
    render(<AlertsListPanel />);
    const rows = screen.getAllByTestId('alert-list-row');
    expect(rows).toHaveLength(3);
  });

  it('clicking "Next" page control increments the page parameter', () => {
    useAlerts.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [{ ...baseItem }],
        total: 25,
        page: 1,
        page_size: 20,
        has_next: true,
      },
    });
    render(<AlertsListPanel />);
    const nextBtn = screen.getByTestId('next-page');
    fireEvent.click(nextBtn);
    // After clicking next, useAlerts should be called with page=2
    const lastCall = useAlerts.mock.calls[useAlerts.mock.calls.length - 1][0];
    expect(lastCall.page).toBe(2);
  });
});
