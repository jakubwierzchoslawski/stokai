/**
 * ScreenerFilterBar — dynamic filter row builder for the Company Screener.
 *
 * Each filter row has:
 *   - Column dropdown (from SCREENER_COLUMN_WHITELIST)
 *   - Operator dropdown (numeric: gt/lt/eq; text: eq/contains)
 *   - Value input
 *   - AND/OR selector (hidden for the first row — it has no predecessor)
 *   - Remove button
 *
 * Filters are accumulated in local state; "Apply" fires onApply with the
 * current list.  No API call fires on every keystroke.
 */
import React, { useState } from "react";
import type { FilterOperator, LogicalOp, ScreenerColumn, ScreenerFilter } from "./screenerTypes";
import {
  NUMERIC_COLUMNS,
  SCREENER_COLUMN_WHITELIST,
  TEXT_COLUMNS,
} from "./screenerTypes";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function defaultOperatorForColumn(col: ScreenerColumn): FilterOperator {
  if (NUMERIC_COLUMNS.has(col)) return "gt";
  return "eq";
}

function operatorsForColumn(col: ScreenerColumn): FilterOperator[] {
  if (NUMERIC_COLUMNS.has(col)) return ["gt", "lt", "eq"];
  return ["eq", "contains"];
}

function emptyFilter(column: ScreenerColumn = "ticker"): ScreenerFilter {
  return {
    column,
    operator: defaultOperatorForColumn(column),
    value: "",
    logical_op: "AND",
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface ScreenerFilterBarProps {
  onApply: (filters: ScreenerFilter[]) => void;
}

export function ScreenerFilterBar({ onApply }: ScreenerFilterBarProps) {
  const [filters, setFilters] = useState<ScreenerFilter[]>([]);

  function addFilter() {
    setFilters((prev) => [...prev, emptyFilter()]);
  }

  function removeFilter(index: number) {
    setFilters((prev) => prev.filter((_, i) => i !== index));
  }

  function updateFilter(index: number, patch: Partial<ScreenerFilter>) {
    setFilters((prev) =>
      prev.map((f, i) => {
        if (i !== index) return f;
        const updated = { ...f, ...patch };
        // Reset operator when column type changes
        if (patch.column && patch.column !== f.column) {
          updated.operator = defaultOperatorForColumn(patch.column as ScreenerColumn);
        }
        return updated;
      }),
    );
  }

  function handleApply() {
    onApply(filters);
  }

  return (
    <div className="screener-filter-bar" aria-label="Filter bar">
      {filters.map((filter, idx) => (
        <div key={idx} className="screener-filter-bar__row" data-testid={`filter-row-${idx}`}>
          {/* AND/OR selector — hidden for first row */}
          {idx > 0 && (
            <select
              aria-label={`Logical operator for filter ${idx + 1}`}
              value={filter.logical_op}
              onChange={(e) =>
                updateFilter(idx, { logical_op: e.target.value as LogicalOp })
              }
              className="screener-filter-bar__logical-op"
            >
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
          )}

          {/* Column selector */}
          <select
            aria-label={`Column for filter ${idx + 1}`}
            value={filter.column}
            onChange={(e) =>
              updateFilter(idx, { column: e.target.value as ScreenerColumn })
            }
            className="screener-filter-bar__column"
          >
            {SCREENER_COLUMN_WHITELIST.map((col) => (
              <option key={col} value={col}>
                {col}
              </option>
            ))}
          </select>

          {/* Operator selector */}
          <select
            aria-label={`Operator for filter ${idx + 1}`}
            value={filter.operator}
            onChange={(e) =>
              updateFilter(idx, { operator: e.target.value as FilterOperator })
            }
            className="screener-filter-bar__operator"
          >
            {operatorsForColumn(filter.column).map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>

          {/* Value input */}
          <input
            aria-label={`Value for filter ${idx + 1}`}
            type={NUMERIC_COLUMNS.has(filter.column) ? "number" : "text"}
            value={String(filter.value)}
            onChange={(e) => updateFilter(idx, { value: e.target.value })}
            className="screener-filter-bar__value"
          />

          {/* Remove button */}
          <button
            aria-label={`Remove filter ${idx + 1}`}
            onClick={() => removeFilter(idx)}
            className="screener-filter-bar__remove"
          >
            Remove
          </button>
        </div>
      ))}

      <div className="screener-filter-bar__controls">
        <button
          aria-label="Add filter"
          onClick={addFilter}
          className="screener-filter-bar__add"
        >
          Add filter
        </button>

        {filters.length > 0 && (
          <button
            aria-label="Apply filters"
            onClick={handleApply}
            className="screener-filter-bar__apply"
          >
            Apply
          </button>
        )}
      </div>
    </div>
  );
}

export default ScreenerFilterBar;
