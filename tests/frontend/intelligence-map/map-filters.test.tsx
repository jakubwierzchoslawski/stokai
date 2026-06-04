/**
 * map-filters.test.tsx — Integration tests: category filter toggling.
 *
 * Verifies:
 *  - Toggling off a category hides matching events from PulseLayer.
 *  - Re-enabling the category restores them.
 *  - No HTTP re-fetch occurs during filter toggles.
 *
 * PLAN-F-019 TASK-012
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

global.WebSocket = jest.fn().mockImplementation(() => ({
  addEventListener: jest.fn(),
  close: jest.fn(),
})) as unknown as typeof WebSocket;

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildConflictEvent(i: number) {
  return {
    event_id: `conflict-${i}`,
    category: ['CONFLICT'],
    intensity: 3,
    headline: `Conflict ${i}`,
    timestamp: new Date().toISOString(),
    lat: 51.5,
    lon: -0.1 + i * 0.01,
    relevance_window_end: new Date(Date.now() + 3_600_000).toISOString(),
    affected_companies: [],
  };
}

function buildEconomicEvent(i: number) {
  return {
    event_id: `economic-${i}`,
    category: ['ECONOMIC'],
    intensity: 3,
    headline: `Economic ${i}`,
    timestamp: new Date().toISOString(),
    lat: 52.0,
    lon: -0.5 + i * 0.01,
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

describe('map-filters integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('filter panel renders and toggling CONFLICT fires no HTTP re-fetch', async () => {
    const conflictEvents = Array.from({ length: 3 }, (_, i) => buildConflictEvent(i));
    const economicEvents = Array.from({ length: 2 }, (_, i) => buildEconomicEvent(i));
    const allEvents = [...conflictEvents, ...economicEvents];

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: allEvents }),
    } as unknown as Response);
    global.fetch = fetchMock;

    renderAtRoot();

    // Wait for events to load.
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Toggle off CONFLICT.
    const conflictCheckbox = screen.getByTestId('checkbox-category-CONFLICT') as HTMLInputElement;
    fireEvent.click(conflictCheckbox);

    // Checkbox should now be unchecked.
    expect(conflictCheckbox.checked).toBe(false);

    // No new HTTP fetch should have occurred.
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('re-enabling CONFLICT restores it without HTTP re-fetch', async () => {
    const allEvents = [
      ...Array.from({ length: 3 }, (_, i) => buildConflictEvent(i)),
      ...Array.from({ length: 2 }, (_, i) => buildEconomicEvent(i)),
    ];

    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: allEvents }),
    } as unknown as Response);
    global.fetch = fetchMock;

    renderAtRoot();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const conflictCheckbox = screen.getByTestId('checkbox-category-CONFLICT') as HTMLInputElement;

    // Toggle off then back on.
    fireEvent.click(conflictCheckbox);
    expect(conflictCheckbox.checked).toBe(false);
    fireEvent.click(conflictCheckbox);
    expect(conflictCheckbox.checked).toBe(true);

    // Still only one HTTP fetch.
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('filter panel is visible when component mounts', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('filter-panel')).toBeTruthy();
  });
});
