/**
 * map-initial-load.test.tsx — Integration tests: initial map load.
 *
 * Verifies:
 *  - Map container is present in the DOM after render at route "/".
 *  - EmptyState is absent when events are loaded.
 *  - GET /api/v1/events is called exactly once on mount.
 *
 * PLAN-F-019 TASK-012
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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

global.WebSocket = jest.fn().mockImplementation(() => ({
  addEventListener: jest.fn(),
  close: jest.fn(),
})) as unknown as typeof WebSocket;

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildEvent(i: number) {
  return {
    event_id: `evt-${i}`,
    category: ['CONFLICT'],
    intensity: 3,
    headline: `Event ${i}`,
    timestamp: new Date().toISOString(),
    lat: 51.5 + i * 0.01,
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

describe('map-initial-load integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('map container is present in the DOM at route "/"', async () => {
    const events = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('map-container')).toBeTruthy();
  });

  it('no redirect occurred — IntelligenceMap is the first rendered element', () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
  });

  it('EmptyState is absent when 10 events are loaded', async () => {
    const events = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    renderAtRoot();
    await waitFor(() => expect(screen.queryByTestId('map-loading')).toBeNull());
    expect(screen.queryByTestId('empty-state')).toBeNull();
  });

  it('GET /api/v1/events is called exactly once on mount', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);
    global.fetch = fetchMock;

    renderAtRoot();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    // Wait another tick to confirm no extra fetches.
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
