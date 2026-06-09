/**
 * usePlayback.ts — Animation engine wrapper hook.
 *
 * Wraps PlaybackEngine in a React useRef (so the engine instance survives
 * re-renders) and drives a requestAnimationFrame tick loop.
 *
 * Exposed state:  { isPlaying, visibleEvents, virtualNow, isComplete }
 * Exposed methods: play(), pause(), reset()
 *
 * PLAN-F-021 TASK-004
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { PlaybackEngine } from '../lib/playback-engine';
import type { EventPulse } from '../types/map.types';
import type { PlaybackSpeed } from '../types/time-mode.types';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface UsePlaybackResult {
  isPlaying: boolean;
  visibleEvents: EventPulse[];
  virtualNow: Date | null;
  isComplete: boolean;
  play: () => void;
  pause: () => void;
  reset: () => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function usePlayback(
  events: EventPulse[],
  speed: PlaybackSpeed,
): UsePlaybackResult {
  const engineRef = useRef<PlaybackEngine>(new PlaybackEngine(events, speed));

  // Mutable refs for the animation loop — no re-render on change.
  const rafIdRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const pausedElapsedRef = useRef<number>(0);

  // React state — drives re-renders.
  const [isPlaying, setIsPlaying] = useState(false);
  const [visibleEvents, setVisibleEvents] = useState<EventPulse[]>([]);
  const [virtualNow, setVirtualNow] = useState<Date | null>(null);
  const [isComplete, setIsComplete] = useState(false);

  // Rebuild the engine whenever events or speed changes.
  const eventsRef = useRef(events);
  const speedRef = useRef(speed);

  const isCompleteRef = useRef(isComplete);
  isCompleteRef.current = isComplete;

  useEffect(() => {
    eventsRef.current = events;
    speedRef.current = speed;
    // Cancel any active RAF loop.
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    engineRef.current = new PlaybackEngine(events, speed);
    engineRef.current.reset();
    pausedElapsedRef.current = 0;
    startTimeRef.current = null;
    setIsPlaying(false);
    setVisibleEvents((prev) => (prev.length === 0 ? prev : []));
    setVirtualNow(null);
    setIsComplete(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, speed]);

  const cancelLoop = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const tick = useCallback(
    (_frameTime: number) => {
      if (startTimeRef.current === null) return;

      const wallElapsed = performance.now() - startTimeRef.current + pausedElapsedRef.current;
      const { visibleEvents: nextEvents, virtualNow: nextNow } =
        engineRef.current.tick(wallElapsed);

      setVisibleEvents(nextEvents);
      setVirtualNow(nextNow);

      // Detect completion: all events visible and wallElapsed exceeds window.
      // PlaybackEngine.tick clamps virtualNow to virtualWindowEnd; compare counts.
      const allEventsVisible =
        eventsRef.current.length > 0 &&
        nextEvents.length === eventsRef.current.length;

      if (allEventsVisible) {
        setIsComplete(true);
        setIsPlaying(false);
        rafIdRef.current = null;
        return; // Do not schedule the next frame.
      }

      // Schedule next frame.
      rafIdRef.current = requestAnimationFrame(tick);
    },
    [],
  );

  const play = useCallback(() => {
    if (isCompleteRef.current) return; // Do not restart after completion; use reset() first.
    if (rafIdRef.current !== null) return; // Already playing — idempotent.

    setIsPlaying(true);
    startTimeRef.current = performance.now();
    rafIdRef.current = requestAnimationFrame(tick);
  }, [tick]);

  const pause = useCallback(() => {
    if (startTimeRef.current !== null) {
      pausedElapsedRef.current += performance.now() - startTimeRef.current;
    }
    startTimeRef.current = null;
    cancelLoop();
    setIsPlaying(false);
  }, [cancelLoop]);

  const reset = useCallback(() => {
    cancelLoop();
    engineRef.current.reset();
    pausedElapsedRef.current = 0;
    startTimeRef.current = null;
    setIsPlaying(false);
    setVisibleEvents([]);
    setVirtualNow(null);
    setIsComplete(false);
  }, [cancelLoop]);

  // Clean up on unmount.
  useEffect(() => {
    return () => {
      cancelLoop();
    };
  }, [cancelLoop]);

  return { isPlaying, visibleEvents, virtualNow, isComplete, play, pause, reset };
}
