import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * map-initial-load.test.tsx â€” Integration tests: initial map load.
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

// â”€â”€ Global mocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

global.WebSocket = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  close: vi.fn(),
})) as unknown as typeof WebSocket;

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('map-initial-load integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('map container is present in the DOM at route "/"', async () => {
    const events = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('map-container')).toBeTruthy();
  });

  it('no redirect occurred â€” IntelligenceMap is the first rendered element', () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
  });

  it('EmptyState is absent when 10 events are loaded', async () => {
    const events = Array.from({ length: 10 }, (_, i) => buildEvent(i));
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    renderAtRoot();
    await waitFor(() => expect(screen.queryByTestId('map-loading')).toBeNull());
    expect(screen.queryByTestId('empty-state')).toBeNull();
  });

  it('GET /api/v1/events is called exactly once on mount', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
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
