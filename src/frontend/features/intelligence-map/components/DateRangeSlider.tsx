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
    <div data-testid="date-range-slider" style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <label htmlFor="date-range-from" style={{ color: '#ccc', fontSize: 11 }}>
          From
        </label>
        <input
          id="date-range-from"
          data-testid="date-range-from"
          type="date"
          value={localFrom}
          onChange={(e) => setLocalFrom(e.target.value)}
          style={{
            background: 'rgba(20,20,30,0.9)',
            color: '#fff',
            border: '1px solid #555',
            borderRadius: 4,
            padding: '2px 6px',
            fontSize: 11,
          }}
        />
        <label htmlFor="date-range-to" style={{ color: '#ccc', fontSize: 11 }}>
          To
        </label>
        <input
          id="date-range-to"
          data-testid="date-range-to"
          type="date"
          value={localTo}
          onChange={(e) => setLocalTo(e.target.value)}
          style={{
            background: 'rgba(20,20,30,0.9)',
            color: '#fff',
            border: '1px solid #555',
            borderRadius: 4,
            padding: '2px 6px',
            fontSize: 11,
          }}
        />
      </div>

      {validationError && (
        <span
          data-testid="date-range-error"
          style={{ color: '#f66', fontSize: 11 }}
          role="alert"
        >
          {validationError}
        </span>
      )}

      <button
        data-testid="date-range-load"
        onClick={handleLoad}
        disabled={!isLoadEnabled}
        style={{
          background: isLoadEnabled ? '#2563eb' : '#555',
          color: '#fff',
          border: 'none',
          borderRadius: 4,
          padding: '4px 12px',
          fontSize: 11,
          cursor: isLoadEnabled ? 'pointer' : 'not-allowed',
          alignSelf: 'flex-start',
        }}
        aria-disabled={!isLoadEnabled}
      >
        Load
      </button>
    </div>
  );
};

export default DateRangeSlider;
