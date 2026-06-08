import { describe, it, expect, vi, type Mock } from 'vitest';
/**
 * ScoreOverlay.test.tsx â€” TDD tests for ScoreOverlay component.
 *
 * PLAN-F-019 TASK-008
 */

import React from 'react';
import { render } from '@testing-library/react';
import { ScoreOverlay } from './ScoreOverlay';
import type { ScoreMarker } from '../types/map.types';

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function makeMockMap() {
  const sources: Record<string, { data: unknown; setData: Mock }> = {};
  const layers: Record<string, unknown> = {};

  return {
    getSource: vi.fn((id: string) => sources[id]),
    addSource: vi.fn((id: string, spec: { data: unknown }) => {
      sources[id] = { data: spec.data, setData: vi.fn() };
    }),
    getLayer: vi.fn((id: string) => layers[id]),
    addLayer: vi.fn((spec: { id: string }) => {
      layers[spec.id] = spec;
    }),
    removeLayer: vi.fn((id: string) => { delete layers[id]; }),
    removeSource: vi.fn((id: string) => { delete sources[id]; }),
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

// â”€â”€ Tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

  it('renders null â€” no DOM elements produced', () => {
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
