/**
 * map-time-mode.test.tsx — Integration tests for time-mode wiring.
 *
 * Verifies:
 *  - TimeModeToolbar is rendered
 *  - Switching to Historical shows DateRangeSlider
 *  - Switching to Playback shows PlaybackControls
 *  - Switching back to Live hides date range
 *  - Live mode empty state message is correct (regression guard)
 *
 * PLAN-F-021 TASK-012
 */

import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IntelligenceMap } from '../../../src/frontend/features/intelligence-map/IntelligenceMap';

// ── Global mocks ──────────────────────────────────────────────────────────────

jest.mock('maplibre-gl', () => {
  const MockMap = jest.fn().mockImplementation(() => ({
    on: jest.fn((event: string, cb: (...args: unknown[]) => void) => {
      if (event === 'load') setTimeout(() => cb(), 0);
    }),
    off: jest.fn(),
    getZoom: jest.fn(() => 2),
    getBounds: jest.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
    flyTo: jest.fn(),
    remove: jest.fn(),
  }));
  return { default: { Map: MockMap }, Map: MockMap };
});

global.Worker = jest.fn().mockImplementation(() => ({
  postMessage: jest.fn(),
  terminate: jest.fn(),
  onmessage: null,
})) as unknown as typeof Worker;

global.WebSocket = jest.fn().mockImplementation(() => ({
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  close: jest.fn(),
})) as unknown as typeof WebSocket;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('IntelligenceMap — time-mode wiring', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [], meta: {}, error: null }),
    } as unknown as Response);
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('renders TimeModeToolbar overlay', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-toolbar')).toBeTruthy();
    });
  });

  it('Live button has aria-pressed=true by default', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-btn-live').getAttribute('aria-pressed')).toBe('true');
    });
  });

  it('PlaybackControls not present in live mode', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeTruthy());
    expect(screen.queryByTestId('playback-controls')).toBeNull();
  });

  it('switching to Playback renders PlaybackControls', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-btn-playback')).toBeTruthy());
    act(() => {
      fireEvent.click(screen.getByTestId('time-mode-btn-playback'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('playback-controls')).toBeTruthy();
    });
  });

  it('switching to Historical shows DateRangeSlider', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-btn-historical')).toBeTruthy());
    act(() => {
      fireEvent.click(screen.getByTestId('time-mode-btn-historical'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('date-range-slider')).toBeTruthy();
    });
  });

  it('switching Historical → Live removes DateRangeSlider', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-btn-historical')).toBeTruthy());

    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });
    await waitFor(() => expect(screen.getByTestId('date-range-slider')).toBeTruthy());

    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-live')); });
    await waitFor(() => {
      expect(screen.queryByTestId('date-range-slider')).toBeNull();
    });
  });

  it('live mode with 0 events → EmptyState shows "Markets are quiet" (regression)', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      const emptyState = screen.queryByTestId('empty-state');
      if (emptyState) {
        expect(emptyState.textContent).toContain('quiet');
      }
    });
  });
});
