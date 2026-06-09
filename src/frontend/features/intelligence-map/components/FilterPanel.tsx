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
      className="absolute right-2.5 top-[60px] z-[900] min-w-[180px] rounded-lg bg-surface-1/85 px-4 py-3 text-text backdrop-blur"
    >
      <div className="mb-2 text-[13px] font-bold">Categories</div>
      {KNOWN_CATEGORIES.map((cat) => {
        const isActive = filters.categories.includes(cat);
        return (
          <label
            key={cat}
            className="mb-1.5 flex cursor-pointer items-center gap-2 text-xs"
            data-testid={`filter-category-${cat}`}
          >
            <input
              type="checkbox"
              checked={isActive}
              onChange={() => onToggleCategory(cat)}
              data-testid={`checkbox-category-${cat}`}
            />
            <span
              className="inline-block h-3 w-3 shrink-0 rounded-sm"
              style={{ background: CATEGORY_COLORS[cat] ?? '#CC79A7' }}
              aria-hidden="true"
            />
            <span>{cat.replace(/_/g, ' ')}</span>
          </label>
        );
      })}

      <div className="mb-2 mt-3 text-[13px] font-bold">Intensity</div>
      {[1, 2, 3, 4, 5].map((level) => {
        const isActive = filters.intensities.includes(level);
        return (
          <label
            key={level}
            className="mb-1.5 flex cursor-pointer items-center gap-2 text-xs"
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
