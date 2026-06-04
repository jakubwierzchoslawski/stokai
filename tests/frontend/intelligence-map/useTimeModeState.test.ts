/**
 * useTimeModeState.test.ts — TDD tests for the time-mode state hook.
 *
 * PLAN-F-021 TASK-002
 */

import { renderHook, act } from '@testing-library/react';
import { useTimeModeState } from '../../../src/frontend/features/intelligence-map/hooks/useTimeModeState';

describe('useTimeModeState', () => {
  it('has correct initial state', () => {
    const { result } = renderHook(() => useTimeModeState());
    expect(result.current.state.timeMode).toBe('live');
    expect(result.current.state.dateRange).toBeNull();
    expect(result.current.state.playbackSpeed).toBe('1x');
  });

  it('SET_TIME_MODE("historical") transitions timeMode without clearing an existing dateRange', () => {
    const { result } = renderHook(() => useTimeModeState());
    act(() => {
      result.current.setDateRange({ from_date: '2025-01-01', to_date: '2025-01-31' });
    });
    act(() => {
      result.current.setTimeMode('historical');
    });
    expect(result.current.state.timeMode).toBe('historical');
    expect(result.current.state.dateRange).toEqual({ from_date: '2025-01-01', to_date: '2025-01-31' });
  });

  it('SET_TIME_MODE("live") from "historical" resets dateRange to null and playbackSpeed to "1x"', () => {
    const { result } = renderHook(() => useTimeModeState());
    act(() => {
      result.current.setTimeMode('historical');
    });
    act(() => {
      result.current.setDateRange({ from_date: '2025-01-01', to_date: '2025-01-31' });
    });
    act(() => {
      result.current.setPlaybackSpeed('16x');
    });
    act(() => {
      result.current.setTimeMode('live');
    });
    expect(result.current.state.timeMode).toBe('live');
    expect(result.current.state.dateRange).toBeNull();
    expect(result.current.state.playbackSpeed).toBe('1x');
  });

  it('SET_DATE_RANGE sets dateRange correctly', () => {
    const { result } = renderHook(() => useTimeModeState());
    act(() => {
      result.current.setDateRange({ from_date: '2025-01-01', to_date: '2025-01-31' });
    });
    expect(result.current.state.dateRange).toEqual({ from_date: '2025-01-01', to_date: '2025-01-31' });
  });

  it('SET_PLAYBACK_SPEED("16x") updates playbackSpeed to "16x"', () => {
    const { result } = renderHook(() => useTimeModeState());
    act(() => {
      result.current.setPlaybackSpeed('16x');
    });
    expect(result.current.state.playbackSpeed).toBe('16x');
  });

  it('SET_TIME_MODE("playback") from "live" with no prior dateRange leaves dateRange as null', () => {
    const { result } = renderHook(() => useTimeModeState());
    act(() => {
      result.current.setTimeMode('playback');
    });
    expect(result.current.state.timeMode).toBe('playback');
    expect(result.current.state.dateRange).toBeNull();
  });
});
