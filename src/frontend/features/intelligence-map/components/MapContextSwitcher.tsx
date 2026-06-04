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
      style={{
        position: 'absolute',
        top: 10,
        left: 10,
        zIndex: 900,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div
        style={{
          display: 'flex',
          background: 'rgba(20, 20, 30, 0.85)',
          borderRadius: 6,
          overflow: 'hidden',
          backdropFilter: 'blur(4px)',
        }}
      >
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onSetMode(m)}
            data-testid={`mode-button-${m}`}
            style={{
              padding: '6px 14px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: mode === m ? 700 : 400,
              background: mode === m ? '#0072B2' : 'transparent',
              color: '#ffffff',
              fontSize: 13,
              transition: 'background 0.15s',
            }}
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
          style={{
            background: 'rgba(20, 20, 30, 0.85)',
            color: '#ffffff',
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 6,
            padding: '4px 8px',
            fontSize: 13,
            backdropFilter: 'blur(4px)',
          }}
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
