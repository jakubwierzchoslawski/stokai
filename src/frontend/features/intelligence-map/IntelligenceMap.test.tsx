/**
 * IntelligenceMap.test.tsx — TDD tests for the IntelligenceMap root component.
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

// ── Mock maplibre-gl ──────────────────────────────────────────────────────────

jest.mock('maplibre-gl', () => {
  const listeners: Record<string, ((...args: unknown[]) => void)[]> = {};
  const MockMap = jest.fn().mockImplementation(() => ({
    on: jest.fn((event: string, cb: (...args: unknown[]) => void) => {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(cb);
      // Auto-fire "load" so tests don't need to wait for async map init.
      if (event === 'load') setTimeout(() => cb(), 0);
    }),
    off: jest.fn(),
    getZoom: jest.fn(() => 2),
    getBounds: jest.fn(() => ({
      toArray: () => [[-180, -85], [180, 85]],
    })),
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

// ── Mock supercluster worker ──────────────────────────────────────────────────

jest.mock('./workers/supercluster.worker.ts', () => ({}), { virtual: true });

// Worker constructor mock — returns a no-op worker.
const mockWorkerPostMessage = jest.fn();
global.Worker = jest.fn().mockImplementation(() => ({
  postMessage: mockWorkerPostMessage,
  onmessage: null,
  terminate: jest.fn(),
})) as unknown as typeof Worker;

// ── Mock WebSocket ────────────────────────────────────────────────────────────

const wsClose = jest.fn();
global.WebSocket = jest.fn().mockImplementation(() => ({
  addEventListener: jest.fn(),
  close: wsClose,
})) as unknown as typeof WebSocket;

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('IntelligenceMap — route "/" renders the map', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  it('renders the map container element', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('map-container')).toBeTruthy();
  });

  it('renders EmptyState when 0 events are returned', async () => {
    global.fetch = jest.fn().mockResolvedValue({
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
    global.fetch = jest.fn().mockResolvedValue({
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

describe('IntelligenceMap — route "/" renders without redirect', () => {
  it('renders IntelligenceMap at "/" via React Router without redirecting', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('intelligence-map-root')).toBeTruthy();
  });
});

describe('IntelligenceMap — context switcher triggers query re-execution', () => {
  it('switches mode to portfolio updates the event feed context', async () => {
    let capturedUrl = '';
    global.fetch = jest.fn().mockImplementation((url: string) => {
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

describe('IntelligenceMap — filter panel available', () => {
  it('renders the filter panel', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: [] }),
    } as unknown as Response);

    renderAtRoot();
    expect(screen.getByTestId('filter-panel')).toBeTruthy();
  });
});
