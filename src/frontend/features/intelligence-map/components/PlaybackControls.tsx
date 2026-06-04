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
      style={{
        position: 'absolute',
        bottom: 32,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 900,
        background: 'rgba(20, 20, 30, 0.9)',
        borderRadius: 8,
        padding: '10px 16px',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        minWidth: 280,
      }}
    >
      {/* Controls row */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {/* Play button — visible when not playing and not complete */}
        {!isPlaying && !isComplete && (
          <button
            data-testid="playback-btn-play"
            onClick={onPlay}
            style={btnStyle('#16a34a')}
            aria-label="Play"
          >
            ▶ Play
          </button>
        )}

        {/* Pause button — visible when playing */}
        {isPlaying && (
          <button
            data-testid="playback-btn-pause"
            onClick={onPause}
            style={btnStyle('#ca8a04')}
            aria-label="Pause"
          >
            ⏸ Pause
          </button>
        )}

        {/* Reset button — always visible */}
        <button
          data-testid="playback-btn-reset"
          onClick={onReset}
          style={btnStyle('#6b7280')}
          aria-label="Reset"
        >
          ↺ Reset
        </button>

        {/* Speed selector */}
        <select
          data-testid="playback-speed-select"
          value={speed}
          onChange={(e) => onSetSpeed(e.target.value as PlaybackSpeed)}
          style={{
            background: 'rgba(40,40,60,0.9)',
            color: '#fff',
            border: '1px solid #555',
            borderRadius: 4,
            padding: '2px 6px',
            fontSize: 12,
            cursor: 'pointer',
          }}
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
      <div style={{ position: 'relative' }}>
        <div
          style={{
            background: 'rgba(80,80,100,0.5)',
            borderRadius: 4,
            height: 6,
            overflow: 'hidden',
          }}
        >
          <div
            data-testid="playback-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct}
            style={{
              background: isComplete ? '#16a34a' : '#2563eb',
              width: `${progressPct}%`,
              height: '100%',
              transition: 'width 0.1s ease',
            }}
          />
        </div>

        {/* Complete label */}
        {isComplete && (
          <span
            data-testid="playback-complete-label"
            style={{
              position: 'absolute',
              right: 0,
              top: -18,
              color: '#16a34a',
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            Complete
          </span>
        )}
      </div>
    </div>
  );
};

// ── Style helper ──────────────────────────────────────────────────────────────

function btnStyle(bg: string): React.CSSProperties {
  return {
    background: bg,
    color: '#fff',
    border: 'none',
    borderRadius: 5,
    padding: '4px 10px',
    fontSize: 12,
    cursor: 'pointer',
    fontWeight: 600,
  };
}

export default PlaybackControls;
