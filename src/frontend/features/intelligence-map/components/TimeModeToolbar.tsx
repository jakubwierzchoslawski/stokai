/**
 * TimeModeToolbar.tsx — Mode toggle (Live / Historical / Playback) with
 * conditional DateRangeSlider overlay at top-right of the map canvas.
 *
 * Conditional rendering:
 *  - timeMode="live": only the toggle is shown.
 *  - timeMode="historical" or "playback": DateRangeSlider is shown below.
 *
 * The "Load" button inside DateRangeSlider triggers the historical fetch only
 * on explicit user confirmation (not on every slider drag).
 *
 * PLAN-F-021 TASK-007
 */

import React from 'react';
import DateRangeSlider from './DateRangeSlider';
import type { TimeMode, DateRange } from '../types/time-mode.types';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface TimeModeToolbarProps {
  timeMode: TimeMode;
  dateRange: DateRange | null;
  onSetTimeMode: (mode: TimeMode) => void;
  onSetDateRange: (range: DateRange | null) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

const MODES: { value: TimeMode; label: string }[] = [
  { value: 'live', label: 'Live' },
  { value: 'historical', label: 'Historical' },
  { value: 'playback', label: 'Playback' },
];

const TimeModeToolbar: React.FC<TimeModeToolbarProps> = ({
  timeMode,
  dateRange,
  onSetTimeMode,
  onSetDateRange,
}) => {
  const showDateRange = timeMode === 'historical' || timeMode === 'playback';

  return (
    <div
      data-testid="time-mode-toolbar"
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        zIndex: 900,
        background: 'rgba(20, 20, 30, 0.85)',
        borderRadius: 8,
        padding: '8px 12px',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        minWidth: 220,
      }}
    >
      {/* Mode toggle group */}
      <div
        role="group"
        aria-label="Time mode"
        style={{ display: 'flex', gap: 4 }}
      >
        {MODES.map(({ value, label }) => (
          <button
            key={value}
            data-testid={`time-mode-btn-${value}`}
            onClick={() => onSetTimeMode(value)}
            aria-pressed={timeMode === value}
            style={{
              background: timeMode === value ? '#2563eb' : 'rgba(80,80,100,0.6)',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 12,
              cursor: 'pointer',
              fontWeight: timeMode === value ? 700 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Conditional date-range picker */}
      {showDateRange && (
        <DateRangeSlider
          from_date={dateRange?.from_date ?? ''}
          to_date={dateRange?.to_date ?? ''}
          onSetRange={onSetDateRange}
        />
      )}
    </div>
  );
};

export default TimeModeToolbar;
