/**
 * PlaybackControls.tsx — Play / Pause / Reset buttons + speed selector.
 *
 * Purely presentational — all state lives in usePlayback.
 * Visible only when timeMode="playback" (controlled by parent IntelligenceMap).
 *
 * Controls:
 *  - Play button: visible when !isPlaying && !isComplete
 *  - Pause button: visible when isPlaying
 *  - Reset button: always visible
 *  - Speed selector: 1×, 4×, 16×
 *  - Progress indicator: linear bar + optional "Complete" label
 *
 * PLAN-F-021 TASK-008
 */

import React from 'react';
import type { PlaybackSpeed } from '../types/time-mode.types';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface PlaybackControlsProps {
  isPlaying: boolean;
  isComplete: boolean;
  speed: PlaybackSpeed;
  /** Number of events currently visible in the playback window. */
  visibleCount: number;
  /** Total events in the loaded event window. */
  totalCount: number;
  onPlay: () => void;
  onPause: () => void;
  onReset: () => void;
  onSetSpeed: (speed: PlaybackSpeed) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

const SPEED_OPTIONS: PlaybackSpeed[] = ['1x', '4x', '16x'];

const PlaybackControls: React.FC<PlaybackControlsProps> = ({
  isPlaying,
  isComplete,
  speed,
  visibleCount,
  totalCount,
  onPlay,
  onPause,
  onReset,
  onSetSpeed,
}) => {
  const progressPct = totalCount > 0 ? Math.round((visibleCount / totalCount) * 100) : 0;

  return (
    <div
      data-testid="playback-controls"
      className="absolute bottom-8 left-1/2 z-[900] flex min-w-[280px] -translate-x-1/2 flex-col gap-2 rounded-lg bg-surface-1/90 px-4 py-2.5 backdrop-blur"
    >
      {/* Controls row */}
      <div className="flex items-center gap-2">
        {!isPlaying && !isComplete && (
          <button
            data-testid="playback-btn-play"
            onClick={onPlay}
            className="rounded border-0 bg-[var(--positive)] px-2.5 py-1 text-xs font-semibold text-white"
            aria-label="Play"
          >
            ▶ Play
          </button>
        )}

        {isPlaying && (
          <button
            data-testid="playback-btn-pause"
            onClick={onPause}
            className="rounded border-0 bg-[var(--warning)] px-2.5 py-1 text-xs font-semibold text-white"
            aria-label="Pause"
          >
            ⏸ Pause
          </button>
        )}

        <button
          data-testid="playback-btn-reset"
          onClick={onReset}
          className="rounded border-0 bg-surface-3 px-2.5 py-1 text-xs font-semibold text-text"
          aria-label="Reset"
        >
          ↺ Reset
        </button>

        <select
          data-testid="playback-speed-select"
          value={speed}
          onChange={(e) => onSetSpeed(e.target.value as PlaybackSpeed)}
          className="rounded-sm border border-subtle bg-surface-2/90 px-1.5 py-0.5 text-xs text-text"
          aria-label="Playback speed"
        >
          {SPEED_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      {/* Progress bar */}
      <div className="relative">
        <div className="h-1.5 overflow-hidden rounded-sm bg-surface-3/50">
          <div
            data-testid="playback-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct}
            className={[
              "h-full transition-[width] duration-100 ease-linear",
              isComplete ? "bg-[var(--positive)]" : "bg-signal",
            ].join(" ")}
            style={{ width: `${progressPct}%` }}
          />
        </div>

        {isComplete && (
          <span
            data-testid="playback-complete-label"
            className="absolute -top-[18px] right-0 text-[11px] font-semibold text-[var(--positive)]"
          >
            Complete
          </span>
        )}
      </div>
    </div>
  );
};

export default PlaybackControls;
