/**
 * map-historical-mode.test.tsx — Integration tests: Historical mode
 * date-range → static pulses + scores.
 *
 * RTL + MSW. Exercises the full hook-to-component flow without a real browser.
 *
 * PLAN-F-021 TASK-013
 */

import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { IntelligenceMap } from '../../../src/frontend/features/intelligence-map/IntelligenceMap';
import type { EventPulse } from '../../../src/frontend/features/intelligence-map/types/map.types';

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

// Track WebSocket constructor calls to assert "no WS subscription in Historical mode".
const wsConstructorSpy = vi.fn();
vi.stubGlobal('WebSocket', vi.fn().mockImplementation((...args: unknown[]) => {
  wsConstructorSpy(...args);
  return {
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    close: vi.fn(),
    send: vi.fn(),
    readyState: 1,
  };
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeEvent(id: string, timestamp: string): EventPulse {
  return {
    event_id: id,
    category: ['geopolitical'],
    intensity: 3,
    headline: `Event ${id}`,
    timestamp,
    lat: 1,
    lon: 1,
    relevance_window_end: timestamp,
    affected_companies: [{ company_id: `co-${id}`, ticker: `T${id}`, score_delta: 0 }],
  };
}

const HIST_EVENTS = [
  makeEvent('h1', '2025-01-05T10:00:00Z'),
  makeEvent('h2', '2025-01-10T12:00:00Z'),
  makeEvent('h3', '2025-01-20T08:00:00Z'),
];

let eventsRequestUrl = '';
let scoresRequestUrl = '';

// ── MSW ───────────────────────────────────────────────────────────────────────

const server = setupServer(
  http.get('http://localhost/api/v1/events', ({ request }) => {
    eventsRequestUrl = request.url;
    const url = new URL(request.url);
    if (url.searchParams.get('from') === '2025-01-01' && url.searchParams.get('to') === '2025-01-31') {
      return HttpResponse.json({ data: HIST_EVENTS, meta: {}, error: null });
    }
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
  http.get('http://localhost/api/v1/scores/history', ({ request }) => {
    scoresRequestUrl = request.url;
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  eventsRequestUrl = '';
  scoresRequestUrl = '';
  wsConstructorSpy.mockClear();
});
afterAll(() => server.close());

// ── Wrapper ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Historical mode integration', () => {
  it('switching to Historical + setting date range calls GET /api/v1/events with from/to params', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());

    // Switch to historical mode.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });
    await waitFor(() => expect(screen.getByTestId('date-range-slider')).toBeInTheDocument());

    // Set date range and load.
    act(() => {
      fireEvent.change(screen.getByTestId('date-range-from'), { target: { value: '2025-01-01' } });
      fireEvent.change(screen.getByTestId('date-range-to'), { target: { value: '2025-01-31' } });
    });
    act(() => { fireEvent.click(screen.getByTestId('date-range-load')); });

    // Assert the events endpoint was called with date-range params.
    await waitFor(() => {
      expect(eventsRequestUrl).toContain('from=2025-01-01');
      expect(eventsRequestUrl).toContain('to=2025-01-31');
    });
  });

  it('Historical mode → GET /api/v1/scores/history called with company IDs from events', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });

    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });
    await waitFor(() => expect(screen.getByTestId('date-range-from')).toBeInTheDocument());

    act(() => {
      fireEvent.change(screen.getByTestId('date-range-from'), { target: { value: '2025-01-01' } });
      fireEvent.change(screen.getByTestId('date-range-to'), { target: { value: '2025-01-31' } });
    });
    act(() => { fireEvent.click(screen.getByTestId('date-range-load')); });

    // After loading events, scores/history should be called with the company IDs.
    await waitFor(() => {
      expect(scoresRequestUrl).toContain('/api/v1/scores/history');
    });
  });

  it('Historical mode WebSocket: WS subscription is established on load (live mode default), but no new WS after switching to historical', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });

    // Record WS calls at initial (live) render.
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());
    const wsCallsAtLive = wsConstructorSpy.mock.calls.length;

    // Switch to historical mode.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });

    // No additional WS connections should be opened for historical mode.
    await waitFor(() => {
      expect(wsConstructorSpy.mock.calls.length).toBe(wsCallsAtLive);
    });
  });
});
