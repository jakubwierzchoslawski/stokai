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
      className="absolute right-3 top-3 z-[900] flex min-w-[220px] flex-col gap-1 rounded-lg bg-surface-1/85 px-3 py-2 backdrop-blur"
    >
      {/* Mode toggle group */}
      <div role="group" aria-label="Time mode" className="flex gap-1">
        {MODES.map(({ value, label }) => (
          <button
            key={value}
            data-testid={`time-mode-btn-${value}`}
            onClick={() => onSetTimeMode(value)}
            aria-pressed={timeMode === value}
            className={[
              "rounded-md border-0 px-2.5 py-1 text-xs text-text",
              timeMode === value
                ? "bg-signal font-bold"
                : "bg-surface-2/60 font-normal hover:bg-surface-3/60",
            ].join(" ")}
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
