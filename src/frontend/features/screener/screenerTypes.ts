/**
 * TypeScript types for the Company Screener feature.
 *
 * SCREENER_COLUMN_WHITELIST mirrors the Python constant in
 * src/api/v1/screener/screener_service.py.  Keep both in sync when adding
 * or removing columns.
 */

export const SCREENER_COLUMN_WHITELIST = [
  "ticker",
  "name",
  "sector",
  "market_cap",
  "custom_score",
  "score_delta",
  "current_price",
  "active_events_count",
] as const;

export type ScreenerColumn = (typeof SCREENER_COLUMN_WHITELIST)[number];

/** Columns where numeric operators (gt/lt/eq) apply. */
export const NUMERIC_COLUMNS: ReadonlySet<ScreenerColumn> = new Set([
  "market_cap",
  "custom_score",
  "score_delta",
  "current_price",
  "active_events_count",
]);

/** Columns where text operators (eq/contains) apply. */
export const TEXT_COLUMNS: ReadonlySet<ScreenerColumn> = new Set([
  "ticker",
  "name",
  "sector",
]);

export type FilterOperator = "eq" | "gt" | "lt" | "contains" | "in";
export type LogicalOp = "AND" | "OR";
export type SortDir = "asc" | "desc";

export interface ScreenerFilter {
  column: ScreenerColumn;
  operator: FilterOperator;
  value: unknown;
  logical_op: LogicalOp;
}

export interface ScreenerRequest {
  filters: ScreenerFilter[];
  sort_column: ScreenerColumn;
  sort_dir: SortDir;
  cursor?: string;
  page_size: number;
  event_id?: string;
}

export interface ScreenerRow {
  company_id: string;
  ticker: string;
  name: string;
  sector: string;
  market_cap: number;
  custom_score: number;
  score_delta: number;
  current_price: number;
  active_events_count: number;
  active_event_categories: string[];
}

export interface ScreenerResponse {
  data: ScreenerRow[];
  next_cursor: string | null;
  total_count: number;
  applied_filters: ScreenerFilter[];
}

/** API envelope wrapper returned by the backend. */
export interface ApiEnvelope<T> {
  data: T;
  meta: Record<string, unknown>;
  error: string | null;
}
