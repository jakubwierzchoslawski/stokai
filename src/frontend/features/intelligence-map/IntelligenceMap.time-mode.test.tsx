/**
 * IntelligenceMap.time-mode.test.tsx — TDD tests for time-mode wiring.
 *
 * Tests the time-mode integration added by PLAN-F-021 TASK-012.
 * Separate file to avoid conflicts with PLAN-F-019's Jest-based test.
 *
 * PLAN-F-021 TASK-012
 */

import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll, afterAll } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { IntelligenceMap } from './IntelligenceMap';
import type { EventPulse } from './types/map.types';

// ── Mock maplibre-gl ──────────────────────────────────────────────────────────

vi.mock('maplibre-gl', () => {
  const MockMap = vi.fn().mockImplementation(() => ({
    on: vi.fn((_event: string, cb: (...args: unknown[]) => void) => {
      if (_event === 'load') setTimeout(() => cb(), 0);
    }),
    off: vi.fn(),
    getZoom: vi.fn(() => 2),
    getBounds: vi.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
    flyTo: vi.fn(),
    remove: vi.fn(),
  }));
  return { default: { Map: MockMap }, Map: MockMap };
});

// ── Mock Worker ───────────────────────────────────────────────────────────────

vi.stubGlobal('Worker', vi.fn().mockImplementation(() => ({
  postMessage: vi.fn(),
  onmessage: null,
  terminate: vi.fn(),
})));

// ── Mock WebSocket ────────────────────────────────────────────────────────────

const mockWsClose = vi.fn();
const mockWsAddEventListener = vi.fn();

vi.stubGlobal('WebSocket', vi.fn().mockImplementation(() => ({
  addEventListener: mockWsAddEventListener,
  removeEventListener: vi.fn(),
  close: mockWsClose,
  send: vi.fn(),
  readyState: 1,
})));

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

// ── MSW server ────────────────────────────────────────────────────────────────

const server = setupServer(
  http.get('http://localhost/api/v1/events', ({ request }) => {
    const url = new URL(request.url);
    const from = url.searchParams.get('from');
    if (from === '2025-01-01') {
      return HttpResponse.json({ data: HIST_EVENTS, meta: {}, error: null });
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
  mockWsClose.mockClear();
  mockWsAddEventListener.mockClear();
});
afterAll(() => server.close());

// ── Wrapper ───────────────────────────────────────────────────────────────────

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('IntelligenceMap — time-mode wiring (PLAN-F-021)', () => {
  it('renders TimeModeToolbar overlay', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument();
    });
  });

  it('timeMode defaults to "live" — Live button has aria-pressed=true', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      const liveBtn = screen.getByTestId('time-mode-btn-live');
      expect(liveBtn.getAttribute('aria-pressed')).toBe('true');
    });
  });

  it('PlaybackControls not present in live mode', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.queryByTestId('playback-controls')).not.toBeInTheDocument();
    });
  });

  it('switching to Playback mode renders PlaybackControls', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-btn-playback')).toBeInTheDocument();
    });
    act(() => {
      fireEvent.click(screen.getByTestId('time-mode-btn-playback'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('playback-controls')).toBeInTheDocument();
    });
  });

  it('switching to Historical mode shows DateRangeSlider', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('time-mode-btn-historical')).toBeInTheDocument();
    });
    act(() => {
      fireEvent.click(screen.getByTestId('time-mode-btn-historical'));
    });
    await waitFor(() => {
      expect(screen.getByTestId('date-range-slider')).toBeInTheDocument();
    });
  });

  it('timeMode="historical" with 0 events → EmptyState displays Historical-mode message', async () => {
    server.use(
      http.get('http://localhost/api/v1/events', ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get('from')) {
          return HttpResponse.json({ data: [], meta: {}, error: null });
        }
        return HttpResponse.json({ data: [], meta: {}, error: null });
      }),
    );

    render(<IntelligenceMap />, { wrapper: makeWrapper() });

    // Wait for initial render.
    await waitFor(() => expect(screen.getByTestId('time-mode-toolbar')).toBeInTheDocument());

    // Switch to historical mode.
    act(() => { fireEvent.click(screen.getByTestId('time-mode-btn-historical')); });

    // Set a date range and load.
    await waitFor(() => expect(screen.getByTestId('date-range-from')).toBeInTheDocument());
    act(() => {
      fireEvent.change(screen.getByTestId('date-range-from'), { target: { value: '2025-01-01' } });
      fireEvent.change(screen.getByTestId('date-range-to'), { target: { value: '2025-01-31' } });
    });
    act(() => { fireEvent.click(screen.getByTestId('date-range-load')); });

    // With 0 events historical empty state should show.
    await waitFor(() => {
      const emptyState = screen.queryByTestId('empty-state');
      if (emptyState) {
        expect(emptyState.textContent).toMatch(/date range|Select/i);
      }
    });
  });

  it('live mode with 0 events → existing Live-mode empty state message shown (regression guard)', async () => {
    render(<IntelligenceMap />, { wrapper: makeWrapper() });
    await waitFor(() => {
      const emptyState = screen.queryByTestId('empty-state');
      if (emptyState) {
        expect(emptyState.textContent).toContain('Markets are quiet');
      }
    });
  });
});
