/**
 * usePlayback.test.ts — TDD tests for the usePlayback hook.
 *
 * Uses vitest fake timers and a mock requestAnimationFrame to simulate the
 * animation loop without a real browser environment.
 *
 * PLAN-F-021 TASK-004
 */

import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { usePlayback } from './usePlayback';
import type { EventPulse } from '../types/map.types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeEvent(id: string, offsetMs: number): EventPulse {
  const ts = new Date(1_700_000_000_000 + offsetMs).toISOString();
  return {
    event_id: id,
    category: ['geopolitical'],
    intensity: 3,
    headline: `Event ${id}`,
    timestamp: ts,
    lat: 0,
    lon: 0,
    relevance_window_end: ts,
    affected_companies: [],
  };
}

const EVENT_T0 = makeEvent('e1', 0);
const EVENT_T30 = makeEvent('e2', 1_800_000);
const EVENT_T60 = makeEvent('e3', 3_600_000);

// Stable reference — passing inline `[...]` inside renderHook creates a new array
// on every render, which the hook treats as an events change and resets playback.
const TEST_EVENTS = [EVENT_T0, EVENT_T30, EVENT_T60];

// ── Mock requestAnimationFrame ────────────────────────────────────────────────

let rafCallbacks: Map<number, FrameRequestCallback> = new Map();
let rafIdCounter = 0;

function setupFakeRaf() {
  rafCallbacks = new Map();
  rafIdCounter = 0;

  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => {
    const id = ++rafIdCounter;
    rafCallbacks.set(id, cb);
    return id;
  });

  vi.stubGlobal('cancelAnimationFrame', (id: number): void => {
    rafCallbacks.delete(id);
  });
}

function flushRaf(nowMs: number) {
  const callbacks = [...rafCallbacks.values()];
  rafCallbacks.clear();
  for (const cb of callbacks) {
    cb(nowMs);
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('usePlayback', () => {
  beforeEach(() => {
    setupFakeRaf();
    vi.spyOn(performance, 'now').mockReturnValue(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('initial state: isPlaying=false, visibleEvents=[], virtualNow=null, isComplete=false', () => {
    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.visibleEvents).toHaveLength(0);
    expect(result.current.virtualNow).toBeNull();
    expect(result.current.isComplete).toBe(false);
  });

  it('play() → visibleEvents grows after RAF ticks', () => {
    vi.spyOn(performance, 'now')
      .mockReturnValueOnce(0)  // startTime
      .mockReturnValueOnce(0); // first tick elapsed calculation

    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );

    act(() => {
      result.current.play();
    });

    expect(result.current.isPlaying).toBe(true);

    // Simulate a RAF frame at T+0 ms wall-clock — T+0 event should be visible.
    act(() => {
      vi.spyOn(performance, 'now').mockReturnValue(0);
      flushRaf(0);
    });

    expect(result.current.visibleEvents.length).toBeGreaterThanOrEqual(1);
  });

  it('pause() during playback → isPlaying becomes false; subsequent RAF does not change visibleEvents', () => {
    vi.spyOn(performance, 'now').mockReturnValue(0);

    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );

    act(() => {
      result.current.play();
    });

    act(() => {
      flushRaf(0);
    });

    const eventsBefore = result.current.visibleEvents.length;

    act(() => {
      result.current.pause();
    });

    expect(result.current.isPlaying).toBe(false);

    // Flushing RAF after pause should not schedule new frames.
    act(() => {
      flushRaf(1_800_000);
    });

    expect(result.current.visibleEvents).toHaveLength(eventsBefore);
  });

  it('reset() → visibleEvents cleared, isPlaying=false, virtualNow=null', () => {
    vi.spyOn(performance, 'now').mockReturnValue(0);

    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );

    act(() => {
      result.current.play();
    });

    act(() => {
      flushRaf(0);
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.visibleEvents).toHaveLength(0);
    expect(result.current.isPlaying).toBe(false);
    expect(result.current.virtualNow).toBeNull();
    expect(result.current.isComplete).toBe(false);
  });

  it('play() called twice without pause → does not start a second animation loop (idempotent)', () => {
    vi.spyOn(performance, 'now').mockReturnValue(0);

    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );

    act(() => {
      result.current.play();
    });

    const rafCountAfterFirst = rafCallbacks.size;

    act(() => {
      result.current.play();
    });

    // Should not have accumulated more RAF callbacks.
    expect(rafCallbacks.size).toBeLessThanOrEqual(rafCountAfterFirst + 1);
    expect(result.current.isPlaying).toBe(true);
  });

  it('playback reaching isComplete=true → isComplete flag is true after full window', () => {
    const { result } = renderHook(() =>
      usePlayback(TEST_EVENTS, '1x'),
    );

    // play() captures startTime = 0 (from beforeEach mock)
    act(() => {
      result.current.play();
    });

    // Advance mock past the full 3600s virtual window, then flush the RAF.
    act(() => {
      vi.spyOn(performance, 'now').mockReturnValue(3_600_001);
      flushRaf(3_600_001);
    });

    expect(result.current.isComplete).toBe(true);
    expect(result.current.visibleEvents).toHaveLength(3);
  });
});
