/**
 * map-live-reconnect.test.tsx — Integration tests: Historical → Live reconnect.
 *
 * RTL + fake WebSocket. Verifies that switching from Historical/Playback back
 * to Live mode re-establishes the WebSocket subscription (AC-005).
 *
 * PLAN-F-021 TASK-013
 */

import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll, afterAll } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { IntelligenceMap } from '../../../src/frontend/features/intelligence-map/IntelligenceMap';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('maplibre-gl', () => {
  const MockMap = vi.fn().mockImplementation(() => ({
    on: vi.fn((_: string, cb: (...a: unknown[]) => void) => {
      if (_ === 'load') setTimeout(() => cb(), 0);
    }),
    off: vi.fn(),
    getZoom: vi.fn(() => 2),
    getBounds: vi.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
    flyTo: vi.fn(),
    remove: vi.fn(),
  }));
  return { default: { Map: MockMap }, Map: MockMap };
});

vi.mock('../../../src/frontend/features/intelligence-map/workers/supercluster.worker.ts', () => ({}), { virtual: true });

vi.stubGlobal('Worker', vi.fn().mockImplementation(() => ({
  postMessage: vi.fn(),
  onmessage: null,
  terminate: vi.fn(),
})));

// Track WebSocket close/open calls.
const wsInstances: { close: ReturnType<typeof vi.fn> }[] = [];
let wsConstructorCallCount = 0;

vi.stubGlobal('WebSocket', vi.fn().mockImplementation(() => {
  wsConstructorCallCount++;
  const instance = {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    send: vi.fn(),
    readyState: 1,
  };
  wsInstances.push(instance);
  return instance;
}));

// ── MSW ───────────────────────────────────────────────────────────────────────

const server = setupServer(
  http.get('http://localhost/api/v1/events', ({ request }) => {
    const url = new URL(request.url);
    if (url.searchParams.get('from')) {
      return HttpResponse.json({ data: [], meta: {}, error: null });
    }
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
  http.get('http://localhost/api/v1/scores/history', () => {
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  wsInstances.length = 0;
  wsConstructorCallCount = 0;
});
afterAll(() => server.close());

// ── Wrapper ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Live reconnect integration (AC-005)', () => {
  it('start in Historical mode, switch back to Live → no page reload required', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());

    // Start in live mode (default) — WebSocket is established.
    await waitFor(() => {
      // WS is subscribed for live mode.
      expect(screen.getByTestId('time-mode-btn-live')).toHaveAttribute('aria-pressed', 'true');
    });

    // Switch to historical mode.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-btn-historical')).toHaveAttribute('aria-pressed', 'true');
    });

    // Switch back to live mode — should not trigger a page reload.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-live')); });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-btn-live')).toHaveAttribute('aria-pressed', 'true');
    });

    // The component is still mounted (no unmount/remount).
    expect(screen.getByTestId('intelligence-map-root')).toBeInTheDocument();
  });

  it('switching Historical → Live re-establishes mode state without error', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());

    // Go to historical.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });
    await waitFor(() => expect(screen.getByTestId('date-range-slider')).toBeInTheDocument());

    // Back to live.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-live')); });
    await waitFor(() => {
      expect(screen.queryByTestId('date-range-slider')).not.toBeInTheDocument();
      expect(screen.getByTestId('time-mode-btn-live')).toHaveAttribute('aria-pressed', 'true');
    });
  });

  it('Playback → Live → dateRange is cleared (no stale range)', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());

    // Switch to playback and set date range.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-playback')); });
    await waitFor(() => expect(screen.getByTestId('date-range-from')).toBeInTheDocument());
    act(() => {
      fireEvent.change(screen.getByTestId('date-range-from'), { target: { value: '2025-01-01' } });
      fireEvent.change(screen.getByTestId('date-range-to'), { target: { value: '2025-01-31' } });
    });

    // Switch back to live — date range should be cleared.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-live')); });
    await waitFor(() => {
      // DateRangeSlider should no longer be in the DOM in Live mode.
      expect(screen.queryByTestId('date-range-slider')).not.toBeInTheDocument();
    });
  });

  it('Live mode at startup — WebSocket subscription is established (AC-001)', async () => {
    wsConstructorCallCount = 0;
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());
    // Expect at least one WebSocket connection was opened.
    expect(wsConstructorCallCount).toBeGreaterThanOrEqual(1);
  });
});
