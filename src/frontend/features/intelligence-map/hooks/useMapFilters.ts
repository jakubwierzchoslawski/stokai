/**
 * useMapFilters.ts — Pure reducer hook for category/intensity filter state.
 *
 * State: { categories: string[], intensities: number[] }
 * Actions: TOGGLE_CATEGORY, TOGGLE_INTENSITY
 * Invariant: at least one category and one intensity must always remain active.
 *
 * PLAN-F-019 TASK-007
 */

import { useReducer } from 'react';
import { KNOWN_CATEGORIES } from '../lib/cluster-properties';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface MapFilters {
  categories: string[];
  intensities: number[];
}

type FilterAction =
  | { type: 'TOGGLE_CATEGORY'; category: string }
  | { type: 'TOGGLE_INTENSITY'; level: number };

// ── Initial state ─────────────────────────────────────────────────────────────

export const ALL_INTENSITIES: number[] = [1, 2, 3, 4, 5];

export const INITIAL_FILTERS: MapFilters = {
  categories: [...KNOWN_CATEGORIES],
  intensities: [...ALL_INTENSITIES],
};

// ── Reducer ───────────────────────────────────────────────────────────────────

export function mapFiltersReducer(
  state: MapFilters,
  action: FilterAction,
): MapFilters {
  switch (action.type) {
    case 'TOGGLE_CATEGORY': {
      const { category } = action;
      if (state.categories.includes(category)) {
        // No-op guard: must keep at least one category active.
        if (state.categories.length <= 1) return state;
        return {
          ...state,
          categories: state.categories.filter((c) => c !== category),
        };
      }
      return { ...state, categories: [...state.categories, category] };
    }
    case 'TOGGLE_INTENSITY': {
      const { level } = action;
      if (state.intensities.includes(level)) {
        // No-op guard: must keep at least one intensity active.
        if (state.intensities.length <= 1) return state;
        return {
          ...state,
          intensities: state.intensities.filter((i) => i !== level),
        };
      }
      return { ...state, intensities: [...state.intensities, level] };
    }
    default:
      return state;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseMapFiltersResult {
  filters: MapFilters;
  toggleCategory: (category: string) => void;
  toggleIntensity: (level: number) => void;
}

export function useMapFilters(): UseMapFiltersResult {
  const [filters, dispatch] = useReducer(mapFiltersReducer, INITIAL_FILTERS);

  function toggleCategory(category: string) {
    dispatch({ type: 'TOGGLE_CATEGORY', category });
  }

  function toggleIntensity(level: number) {
    dispatch({ type: 'TOGGLE_INTENSITY', level });
  }

  return { filters, toggleCategory, toggleIntensity };
}
