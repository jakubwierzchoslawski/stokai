/**
 * DateRangeSlider.tsx — Controlled date-range input component.
 *
 * Renders two date pickers (from_date, to_date) with validation:
 * - from_date must be before to_date
 * - Maximum range: 365 days
 * "Load" button is disabled when the range is invalid.
 *
 * PLAN-F-021 TASK-007
 */

import React, { useState } from 'react';
import type { DateRange } from '../types/time-mode.types';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface DateRangeSliderProps {
  from_date: string;
  to_date: string;
  onSetRange: (range: DateRange) => void;
}

// ── Validation helpers ────────────────────────────────────────────────────────

function parseDate(iso: string): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function daysBetween(from: Date, to: Date): number {
  return (to.getTime() - from.getTime()) / (1000 * 60 * 60 * 24);
}

const MAX_RANGE_DAYS = 365;

// ── Component ─────────────────────────────────────────────────────────────────

const DateRangeSlider: React.FC<DateRangeSliderProps> = ({
  from_date,
  to_date,
  onSetRange,
}) => {
  const [localFrom, setLocalFrom] = useState<string>(from_date);
  const [localTo, setLocalTo] = useState<string>(to_date);

  const fromDate = parseDate(localFrom);
  const toDate = parseDate(localTo);

  let validationError: string | null = null;

  if (fromDate && toDate) {
    if (fromDate >= toDate) {
      validationError = 'From date must be before to date.';
    } else if (daysBetween(fromDate, toDate) > MAX_RANGE_DAYS) {
      validationError = 'Date range exceeds 1 year. Please choose a shorter range.';
    }
  } else if (localFrom && localTo && (!fromDate || !toDate)) {
    validationError = 'Invalid date format. Use YYYY-MM-DD.';
  }

  const isLoadEnabled = fromDate !== null && toDate !== null && validationError === null;

  function handleLoad() {
    if (!isLoadEnabled) return;
    onSetRange({ from_date: localFrom, to_date: localTo });
  }

  return (
    <div
      data-testid="date-range-slider"
      className="mt-2 flex flex-col gap-1.5"
    >
      <div className="flex items-center gap-2">
        <label htmlFor="date-range-from" className="text-[11px] text-muted">
          From
        </label>
        <input
          id="date-range-from"
          data-testid="date-range-from"
          type="date"
          value={localFrom}
          onChange={(e) => setLocalFrom(e.target.value)}
          className="rounded-sm border border-subtle bg-surface-1/90 px-1.5 py-0.5 text-[11px] text-text"
        />
        <label htmlFor="date-range-to" className="text-[11px] text-muted">
          To
        </label>
        <input
          id="date-range-to"
          data-testid="date-range-to"
          type="date"
          value={localTo}
          onChange={(e) => setLocalTo(e.target.value)}
          className="rounded-sm border border-subtle bg-surface-1/90 px-1.5 py-0.5 text-[11px] text-text"
        />
      </div>

      {validationError && (
        <span
          data-testid="date-range-error"
          className="text-[11px] text-[var(--negative)]"
          role="alert"
        >
          {validationError}
        </span>
      )}

      <button
        data-testid="date-range-load"
        onClick={handleLoad}
        disabled={!isLoadEnabled}
        className={[
          "self-start rounded-sm border-0 px-3 py-1 text-[11px] text-white",
          isLoadEnabled
            ? "cursor-pointer bg-signal"
            : "cursor-not-allowed bg-surface-3",
        ].join(" ")}
        aria-disabled={!isLoadEnabled}
      >
        Load
      </button>
    </div>
  );
};

export default DateRangeSlider;
