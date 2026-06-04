/**
 * useHistoricalEvents.test.ts — TDD tests for useHistoricalEvents.
 *
 * Uses MSW to intercept GET /api/v1/events requests.
 *
 * PLAN-F-021 TASK-005
 */

import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useHistoricalEvents } from './useHistoricalEvents';
import type { EventPulse } from '../types/map.types';

// ── MSW server ────────────────────────────────────────────────────────────────

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
    affected_companies: [],
  };
}

const RANGE_EVENTS: EventPulse[] = [
  makeEvent('a1', '2025-01-05T12:00:00.000Z'),
  makeEvent('a2', '2025-01-10T08:00:00.000Z'),
  makeEvent('a3', '2025-01-15T16:00:00.000Z'),
  makeEvent('a4', '2025-01-20T09:00:00.000Z'),
  makeEvent('a5', '2025-01-25T11:00:00.000Z'),
];

let lastRequestUrl = '';

const server = setupServer(
  http.get('http://localhost/api/v1/events', ({ request }) => {
    lastRequestUrl = request.url;
    const url = new URL(request.url);
    const from = url.searchParams.get('from');
    const to = url.searchParams.get('to');
    if (from === '2025-01-01' && to === '2025-01-31') {
      return HttpResponse.json({ data: RANGE_EVENTS, meta: {}, error: null });
    }
    if (from === '2025-02-01' && to === '2025-02-28') {
      return HttpResponse.json({ data: [makeEvent('b1', '2025-02-10T00:00:00.000Z')], meta: {}, error: null });
    }
    // Return malformed event (missing lat).
    if (from === '2025-03-01' && to === '2025-03-31') {
      return HttpResponse.json({ data: [{ event_id: 'bad', category: [], intensity: 1, headline: 'bad', timestamp: '2025-03-01T00:00:00Z', lon: 0, relevance_window_end: '2025-03-01T00:00:00Z', affected_companies: [] }], meta: {}, error: null });
    }
    // Out-of-order events.
    if (from === '2025-04-01' && to === '2025-04-30') {
      return HttpResponse.json({
        data: [
          makeEvent('c2', '2025-04-20T00:00:00.000Z'),
          makeEvent('c1', '2025-04-05T00:00:00.000Z'),
        ],
        meta: {},
        error: null,
      });
    }
    return HttpResponse.json({ data: [], meta: {}, error: null });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ── Wrapper ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useHistoricalEvents', () => {
  it('enabled=false → no GET /api/v1/events request; returns empty events array', () => {
    lastRequestUrl = '';
    const { result } = renderHook(
      () => useHistoricalEvents({ dateRange: { from_date: '2025-01-01', to_date: '2025-01-31' }, enabled: false }),
      { wrapper: createWrapper() },
    );
    expect(result.current.events).toHaveLength(0);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isError).toBe(false);
    expect(lastRequestUrl).toBe('');
  });

  it('enabled=true, MSW returns 5 events → events has length 5 after loading resolves', async () => {
    const { result } = renderHook(
      () => useHistoricalEvents({ dateRange: { from_date: '2025-01-01', to_date: '2025-01-31' }, enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(5);
    expect(result.current.isError).toBe(false);
  });

  it('date range changes → new fetch triggered with updated from and to params', async () => {
    let dateRange = { from_date: '2025-01-01', to_date: '2025-01-31' };
    const { result, rerender } = renderHook(
      () => useHistoricalEvents({ dateRange, enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(5);

    // Change date range.
    dateRange = { from_date: '2025-02-01', to_date: '2025-02-28' };
    rerender();
    await waitFor(() => expect(result.current.events).toHaveLength(1));
  });

  it('MSW returns malformed event (missing lat) → isError=true; events remains empty', async () => {
    const { result } = renderHook(
      () => useHistoricalEvents({ dateRange: { from_date: '2025-03-01', to_date: '2025-03-31' }, enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isError).toBe(true);
    expect(result.current.events).toHaveLength(0);
  });

  it('events returned out of chronological order → hook returns them sorted ascending by timestamp', async () => {
    const { result } = renderHook(
      () => useHistoricalEvents({ dateRange: { from_date: '2025-04-01', to_date: '2025-04-30' }, enabled: true }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(2);
    expect(result.current.events[0].event_id).toBe('c1');
    expect(result.current.events[1].event_id).toBe('c2');
  });
});
