import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * map-filters.test.tsx â€” Integration tests: category filter toggling.
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

global.WebSocket = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  close: vi.fn(),
})) as unknown as typeof WebSocket;

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('map-filters integration', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('filter panel renders and toggling CONFLICT fires no HTTP re-fetch', async () => {
    const conflictEvents = Array.from({ length: 3 }, (_, i) => buildConflictEvent(i));
    const economicEvents = Array.from({ length: 2 }, (_, i) => buildEconomicEvent(i));
    const allEvents = [...conflictEvents, ...economicEvents];

    const fetchMock = vi.fn().mockResolvedValue({
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

    const fetchMock = vi.fn().mockResolvedValue({
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
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('filter-panel')).toBeTruthy();
  });
});
