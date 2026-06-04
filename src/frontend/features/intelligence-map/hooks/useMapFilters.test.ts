/**
 * useMapFilters.test.ts — TDD tests for the useMapFilters hook and reducer.
 *
 * PLAN-F-019 TASK-007
 */

import { renderHook, act } from '@testing-library/react';
import {
  mapFiltersReducer,
  useMapFilters,
  INITIAL_FILTERS,
  ALL_INTENSITIES,
} from './useMapFilters';
import { KNOWN_CATEGORIES } from '../lib/cluster-properties';

// ── Reducer unit tests ────────────────────────────────────────────────────────

describe('mapFiltersReducer — initial state', () => {
  it('initial state has all 6 categories enabled', () => {
    expect(INITIAL_FILTERS.categories).toHaveLength(KNOWN_CATEGORIES.length);
    for (const cat of KNOWN_CATEGORIES) {
      expect(INITIAL_FILTERS.categories).toContain(cat);
    }
  });

  it('initial state has all 5 intensities enabled', () => {
    expect(INITIAL_FILTERS.intensities).toEqual([1, 2, 3, 4, 5]);
  });
});

describe('mapFiltersReducer — TOGGLE_CATEGORY', () => {
  it('removes a category when 2 categories are active', () => {
    const twoCategories = { ...INITIAL_FILTERS, categories: ['CONFLICT', 'ECONOMIC'] };
    const next = mapFiltersReducer(twoCategories, { type: 'TOGGLE_CATEGORY', category: 'CONFLICT' });
    expect(next.categories).not.toContain('CONFLICT');
    expect(next.categories).toContain('ECONOMIC');
  });

  it('adds a category when it is currently inactive', () => {
    const oneCategory = { ...INITIAL_FILTERS, categories: ['ECONOMIC'] };
    const next = mapFiltersReducer(oneCategory, { type: 'TOGGLE_CATEGORY', category: 'CONFLICT' });
    expect(next.categories).toContain('CONFLICT');
    expect(next.categories).toContain('ECONOMIC');
  });

  it('no-op when toggling the only active category', () => {
    const oneCategory = { ...INITIAL_FILTERS, categories: ['CONFLICT'] };
    const next = mapFiltersReducer(oneCategory, { type: 'TOGGLE_CATEGORY', category: 'CONFLICT' });
    expect(next.categories).toEqual(['CONFLICT']);
  });
});

describe('mapFiltersReducer — TOGGLE_INTENSITY', () => {
  it('removes an intensity when more than one is active', () => {
    const next = mapFiltersReducer(INITIAL_FILTERS, { type: 'TOGGLE_INTENSITY', level: 3 });
    expect(next.intensities).not.toContain(3);
  });

  it('adds an intensity when it is currently inactive', () => {
    const noThree = { ...INITIAL_FILTERS, intensities: [1, 2, 4, 5] };
    const next = mapFiltersReducer(noThree, { type: 'TOGGLE_INTENSITY', level: 3 });
    expect(next.intensities).toContain(3);
  });

  it('no-op when toggling the only active intensity', () => {
    const oneIntensity = { ...INITIAL_FILTERS, intensities: [3] };
    const next = mapFiltersReducer(oneIntensity, { type: 'TOGGLE_INTENSITY', level: 3 });
    expect(next.intensities).toEqual([3]);
  });
});

// ── useMapFilters hook tests ──────────────────────────────────────────────────

describe('useMapFilters hook', () => {
  it('starts with all categories and intensities enabled', () => {
    const { result } = renderHook(() => useMapFilters());
    expect(result.current.filters.categories).toHaveLength(KNOWN_CATEGORIES.length);
    expect(result.current.filters.intensities).toEqual(ALL_INTENSITIES);
  });

  it('toggleCategory removes an active category', () => {
    const { result } = renderHook(() => useMapFilters());
    act(() => result.current.toggleCategory('CONFLICT'));
    expect(result.current.filters.categories).not.toContain('CONFLICT');
  });

  it('toggleCategory adds an inactive category back', () => {
    const { result } = renderHook(() => useMapFilters());
    act(() => result.current.toggleCategory('CONFLICT'));
    act(() => result.current.toggleCategory('CONFLICT'));
    expect(result.current.filters.categories).toContain('CONFLICT');
  });

  it('toggleIntensity removes an active intensity', () => {
    const { result } = renderHook(() => useMapFilters());
    act(() => result.current.toggleIntensity(3));
    expect(result.current.filters.intensities).not.toContain(3);
  });
});
