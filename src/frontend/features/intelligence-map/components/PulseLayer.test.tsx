/**
 * PulseLayer.test.tsx — TDD tests for PulseLayer.
 *
 * MapLibre is mocked. WebGL context is mocked to count buffer upload calls.
 *
 * PLAN-F-019 TASK-006
 */

import React from 'react';
import { render } from '@testing-library/react';
import {
  PulseLayer,
  applyFilters,
  VERTEX_SHADER_SOURCE,
  FRAGMENT_SHADER_SOURCE,
  type MapFilters,
} from './PulseLayer';
import type { EventPulse } from '../types/map.types';
import { computePulseState } from '../lib/pulse-animation';

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildEvent(overrides: Partial<EventPulse> = {}): EventPulse {
  const base: EventPulse = {
    event_id: 'e1',
    category: ['CONFLICT'],
    intensity: 3,
    headline: 'Test',
    timestamp: new Date(Date.now() - 1000).toISOString(),
    lat: 51.5,
    lon: -0.1,
    relevance_window_end: new Date(Date.now() + 3_600_000).toISOString(),
    affected_companies: [],
  };
  return { ...base, ...overrides };
}

const ALL_FILTERS: MapFilters = {
  categories: ['CONFLICT', 'ECONOMIC', 'POLITICAL', 'NATURAL_DISASTER', 'REGULATORY', 'SOCIAL'],
  intensities: [1, 2, 3, 4, 5],
};

function makeMockMap() {
  const layers: Record<string, unknown> = {};
  const listeners: Record<string, ((e: unknown) => void)[]> = {};

  return {
    addLayer: jest.fn((layer: { id: string; onAdd?: (m: unknown, gl: unknown) => void }) => {
      layers[layer.id] = layer;
    }),
    removeLayer: jest.fn((id: string) => { delete layers[id]; }),
    getLayer: jest.fn((id: string) => layers[id]),
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

// ── applyFilters unit tests ───────────────────────────────────────────────────

describe('applyFilters', () => {
  it('passes events matching active category and intensity', () => {
    const events = [buildEvent({ category: ['CONFLICT'], intensity: 3 })];
    expect(applyFilters(events, ALL_FILTERS)).toHaveLength(1);
  });

  it('filters out events whose category is not in active categories', () => {
    const events = [
      buildEvent({ event_id: 'e1', category: ['CONFLICT'], intensity: 3 }),
      buildEvent({ event_id: 'e2', category: ['ECONOMIC'], intensity: 3 }),
    ];
    const filters: MapFilters = { categories: ['ECONOMIC'], intensities: [1, 2, 3, 4, 5] };
    const result = applyFilters(events, filters);
    expect(result).toHaveLength(1);
    expect(result[0].event_id).toBe('e2');
  });

  it('filters out events whose intensity is not in active intensities', () => {
    const events = [
      buildEvent({ event_id: 'e1', intensity: 2 }),
      buildEvent({ event_id: 'e2', intensity: 4 }),
      buildEvent({ event_id: 'e3', intensity: 5 }),
    ];
    const filters: MapFilters = { categories: ['CONFLICT'], intensities: [4, 5] };
    const result = applyFilters(events, filters);
    expect(result).toHaveLength(2);
    expect(result.map((e) => e.event_id)).toEqual(['e2', 'e3']);
  });

  it('returns empty array when no events pass filters', () => {
    const events = [buildEvent({ category: ['CONFLICT'] })];
    const filters: MapFilters = { categories: ['ECONOMIC'], intensities: [1, 2, 3, 4, 5] };
    expect(applyFilters(events, filters)).toHaveLength(0);
  });
});

// ── computePulseState integration ─────────────────────────────────────────────

describe('computePulseState integration with PulseLayer', () => {
  it('event 30% into its window has expected opacity', () => {
    const window = 3_600_000;
    const elapsed = window * 0.3;
    const start = new Date(Date.now() - elapsed);
    const end = new Date(start.getTime() + window);
    const state = computePulseState(
      {
        timestamp: start.toISOString(),
        relevance_window_end: end.toISOString(),
        intensity: 3,
      },
      new Date(),
    );
    // opacity = 1.0 - 0.3 * 0.85 = 0.745
    expect(state.opacity).toBeCloseTo(0.745, 2);
  });
});

// ── Shader snapshot test ──────────────────────────────────────────────────────

describe('Shader source strings', () => {
  it('vertex shader snapshot is stable', () => {
    expect(VERTEX_SHADER_SOURCE).toMatchSnapshot();
  });

  it('fragment shader snapshot is stable', () => {
    expect(FRAGMENT_SHADER_SOURCE).toMatchSnapshot();
  });
});

// ── PulseLayer component — onPulseClick ──────────────────────────────────────

describe('PulseLayer — onPulseClick', () => {
  it('fires onPulseClick with the closest EventPulse on map click', () => {
    const map = makeMockMap();
    const events = [buildEvent({ event_id: 'target', lon: 0, lat: 0 })];
    const clickFn = jest.fn();

    render(
      <PulseLayer
        map={map}
        events={events}
        activeFilters={ALL_FILTERS}
        onPulseClick={clickFn}
      />,
    );

    map._trigger('click', { lngLat: { lng: 0.05, lat: 0.05 } });
    expect(clickFn).toHaveBeenCalledTimes(1);
    expect(clickFn).toHaveBeenCalledWith(events[0]);
  });

  it('does not fire onPulseClick when click is far from all events', () => {
    const map = makeMockMap();
    const events = [buildEvent({ lon: 0, lat: 0 })];
    const clickFn = jest.fn();

    render(
      <PulseLayer
        map={map}
        events={events}
        activeFilters={ALL_FILTERS}
        onPulseClick={clickFn}
      />,
    );

    map._trigger('click', { lngLat: { lng: 10, lat: 10 } });
    expect(clickFn).not.toHaveBeenCalled();
  });
});

// ── PulseLayer renders null (no DOM) ─────────────────────────────────────────

describe('PulseLayer — rendering', () => {
  it('renders null — no DOM elements produced', () => {
    const map = makeMockMap();
    const { container } = render(
      <PulseLayer map={map} events={[]} activeFilters={ALL_FILTERS} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
