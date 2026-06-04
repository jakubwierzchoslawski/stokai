/**
 * ScoreOverlay.test.tsx — TDD tests for ScoreOverlay component.
 *
 * PLAN-F-019 TASK-008
 */

import React from 'react';
import { render } from '@testing-library/react';
import { ScoreOverlay } from './ScoreOverlay';
import type { ScoreMarker } from '../types/map.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeMockMap() {
  const sources: Record<string, { data: unknown; setData: jest.Mock }> = {};
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
  };
}

function buildMarker(overrides: Partial<ScoreMarker> = {}): ScoreMarker {
  return {
    company_id: 'company-1',
    ticker: 'ACME',
    lat: 51.5,
    lon: -0.1,
    geo_adjusted: 75,
    score_delta: 5,
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ScoreOverlay', () => {
  it('adds a MapLibre source on mount', () => {
    const map = makeMockMap();
    render(<ScoreOverlay map={map} markers={[buildMarker()]} />);
    expect(map.addSource).toHaveBeenCalled();
  });

  it('adds a circle layer on mount', () => {
    const map = makeMockMap();
    render(<ScoreOverlay map={map} markers={[buildMarker()]} />);
    expect(map.addLayer).toHaveBeenCalled();
  });

  it('renders null — no DOM elements produced', () => {
    const map = makeMockMap();
    const { container } = render(<ScoreOverlay map={map} markers={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('removes layers on unmount', () => {
    const map = makeMockMap();
    const { unmount } = render(<ScoreOverlay map={map} markers={[buildMarker()]} />);
    unmount();
    expect(map.removeLayer).toHaveBeenCalled();
    expect(map.removeSource).toHaveBeenCalled();
  });
});
