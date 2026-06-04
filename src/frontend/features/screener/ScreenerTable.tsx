/**
 * ScreenerTable — paginated, sortable table for Company Screener rows.
 *
 * Columns: Ticker, Name, Sector, Market Cap, Custom Score, Score Delta,
 *          Price, Active Events.
 *
 * Behaviour:
 *   - Clicking a header toggles sort asc/desc on that column.
 *   - "Load more" button at the bottom triggers the next page fetch.
 *   - Visual sort indicator (↑/↓) on the active column.
 *
 * Responsive layout (REQ-N-014):
 *   - Tablet viewports (768px–1024px): Market Cap and Active Events columns
 *     are hidden via CSS class to keep the table readable.
 *   - Below 768px is out of scope — mobile not required per REQ-N-014.
 *
 * // mobile not required — REQ-N-014 scope: tablet+
 */
import React from "react";
import type { ScreenerColumn, ScreenerRow, SortDir } from "./screenerTypes";

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

interface ColumnDef {
  key: ScreenerColumn;
  label: string;
  /** When true, column hides at tablet breakpoint (768px–1024px). */
  collapseOnTablet?: boolean;
  render?: (row: ScreenerRow) => React.ReactNode;
}

const COLUMNS: ColumnDef[] = [
  { key: "ticker", label: "Ticker" },
  { key: "name", label: "Name" },
  { key: "sector", label: "Sector" },
  { key: "market_cap", label: "Market Cap", collapseOnTablet: true,
    render: (r) => r.market_cap.toLocaleString("en-US", { maximumFractionDigits: 0 }) },
  { key: "custom_score", label: "Custom Score",
    render: (r) => r.custom_score.toFixed(2) },
  { key: "score_delta", label: "Score Delta",
    render: (r) => {
      const sign = r.score_delta >= 0 ? "+" : "";
      return `${sign}${r.score_delta.toFixed(2)}`;
    } },
  { key: "current_price", label: "Price",
    render: (r) => r.current_price.toFixed(2) },
  { key: "active_events_count", label: "Active Events", collapseOnTablet: true },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface ScreenerTableProps {
  rows: ScreenerRow[];
  sortColumn: ScreenerColumn;
  sortDir: SortDir;
  onSortChange: (column: ScreenerColumn, dir: SortDir) => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}

export function ScreenerTable({
  rows,
  sortColumn,
  sortDir,
  onSortChange,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
}: ScreenerTableProps) {
  function handleHeaderClick(col: ColumnDef) {
    if (col.key === sortColumn) {
      // Toggle direction
      onSortChange(col.key, sortDir === "asc" ? "desc" : "asc");
    } else {
      onSortChange(col.key, "desc");
    }
  }

  return (
    <div className="screener-table-wrapper" style={{ overflowX: "auto" }}>
      <table className="screener-table" aria-label="Company screener results">
        <thead>
          <tr>
            {COLUMNS.map((col) => {
              const isActive = col.key === sortColumn;
              const indicator = isActive ? (sortDir === "asc" ? " ↑" : " ↓") : "";
              const thClass = [
                "screener-table__th",
                col.collapseOnTablet ? "screener-table__th--collapse-tablet" : "",
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <th
                  key={col.key}
                  className={thClass}
                  onClick={() => handleHeaderClick(col)}
                  aria-sort={
                    isActive ? (sortDir === "asc" ? "ascending" : "descending") : undefined
                  }
                  style={{ cursor: "pointer", userSelect: "none" }}
                >
                  {col.label}
                  {indicator && (
                    <span aria-hidden="true" className="screener-table__sort-indicator">
                      {indicator}
                    </span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.company_id} className="screener-table__row">
              {COLUMNS.map((col) => {
                const tdClass = [
                  "screener-table__td",
                  col.collapseOnTablet ? "screener-table__td--collapse-tablet" : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                return (
                  <td key={col.key} className={tdClass}>
                    {col.render ? col.render(row) : String(row[col.key])}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {hasNextPage && (
        <div className="screener-table__load-more">
          <button
            onClick={onLoadMore}
            disabled={isFetchingNextPage}
            aria-label="Load more companies"
            className="screener-table__load-more-btn"
          >
            {isFetchingNextPage ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}

export default ScreenerTable;
