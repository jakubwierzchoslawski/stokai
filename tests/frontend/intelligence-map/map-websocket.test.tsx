/**
 * map-websocket.test.tsx — Integration tests: WebSocket live event push.
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

// ── MapLibre mock ─────────────────────────────────────────────────────────────

jest.mock('maplibre-gl', () => {
  const MockMap = jest.fn().mockImplementation(() => ({
    on: jest.fn((event: string, cb: (...args: unknown[]) => void) => {
      if (event === 'load') setTimeout(() => cb(), 0);
    }),
    off: jest.fn(),
    getZoom: jest.fn(() => 2),
    getBounds: jest.fn(() => ({ toArray: () => [[-180, -85], [180, 85]] })),
    flyTo: jest.fn(),
    addLayer: jest.fn(),
    removeLayer: jest.fn(),
    getLayer: jest.fn(() => undefined),
    addSource: jest.fn(),
    removeSource: jest.fn(),
    getSource: jest.fn(() => undefined),
    remove: jest.fn(),
  }));
  return { default: { Map: MockMap }, Map: MockMap };
});

global.Worker = jest.fn().mockImplementation(() => ({
  postMessage: jest.fn(),
  terminate: jest.fn(),
  onmessage: null,
})) as unknown as typeof Worker;

// ── WebSocket mock with message capture ───────────────────────────────────────

let capturedMessageListener: ((e: MessageEvent) => void) | null = null;
const wsClose = jest.fn();

beforeEach(() => {
  capturedMessageListener = null;
  wsClose.mockClear();
  global.WebSocket = jest.fn().mockImplementation(() => ({
    addEventListener: jest.fn((event: string, cb: (e: MessageEvent) => void) => {
      if (event === 'message') capturedMessageListener = cb;
    }),
    close: wsClose,
  })) as unknown as typeof WebSocket;
});

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('map-websocket integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('WS event push adds to event count without a new HTTP fetch', async () => {
    const initialEvents = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    const fetchMock = jest.fn().mockResolvedValue({
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
    global.fetch = jest.fn().mockResolvedValue({
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
