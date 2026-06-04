/**
 * ClusterLayer.test.tsx — TDD tests for ClusterLayer component.
 *
 * MapLibre is mocked — we test prop/callback behavior, not canvas rendering.
 *
 * PLAN-F-019 TASK-005
 */

import React from 'react';
import { render, screen, act } from '@testing-library/react';
import { ClusterLayer, getDominantCategory } from './ClusterLayer';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeEmptyFC() {
  return { type: 'FeatureCollection' as const, features: [] };
}

function makeOneClusterFC(props: Record<string, unknown> = {}) {
  return {
    type: 'FeatureCollection' as const,
    features: [
      {
        type: 'Feature' as const,
        geometry: { type: 'Point', coordinates: [0, 0] as [number, number] },
        properties: {
          cluster: true,
          point_count: 5,
          count_CONFLICT: 3,
          count_ECONOMIC: 2,
          max_intensity: 3,
          ...props,
        },
      },
    ],
  };
}

function makeMockMap() {
  const listeners: Record<string, ((e: unknown) => void)[]> = {};
  const sources: Record<string, { data: unknown; setData: (d: unknown) => void }> = {};
  const layers: Record<string, unknown> = {};

  return {
    getSource: jest.fn((id: string) => sources[id]),
    addSource: jest.fn((id: string, spec: { data: unknown }) => {
      sources[id] = { data: spec.data, setData: jest.fn() };
    }),
    getLayer: jest.fn((id: string) => layers[id]),
    addLayer: jest.fn((spec: { id: string }) => {
      layers[spec.id] = spec;
    }),
    removeLayer: jest.fn((id: string) => { delete layers[id]; }),
    removeSource: jest.fn((id: string) => { delete sources[id]; }),
    on: jest.fn((event: string, _layer: string, cb: (e: unknown) => void) => {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(cb);
    }),
    off: jest.fn(),
    _trigger: (event: string, e: unknown) => {
      (listeners[event] ?? []).forEach((cb) => cb(e));
    },
  };
}

// ── getDominantCategory unit tests ────────────────────────────────────────────

describe('getDominantCategory', () => {
  it('returns the category with the highest count', () => {
    expect(getDominantCategory({ CONFLICT: 5, ECONOMIC: 2, POLITICAL: 1 })).toBe('CONFLICT');
  });

  it('returns the only category when there is just one', () => {
    expect(getDominantCategory({ ECONOMIC: 10 })).toBe('ECONOMIC');
  });

  it('returns null for an empty categories object', () => {
    expect(getDominantCategory({})).toBeNull();
  });
});

// ── ClusterLayer component tests ──────────────────────────────────────────────

describe('ClusterLayer', () => {
  it('renders without crashing with an empty FeatureCollection', () => {
    const map = makeMockMap();
    render(<ClusterLayer map={map} clusters={makeEmptyFC()} />);
    // No assertion on circle count since rendering is done by MapLibre (mocked).
    // We assert the component mounts without error.
    expect(map.addSource).toHaveBeenCalled();
    expect(map.addLayer).toHaveBeenCalled();
  });

  it('calls onClusterClick with the cluster feature when click event fires', () => {
    const map = makeMockMap();
    const mockFn = jest.fn();
    const fc = makeOneClusterFC();

    render(<ClusterLayer map={map} clusters={fc} onClusterClick={mockFn} />);

    act(() => {
      map._trigger('click', { features: [fc.features[0]] });
    });

    expect(mockFn).toHaveBeenCalledTimes(1);
    expect(mockFn).toHaveBeenCalledWith(fc.features[0]);
  });

  it('does not call onClusterClick when features array is empty', () => {
    const map = makeMockMap();
    const mockFn = jest.fn();
    const fc = makeOneClusterFC();

    render(<ClusterLayer map={map} clusters={fc} onClusterClick={mockFn} />);

    act(() => {
      map._trigger('click', { features: [] });
    });

    expect(mockFn).not.toHaveBeenCalled();
  });

  it('shows cluster donut tooltip on mouseenter', () => {
    const map = makeMockMap();
    const fc = makeOneClusterFC();

    render(<ClusterLayer map={map} clusters={fc} />);

    act(() => {
      map._trigger('mouseenter', {
        features: [fc.features[0]],
        point: { x: 100, y: 100 },
      });
    });

    expect(screen.getByTestId('cluster-donut-tooltip')).toBeTruthy();
  });

  it('hides cluster donut tooltip on mouseleave', () => {
    const map = makeMockMap();
    const fc = makeOneClusterFC();

    render(<ClusterLayer map={map} clusters={fc} />);

    act(() => {
      map._trigger('mouseenter', {
        features: [fc.features[0]],
        point: { x: 100, y: 100 },
      });
    });
    act(() => {
      map._trigger('mouseleave', {});
    });

    expect(screen.queryByTestId('cluster-donut-tooltip')).toBeNull();
  });
});
