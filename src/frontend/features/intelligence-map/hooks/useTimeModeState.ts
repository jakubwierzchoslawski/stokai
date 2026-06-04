/**
 * useTimeModeState.ts — useReducer-based hook owning all time-mode state.
 *
 * State: { timeMode, dateRange, playbackSpeed }
 * Actions: SET_TIME_MODE, SET_DATE_RANGE, SET_PLAYBACK_SPEED
 *
 * Guard: transitioning to "live" resets dateRange to null and playbackSpeed
 * to "1x" atomically so downstream subscribers never observe an inconsistent
 * state (e.g. timeMode="live" with a stale dateRange).
 *
 * Guard: transitioning to "historical" or "playback" preserves an existing
 * dateRange across mode switches.
 *
 * PLAN-F-021 TASK-002
 */

import { useReducer } from 'react';
import type { TimeMode, PlaybackSpeed, DateRange } from '../types/time-mode.types';

// ── State ─────────────────────────────────────────────────────────────────────

export interface TimeModeState {
  timeMode: TimeMode;
  dateRange: DateRange | null;
  playbackSpeed: PlaybackSpeed;
}

// ── Actions ───────────────────────────────────────────────────────────────────

type TimeModeAction =
  | { type: 'SET_TIME_MODE'; payload: TimeMode }
  | { type: 'SET_DATE_RANGE'; payload: DateRange | null }
  | { type: 'SET_PLAYBACK_SPEED'; payload: PlaybackSpeed };

// ── Initial state ─────────────────────────────────────────────────────────────

const INITIAL_STATE: TimeModeState = {
  timeMode: 'live',
  dateRange: null,
  playbackSpeed: '1x',
};

// ── Reducer ───────────────────────────────────────────────────────────────────

export function timeModeReducer(
  state: TimeModeState,
  action: TimeModeAction,
): TimeModeState {
  switch (action.type) {
    case 'SET_TIME_MODE': {
      if (action.payload === 'live') {
        // Reset both dateRange and playbackSpeed atomically on live re-entry.
        return {
          timeMode: 'live',
          dateRange: null,
          playbackSpeed: '1x',
        };
      }
      // Transitioning to historical or playback: preserve existing dateRange.
      return {
        ...state,
        timeMode: action.payload,
      };
    }
    case 'SET_DATE_RANGE':
      return { ...state, dateRange: action.payload };
    case 'SET_PLAYBACK_SPEED':
      return { ...state, playbackSpeed: action.payload };
    default:
      return state;
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface UseTimeModeStateResult {
  state: TimeModeState;
  setTimeMode: (mode: TimeMode) => void;
  setDateRange: (range: DateRange | null) => void;
  setPlaybackSpeed: (speed: PlaybackSpeed) => void;
}

export function useTimeModeState(): UseTimeModeStateResult {
  const [state, dispatch] = useReducer(timeModeReducer, INITIAL_STATE);

  function setTimeMode(mode: TimeMode): void {
    dispatch({ type: 'SET_TIME_MODE', payload: mode });
  }

  function setDateRange(range: DateRange | null): void {
    dispatch({ type: 'SET_DATE_RANGE', payload: range });
  }

  function setPlaybackSpeed(speed: PlaybackSpeed): void {
    dispatch({ type: 'SET_PLAYBACK_SPEED', payload: speed });
  }

  return { state, setTimeMode, setDateRange, setPlaybackSpeed };
}
