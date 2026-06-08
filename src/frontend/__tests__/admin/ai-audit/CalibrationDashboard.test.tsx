/**
 * Tests for CalibrationDashboard component and useCalibration hook.
 *
 * PLAN-F-029 TASK-010
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const MOCK_SERIES = [
  {
    result_id: 'r1',
    action_signal: 'HOLD',
    window_days: 30,
    corr_confidence_actual: 0.42,
    direction_correct_pct: 0.65,
    mean_confidence: 0.72,
    total_recommendations: 100,
    computed_at: '2026-05-05T00:00:00Z',
    below_threshold: false,
  },
];

const MOCK_SUMMARY_ABOVE = {
  window_days: 30,
  below_threshold: false,
  threshold: 0.3,
  per_signal_accuracy: [
    {
      action_signal: 'HOLD',
      direction_correct_pct: 0.65,
      mean_confidence: 0.72,
      total_recommendations: 100,
    },
  ],
  computed_at: '2026-06-04T00:00:00Z',
};

const MOCK_SUMMARY_BELOW = {
  ...MOCK_SUMMARY_ABOVE,
  below_threshold: true,
};

describe('CalibrationDashboard', () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  function setupMocks(summary: typeof MOCK_SUMMARY_ABOVE) {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: MOCK_SERIES, error: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: summary, error: null }),
      } as Response);
  }

  it('renders warning banner when below_threshold=true', async () => {
    setupMocks(MOCK_SUMMARY_BELOW);
    const { CalibrationDashboard } = await import('../../../pages/admin/ai-audit/CalibrationDashboard');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(CalibrationDashboard)));

    await waitFor(() => {
      expect(screen.getByTestId('below-threshold-banner')).toBeDefined();
    });
  });

  it('does NOT render warning banner when below_threshold=false', async () => {
    setupMocks(MOCK_SUMMARY_ABOVE);
    const { CalibrationDashboard } = await import('../../../pages/admin/ai-audit/CalibrationDashboard');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(CalibrationDashboard)));

    await waitFor(() => {
      expect(screen.getByTestId('per-signal-table')).toBeDefined();
    });
    expect(screen.queryByTestId('below-threshold-banner')).toBeNull();
  });

  it('renders per-signal accuracy table with one row per signal', async () => {
    setupMocks(MOCK_SUMMARY_ABOVE);
    const { CalibrationDashboard } = await import('../../../pages/admin/ai-audit/CalibrationDashboard');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(CalibrationDashboard)));

    await waitFor(() => {
      expect(screen.getByTestId('signal-row-HOLD')).toBeDefined();
    });
  });

  it('selecting 60 days triggers new fetch with days=60', async () => {
    setupMocks(MOCK_SUMMARY_ABOVE);
    // Set up mocks for the second fetch (days=60)
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [], error: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: MOCK_SUMMARY_ABOVE, error: null }),
      } as Response);

    const { CalibrationDashboard } = await import('../../../pages/admin/ai-audit/CalibrationDashboard');
    const Wrapper = makeWrapper();
    render(React.createElement(Wrapper, null, React.createElement(CalibrationDashboard)));

    // Wait for initial load
    await waitFor(() => screen.getByTestId('lookback-60'));

    fireEvent.click(screen.getByTestId('lookback-60'));

    await waitFor(() => {
      // Should have fetched with days=60
      const calls = mockFetch.mock.calls.map((c) => c[0] as string);
      expect(calls.some((url) => url.includes('days=60'))).toBe(true);
    });
  });
});
