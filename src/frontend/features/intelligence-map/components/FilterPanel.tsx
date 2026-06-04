/**
 * FilterPanel.tsx — Category and intensity checkbox filter sidebar.
 *
 * Uses standard HTML checkboxes styled with inline color swatches.
 * (shadcn/ui Checkbox can replace the native input when the UI library is available.)
 * Filter changes call the respective callback immediately — no debounce.
 *
 * PLAN-F-019 TASK-007
 */

import React from 'react';
import { CATEGORY_COLORS } from '../lib/color-palette';
import { KNOWN_CATEGORIES } from '../lib/cluster-properties';
import type { MapFilters } from '../hooks/useMapFilters';

// ── Props ─────────────────────────────────────────────────────────────────────

export interface FilterPanelProps {
  filters: MapFilters;
  onToggleCategory: (category: string) => void;
  onToggleIntensity: (level: number) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const FilterPanel: React.FC<FilterPanelProps> = ({
  filters,
  onToggleCategory,
  onToggleIntensity,
}) => {
  return (
    <div
      data-testid="filter-panel"
      style={{
        position: 'absolute',
        top: 60,
        right: 10,
        background: 'rgba(20, 20, 30, 0.85)',
        color: '#ffffff',
        borderRadius: 8,
        padding: '12px 16px',
        zIndex: 900,
        minWidth: 180,
        backdropFilter: 'blur(4px)',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>
        Categories
      </div>
      {KNOWN_CATEGORIES.map((cat) => {
        const isActive = filters.categories.includes(cat);
        return (
          <label
            key={cat}
            style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 12 }}
            data-testid={`filter-category-${cat}`}
          >
            <input
              type="checkbox"
              checked={isActive}
              onChange={() => onToggleCategory(cat)}
              data-testid={`checkbox-category-${cat}`}
            />
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: 2,
                background: CATEGORY_COLORS[cat] ?? '#CC79A7',
                display: 'inline-block',
                flexShrink: 0,
              }}
              aria-hidden="true"
            />
            <span>{cat.replace(/_/g, ' ')}</span>
          </label>
        );
      })}

      <div style={{ fontWeight: 700, marginBottom: 8, marginTop: 12, fontSize: 13 }}>
        Intensity
      </div>
      {[1, 2, 3, 4, 5].map((level) => {
        const isActive = filters.intensities.includes(level);
        return (
          <label
            key={level}
            style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, cursor: 'pointer', fontSize: 12 }}
            data-testid={`filter-intensity-${level}`}
          >
            <input
              type="checkbox"
              checked={isActive}
              onChange={() => onToggleIntensity(level)}
              data-testid={`checkbox-intensity-${level}`}
            />
            <span>Level {level}</span>
          </label>
        );
      })}
    </div>
  );
};

export default FilterPanel;
