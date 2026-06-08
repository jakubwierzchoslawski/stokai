import { describe, it, expect, vi, afterEach } from 'vitest';
/**
 * IntelligenceMap.test.tsx â€” TDD tests for the IntelligenceMap root component.
 *
 * MapLibre GL JS is mocked. MSW / fetch mock provides event data.
 * WebSocket is mocked globally.
 *
 * PLAN-F-019 TASK-011
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { IntelligenceMap } from './IntelligenceMap';

// â”€â”€ Mock maplibre-gl â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

vi.mock('maplibre-gl', () => {
  const listeners: Record<string, ((...args: unknown[]) => void)[]> = {};
  const MockMap = vi.fn().mockImplementation(() => ({
    on: vi.fn((event: string, cb: (...args: unknown[]) => void) => {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(cb);
      // Auto-fire "load" so tests don't need to wait for async map init.
      if (event === 'load') setTimeout(() => cb(), 0);
    }),
    off: vi.fn(),
    getZoom: vi.fn(() => 2),
    getBounds: vi.fn(() => ({
      toArray: () => [[-180, -85], [180, 85]],
    })),
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

// â”€â”€ Mock supercluster worker â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

vi.mock('./workers/supercluster.worker.ts', () => ({}), { virtual: true });

// Worker constructor mock â€” returns a no-op worker.
const mockWorkerPostMessage = vi.fn();
global.Worker = vi.fn().mockImplementation(() => ({
  postMessage: mockWorkerPostMessage,
  onmessage: null,
  terminate: vi.fn(),
})) as unknown as typeof Worker;

// â”€â”€ Mock WebSocket â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const wsClose = vi.fn();
global.WebSocket = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  close: wsClose,
})) as unknown as typeof WebSocket;

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function buildEvent(overrides: Partial<import('./types/map.types').EventPulse> = {}) {
  return {
    event_id: `evt-${Math.random().toString(36).slice(2, 6)}`,
    category: ['CONFLICT'],
    intensity: 3,
    headline: 'Test event',
    timestamp: new Date().toISOString(),
    lat: 51.5,
    lon: -0.1,
    relevance_window_end: new Date(Date.now() + 3_600_000).toISOString(),
    affected_companies: [],
    ...overrides,
  };
}

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
  return Wrapper;
}

function renderAtRoot(props: Parameters<typeof IntelligenceMap>[0] = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<IntelligenceMap {...props} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

describe('IntelligenceMap â€” route "/" renders the map', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('renders the map container element', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('map-container')).toBeTruthy();
  });

  it('renders EmptyState when 0 events are returned', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toBeTruthy(),
    );
  });

  it('does NOT render EmptyState when events are loaded', async () => {
    const events = Array.from({ length: 5 }, (_, i) => buildEvent({ event_id: `e${i}` }));
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: events }),
    } as unknown as Response);

    renderAtRoot();
    // Wait for loading to complete.
    await waitFor(() =>
      expect(screen.queryByTestId('map-loading')).toBeNull(),
    );
    expect(screen.queryByTestId('empty-state')).toBeNull();
  });
});

describe('IntelligenceMap â€” route "/" renders without redirect', () => {
  it('renders IntelligenceMap at "/" via React Router without redirecting', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
  });
});

describe('IntelligenceMap â€” context switcher triggers query re-execution', () => {
  it('switches mode to portfolio updates the event feed context', async () => {
    let capturedUrl = '';
    global.fetch = vi.fn().mockImplementation((url: string) => {
      capturedUrl = url;
      return Promise.resolve({
        ok: true,
        json: async () => ({ data: [] }),
      } as unknown as Response);
    });

    const { getByTestId } = renderAtRoot();

    await waitFor(() => expect(capturedUrl).toContain('global'));

    const portfolioBtn = getByTestId('mode-button-portfolio');
    act(() => portfolioBtn.click());

    await waitFor(() => expect(capturedUrl).toContain('portfolio'));
  });
});

describe('IntelligenceMap â€” filter panel available', () => {
  it('renders the filter panel', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('filter-panel')).toBeTruthy();
  });
});
