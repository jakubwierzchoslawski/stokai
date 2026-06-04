/**
 * useMapMode.ts — Global/Portfolio/Sector context mode state.
 *
 * State: { mode: "global" | "portfolio" | "sector", sector: string | null }
 * Actions: SET_MODE, SET_SECTOR
 *
 * Switching mode causes the TanStack Query key that includes `context` to change,
 * which triggers a re-fetch in useEventFeed automatically.
 *
 * PLAN-F-019 TASK-009
 */

import { useReducer } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

export type MapMode = 'global' | 'portfolio' | 'sector';

export interface MapModeState {
  mode: MapMode;
  sector: string | null;
}

type MapModeAction =
  | { type: 'SET_MODE'; mode: MapMode }
  | { type: 'SET_SECTOR'; sector: string };

// ── Reducer ───────────────────────────────────────────────────────────────────

export function mapModeReducer(
  state: MapModeState,
  action: MapModeAction,
): MapModeState {
  switch (action.type) {
    case 'SET_MODE':
      return {
        ...state,
        mode: action.mode,
        // Clear sector when switching away from sector mode.
        sector: action.mode === 'sector' ? state.sector : null,
      };
    case 'SET_SECTOR':
      return { ...state, sector: action.sector };
    default:
      return state;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseMapModeResult {
  mode: MapMode;
  sector: string | null;
  setMode: (mode: MapMode) => void;
  setSector: (sector: string) => void;
}

export function useMapMode(): UseMapModeResult {
  const [state, dispatch] = useReducer(mapModeReducer, {
    mode: 'global',
    sector: null,
  });

  function setMode(mode: MapMode) {
    dispatch({ type: 'SET_MODE', mode });
  }

  function setSector(sector: string) {
    dispatch({ type: 'SET_SECTOR', sector });
  }

  return { mode: state.mode, sector: state.sector, setMode, setSector };
}
