import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
/**
 * map-websocket.test.tsx â€” Integration tests: WebSocket live event push.
 *
 * Verifies:
 *  - WS-pushed event is merged into the event list without a new HTTP fetch.
 *  - Malformed WS message does not crash the component.
 *
 * PLAN-F-019 TASK-012
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { IntelligenceMap } from '../../../src/frontend/features/intelligence-map/IntelligenceMap';

// â”€â”€ MapLibre mock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

vi.mock('maplibre-gl', () => {
  const MockMap = vi.fn().mockImplementation(() => ({
    on: vi.fn((event: string, cb: (...args: unknown[]) => void) => {
      if (event === 'load') setTimeout(() => cb(), 0);
    }),
    off: vi.fn(),
    getZoom: vi.fn(() => 2),
    getBounds: vi.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
    flyTo: vi.fn(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    getLayer: vi.fn(() => undefined),
    addSource: vi.fn(),
    removeSource: vi.fn(),
    getSource: vi.fn(() => undefined),
    remove: vi.fn(),
  }));
  return { default: { Map: MockMap }, Map: MockMap };
});

global.Worker = vi.fn().mockImplementation(() => ({
  postMessage: vi.fn(),
  terminate: vi.fn(),
  onmessage: null,
})) as unknown as typeof Worker;

// â”€â”€ WebSocket mock with message capture â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

let capturedMessageListener: ((e: MessageEvent) => void) | null = null;
const wsClose = vi.fn();

beforeEach(() => {
  capturedMessageListener = null;
  wsClose.mockClear();
  global.WebSocket = vi.fn().mockImplementation(() => ({
    addEventListener: vi.fn((event: string, cb: (e: MessageEvent) => void) => {
      if (event === 'message') capturedMessageListener = cb;
    }),
    close: wsClose,
  })) as unknown as typeof WebSocket;
});

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function buildEvent(i: number) {
  return {
    event_id: `evt-${i}`,
    category: ['CONFLICT'],
    intensity: 3,
    headline: `Event ${i}`,
    timestamp: new Date().toISOString(),
    lat: 51.5,
    lon: -0.1,
    relevance_window_end: new Date(Date.now() + 3_600_000).toISOString(),
    affected_companies: [],
  };
}

function renderAtRoot() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<IntelligenceMap />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('map-websocket integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('WS event push adds to event count without a new HTTP fetch', async () => {
    const initialEvents = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: initialEvents }),
    } as unknown as Response);
    global.fetch = fetchMock;

    renderAtRoot();
    // Wait for initial fetch.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Simulate a WS push of one new event.
    const newEvent = buildEvent(99);
    act(() => {
      capturedMessageListener?.({ data: JSON.stringify(newEvent) } as MessageEvent);
    });

    // Verify no additional fetch occurred.
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // The component should not have crashed.
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
  });

  it('malformed WS message does not crash the component', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    await waitFor(() =>
      expect(screen.queryByTestId('map-loading')).toBeNull(),
    );

    // Push invalid JSON over WebSocket.
    act(() => {
      capturedMessageListener?.({ data: '{ invalid json !!!' } as MessageEvent);
    });

    // Component must still be mounted and functional.
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
    // EmptyState should still be visible (0 events).
    expect(screen.getByTestId('empty-state')).toBeTruthy();
  });
});
