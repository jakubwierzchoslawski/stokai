import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * useEventFeed.test.ts â€” TDD tests for the useEventFeed hook.
 *
 * Uses @testing-library/react renderHook, MSW for HTTP mocking, and a fake
 * WebSocket implementation to test WS push behavior.
 *
 * PLAN-F-019 TASK-002
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { fetchEvents, EventFetchError } from '../api/events.api';
import type { EventPulse } from '../types/map.types';

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function buildEvent(overrides: Partial<EventPulse> = {}): EventPulse {
  return {
    event_id: 'evt-001',
    category: ['CONFLICT'],
    intensity: 3,
    headline: 'Test event',
    timestamp: new Date().toISOString(),
    lat: 10,
    lon: 20,
    relevance_window_end: new Date(Date.now() + 3_600_000).toISOString(),
    affected_companies: [],
    ...overrides,
  };
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

// â”€â”€ fetchEvents tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('fetchEvents', () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns an array of EventPulse on success', async () => {
    const events = [buildEvent(), buildEvent({ event_id: 'evt-002' })];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events, meta: {}, error: null }),
    } as unknown as Response);

    const result = await fetchEvents({ context: 'global' });
    expect(result).toHaveLength(2);
    expect(result[0].event_id).toBe('evt-001');
  });

  it('throws EventFetchError with code UNAUTHORIZED on HTTP 401', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    } as unknown as Response);

    await expect(fetchEvents({})).rejects.toMatchObject({
      code: 'UNAUTHORIZED',
    });
  });

  it('throws EventFetchError with code SCHEMA_VIOLATION on malformed event (missing lat)', async () => {
    const malformed = { event_id: 'x', category: [], intensity: 3, headline: 'h', timestamp: 't', lon: 1, relevance_window_end: 'e', affected_companies: [] };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [malformed] }),
    } as unknown as Response);

    await expect(fetchEvents({})).rejects.toMatchObject({
      code: 'SCHEMA_VIOLATION',
    });
  });

  it('EventFetchError is an instance of Error', () => {
    const err = new EventFetchError('UNAUTHORIZED', 'msg', 401);
    expect(err).toBeInstanceOf(Error);
    expect(err.code).toBe('UNAUTHORIZED');
    expect(err.status).toBe(401);
  });
});

// â”€â”€ useEventFeed hook tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

// We test the hook's WebSocket behavior by mocking subscribeToEventChannel.
vi.mock('../hooks/useEventFeed', async () => {
  const actual = await vi.importActual('../hooks/useEventFeed');
  return actual as object;
});

describe('useEventFeed â€” initial fetch', () => {
  const originalFetch = global.fetch;
  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('returns 3 events after isLoading resolves', async () => {
    const events = [buildEvent(), buildEvent({ event_id: 'e2' }), buildEvent({ event_id: 'e3' })];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    // Mock WebSocket so it never sends messages in this test.
    const wsClose = vi.fn();
    global.WebSocket = vi.fn().mockImplementation(() => ({
      addEventListener: vi.fn(),
      close: wsClose,
    })) as unknown as typeof WebSocket;

    const { useEventFeed } = await import('./useEventFeed');
    const { result } = renderHook(() => useEventFeed({ context: 'global' }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(3);
    expect(result.current.isError).toBe(false);
  });
});

describe('useEventFeed â€” WebSocket push', () => {
  it('appends a WS-pushed event without re-fetching', async () => {
    const initialEvents = Array.from({ length: 3 }, (_, i) =>
      buildEvent({ event_id: `e${i}` }),
    );
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: initialEvents }),
    } as unknown as Response);
    global.fetch = fetchMock;

    let capturedMessageListener: ((e: MessageEvent) => void) | null = null;
    const wsClose = vi.fn();
    global.WebSocket = vi.fn().mockImplementation(() => {
      return {
        addEventListener: vi.fn((event: string, cb: (e: MessageEvent) => void) => {
          if (event === 'message') capturedMessageListener = cb;
        }),
        close: wsClose,
      };
    }) as unknown as typeof WebSocket;

    const { useEventFeed } = await import('./useEventFeed');
    const { result } = renderHook(() => useEventFeed({ context: 'global' }), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.events).toHaveLength(3);

    const newEvent = buildEvent({ event_id: 'ws-new' });
    act(() => {
      capturedMessageListener?.({ data: JSON.stringify(newEvent) } as MessageEvent);
    });

    await waitFor(() => expect(result.current.events).toHaveLength(4));
    // No additional fetches should have occurred.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('useEventFeed â€” unmount unsubscribes', () => {
  it('calls ws.close() exactly once on unmount', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    const wsClose = vi.fn();
    global.WebSocket = vi.fn().mockImplementation(() => ({
      addEventListener: vi.fn(),
      close: wsClose,
    })) as unknown as typeof WebSocket;

    const { useEventFeed } = await import('./useEventFeed');
    const { unmount } = renderHook(() => useEventFeed({ context: 'global' }), {
      wrapper: makeWrapper(),
    });
    unmount();
    expect(wsClose).toHaveBeenCalledTimes(1);
  });
});
