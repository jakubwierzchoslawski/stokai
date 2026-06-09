/**
 * MapContextSwitcher.tsx — Three-button mode toggle: Global / Portfolio / Sector.
 *
 * Rendered as an absolute-positioned overlay at the top-left of the map canvas.
 * When "Sector" is selected, a sector dropdown appears.
 *
 * PLAN-F-019 TASK-009
 */

import React from 'react';
import type { MapMode } from '../hooks/useMapMode';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface MapContextSwitcherProps {
  mode: MapMode;
  sector: string | null;
  onSetMode: (mode: MapMode) => void;
  onSetSector?: (sector: string) => void;
}

// ── Available sectors ─────────────────────────────────────────────────────────

const SECTORS = [
  'Energy',
  'Financials',
  'Technology',
  'Healthcare',
  'Industrials',
  'Materials',
  'Consumer Staples',
  'Consumer Discretionary',
  'Utilities',
  'Real Estate',
  'Communication Services',
];

// ── Component ─────────────────────────────────────────────────────────────────

const MODES: MapMode[] = ['global', 'portfolio', 'sector'];
const MODE_LABELS: Record<MapMode, string> = {
  global: 'Global',
  portfolio: 'Portfolio',
  sector: 'Sector',
};

export const MapContextSwitcher: React.FC<MapContextSwitcherProps> = ({
  mode,
  sector,
  onSetMode,
  onSetSector,
}) => {
  return (
    <div
      data-testid="map-context-switcher"
      className="absolute left-2.5 top-2.5 z-[900] flex flex-col gap-1.5"
    >
      <div className="flex overflow-hidden rounded-md bg-surface-1/85 backdrop-blur">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onSetMode(m)}
            data-testid={`mode-button-${m}`}
            className={[
              "border-0 px-3.5 py-1.5 text-[13px] text-text transition-colors",
              mode === m
                ? "bg-signal font-bold"
                : "bg-transparent font-normal hover:bg-surface-2/60",
            ].join(" ")}
            aria-pressed={mode === m}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      {mode === 'sector' && (
        <select
          data-testid="sector-select"
          value={sector ?? ''}
          onChange={(e) => onSetSector?.(e.target.value)}
          className="rounded-md border border-subtle bg-surface-1/85 px-2 py-1 text-[13px] text-text backdrop-blur"
        >
          <option value="" disabled>
            Select sector
          </option>
          {SECTORS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      )}
    </div>
  );
};

export default MapContextSwitcher;
