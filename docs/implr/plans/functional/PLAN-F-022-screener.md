---
plan_id: PLAN-F-022
slug: screener
title: Company Screener
linked_requirement: REQ-F-022
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-014, reason: "Screener table must be responsive and usable on tablet and desktop" }
  - { id: REQ-N-015, reason: "Screener results cached client-side via TanStack Query; backend results served via cache-or-fetch layer" }
dependencies:
  - { id: PLAN-F-017, reason: "Company scores required for screener rows — company_score table and scoring_service must exist" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-022 — Company Screener

## Linked Requirement
**REQ-F-022** — Company Screener
Status: approved | Jira:

## Objective

Build a sortable, filterable company screener accessible from the top navigation bar and from the Intelligence Map's "show in screener" event popup button. The screener exposes all tracked companies (~100–200) in a paginated table showing name, ticker, sector, market cap, current custom score, score delta, 15-minute-delayed price, and active event count/categories. Filters support any displayed column with AND/OR logical composition. When entered from a map event context, the screener pre-filters to that event's affected companies sorted by custom score descending. A CSV export serialises the current filtered and sorted view. The backend delivers a FastAPI endpoint at `/api/v1/screener` using cursor-based pagination; the frontend uses TanStack Query for client-side caching and server-state management.

## Architecture Context

This plan spans Layer 5 (Serving) and Layer 6 (Presentation).

**Backend** lives in `src/api/` (the `api` module — ARCHITECTURE.md §5). The screener endpoint is a read-only aggregation query joining `company`, `company_score`, `price_bar`, and `event_exposure` / `geo_event` tables through the repository pattern (`storage` module). The `api` module orchestrates these through an injected `ScreenerService`; it does not write SQL directly (Principle 1). Cursor-based pagination is required for large datasets (DEV-STANDARDS.md §7). Server-side result sets are served through the cache-or-fetch layer (PLAN-F-032) with a short TTL appropriate for 15-minute-delayed price data.

**Frontend** lives in `src/frontend/` under a `screener/` feature folder. React 18 + TypeScript, TanStack Query for data fetching and client-side caching, plain React state for filter/sort UI (no Redux per ARCHITECTURE.md §11). The map's "show in screener" button passes an `event_id` query parameter to the screener route; the screener reads this parameter on mount and applies the preset event filter before the first data fetch.

**Data contracts**: `ScreenerRow` and `ScreenerFilter` from the requirement data model are implemented as Pydantic response schemas on the backend and TypeScript interfaces on the frontend. The filter composition engine accepts a list of `ScreenerFilter` objects and produces a WHERE clause via parameterised SQLAlchemy expressions (never raw string interpolation — DEV-STANDARDS.md §8).

The `company_score` table is an event-driven TimescaleDB snapshot (D4); the screener always reads the most recent score row per company per active indicator. Score delta is computed as `current_score − score_at_previous_session_boundary` using a session-anchor timestamp stored in `user.settings`.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-014 | Screener must be usable on tablet (768px+) and desktop | TASK-004 applies responsive CSS (table scroll on narrow viewports, min column widths); column visibility collapses on tablet per defined breakpoint |
| REQ-N-015 | Client-side results cached; server results served via cache-or-fetch | TASK-001 wraps DB query via cache-or-fetch with 60s TTL; TASK-004 configures TanStack Query `staleTime: 60_000` and `gcTime: 300_000`; cursor tokens are part of the cache key |

## Component Design

### New Components

```
Module: api  (src/api/v1/screener/)
  ├── router.py             — FastAPI router: GET /api/v1/screener
  ├── schemas.py            — Pydantic: ScreenerRow, ScreenerFilter, ScreenerRequest,
  │                           ScreenerResponse (cursor-paginated envelope)
  ├── screener_service.py   — Business logic: apply filters, build sort, delegate to repo
  └── screener_repository.py — SQLAlchemy query: join company + company_score +
                               price_bar + event_exposure; cursor pagination; parameterised filters

Module: frontend  (src/frontend/features/screener/)
  ├── ScreenerPage.tsx          — Route component; reads ?event_id query param on mount
  ├── ScreenerTable.tsx         — Virtualized/paginated table; TanStack Query fetch hook
  ├── ScreenerFilterBar.tsx     — Filter row builder: column selector, operator, value, AND/OR toggle
  ├── useScreener.ts            — TanStack Query hook wrapping GET /api/v1/screener
  ├── screenerTypes.ts          — TypeScript: ScreenerRow, ScreenerFilter, ScreenerRequest
  └── screenerUtils.ts          — CSV serialiser, filter-to-query-param encoder
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/v1/__init__.py` (or `router.py`) | Register screener router | Wire new endpoint into FastAPI app |
| `src/frontend/App.tsx` (or router config) | Add `/screener` route pointing to `ScreenerPage` | Enable navigation |
| `src/frontend/components/layout/TopNav.tsx` | Add "Screener" link in top navigation | AC-001 navigation entry point |
| `src/frontend/features/map/EventPopup.tsx` | Add "Show in Screener" button linking to `/screener?event_id=<id>` | AC-003 map context trigger |

### Interfaces and Contracts

```python
# src/api/v1/screener/schemas.py

class ScreenerFilter(BaseModel):
    column: str                     # must match a whitelisted column name
    operator: Literal["eq", "gt", "lt", "contains", "in"]
    value: Any
    logical_op: Literal["AND", "OR"] = "AND"  # combines with previous filter in list

class ScreenerRequest(BaseModel):
    filters: list[ScreenerFilter] = []
    sort_column: str = "custom_score"
    sort_dir: Literal["asc", "desc"] = "desc"
    cursor: str | None = None       # opaque base64-encoded cursor
    page_size: int = Field(default=50, ge=1, le=200)
    event_id: UUID | None = None    # preset filter: affected companies for this event

class ScreenerRow(BaseModel):
    company_id: UUID
    ticker: str
    name: str
    sector: str
    market_cap: float
    custom_score: float
    score_delta: float
    current_price: float            # 15-min delayed
    active_events_count: int
    active_event_categories: list[str]

class ScreenerResponse(BaseModel):
    data: list[ScreenerRow]
    next_cursor: str | None
    total_count: int                # total matching rows (for display, not for pagination)
    applied_filters: list[ScreenerFilter]
```

```python
# src/api/v1/screener/screener_service.py  — protocol

class IScreenerRepository(Protocol):
    async def fetch_rows(
        self,
        request: ScreenerRequest,
        tenant_id: UUID,
    ) -> tuple[list[ScreenerRow], str | None, int]: ...
    # returns (rows, next_cursor, total_count)
```

```typescript
// src/frontend/features/screener/screenerTypes.ts

export interface ScreenerFilter {
  column: string;
  operator: "eq" | "gt" | "lt" | "contains" | "in";
  value: unknown;
  logical_op: "AND" | "OR";
}

export interface ScreenerRequest {
  filters: ScreenerFilter[];
  sort_column: string;
  sort_dir: "asc" | "desc";
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
```

## Implementation Tasks

### TASK-001: Screener API endpoint with sort and cursor-based pagination · M/TDD · src/api/v1/screener/router.py, src/api/v1/screener/schemas.py, src/api/v1/screener/screener_service.py, src/api/v1/screener/screener_repository.py, tests/unit/screener/test_screener_service.py, tests/integration/screener/test_screener_endpoint.py

Implement the `GET /api/v1/screener` FastAPI endpoint and its supporting service and repository. The endpoint accepts `ScreenerRequest` as query parameters (filters serialised as repeated JSON-encoded items or a single JSON body via request body for complex queries — use POST with a JSON body to avoid URL-length issues). The repository executes a SQLAlchemy async query joining `company`, the most-recent `company_score` per `(company_id, indicator_id)` using a lateral or window-function subquery, the most-recent `price_bar` for each company, and an aggregated count of active `event_exposure` rows. Sort is applied via the `sort_column` / `sort_dir` parameters against a whitelist of allowed columns (never interpolated directly into SQL). Cursor-based pagination encodes the last row's sort key and `company_id` as a base64 opaque token; the repository decodes and applies a WHERE clause to continue from the cursor position.

The service layer validates filter columns against a `SCREENER_COLUMN_WHITELIST` constant, rejects unknown columns with a 422 response, and delegates to the repository. JWT tenant context is extracted from the `Authorization: Bearer` header by FastAPI dependency; `tenant_id` is injected into every repository call (ARCHITECTURE.md §12.3).

Register the router in the FastAPI application router. The endpoint is protected (authentication required by default — DEV-STANDARDS.md §8).

**Tests to write first (TDD):**
- Unit: `ScreenerService.build_filter_clause` rejects unknown column names with `ValueError`
- Unit: `ScreenerService.build_filter_clause` produces correct AND/OR combinations for two filters
- Unit: cursor encode/decode is a round-trip identity for any `(sort_value, company_id)` tuple
- Integration: `GET /api/v1/screener` with no filters returns 200 and a paginated `ScreenerResponse`
- Integration: sort by `custom_score desc` places highest-scored company in first position
- Integration: cursor from first page response, when used as the next request cursor, returns the continuation without overlap

**AC covered**: AC-001, AC-005

---

### TASK-002: AND/OR filter composition engine · M/TDD · src/api/v1/screener/screener_service.py, src/api/v1/screener/screener_repository.py, tests/unit/screener/test_filter_composition.py

Extend `ScreenerService` and `ScreenerRepository` to translate a list of `ScreenerFilter` objects into a composed SQLAlchemy WHERE clause using `and_` / `or_` combinators. The composition rule: process the filter list left to right; the first filter is the base predicate; each subsequent filter's `logical_op` field determines whether it is ANDed or ORed with the accumulated predicate so far. This produces correct left-associative AND/OR expressions without nested ambiguity.

Each operator type maps to a SQLAlchemy expression: `eq` → `==`, `gt` → `>`, `lt` → `<`, `contains` → `ilike('%value%')` on text columns, `in` → `in_([...])`. Column mapping is validated against `SCREENER_COLUMN_WHITELIST` before expression construction. Parameterised bindings are used exclusively — no string formatting.

The `event_id` preset filter (from map context, AC-003) is implemented here as a special case: when `event_id` is present in the request, the repository adds an inner join against `event_exposure WHERE event_id = :event_id` before applying user-supplied filters.

**Tests to write first (TDD):**
- `filter_list = [{column: "sector", op: "eq", value: "Technology", logical_op: "AND"}]` → single predicate
- Two filters with `logical_op: "AND"` → `WHERE (sector = 'X' AND custom_score > 50)`
- Two filters with second `logical_op: "OR"` → `WHERE (sector = 'X' OR custom_score > 50)`
- Three filters AND/OR/AND → correct associativity
- `operator: "contains"` on `name` column → `ilike` used (case-insensitive)
- `operator: "in"` on `sector` → `in_` used with list value
- Unknown column in filter → `ValueError` raised before any SQL is constructed
- `event_id` set → join against `event_exposure` present in generated query

**AC covered**: AC-002, AC-003

---

### TASK-003: Pre-filter routing from map event context · S/no-TDD · src/frontend/features/map/EventPopup.tsx, src/frontend/features/screener/ScreenerPage.tsx, src/frontend/features/screener/useScreener.ts

Wire the "Show in Screener" button in the map event popup to the screener route with an `event_id` query parameter. In `EventPopup.tsx`, add a button that navigates to `/screener?event_id=<event.event_id>`. In `ScreenerPage.tsx`, read the `event_id` search parameter on mount using the React Router `useSearchParams` hook. When `event_id` is present: initialise the `ScreenerRequest` with `event_id` set and `sort_column: "custom_score"`, `sort_dir: "desc"` (matching AC-003); display a dismissible banner reading "Filtered to companies affected by [event title]" above the table. When the user dismisses the banner or clears all filters, `event_id` is removed from the request and the URL.

The `useScreener` hook accepts the full `ScreenerRequest` object and builds the API URL including `event_id` when present. The TanStack Query key includes all request fields so that different filter combinations are cached independently.

**AC covered**: AC-003

---

### TASK-004: Frontend Screener table component with filter bar, sort, and responsive layout · M/TDD · src/frontend/features/screener/ScreenerPage.tsx, src/frontend/features/screener/ScreenerTable.tsx, src/frontend/features/screener/ScreenerFilterBar.tsx, src/frontend/features/screener/useScreener.ts, src/frontend/features/screener/screenerTypes.ts, src/frontend/components/layout/TopNav.tsx, tests/frontend/screener/ScreenerTable.test.tsx, tests/frontend/screener/ScreenerFilterBar.test.tsx, tests/frontend/screener/useScreener.test.ts

Build the complete frontend screener experience.

`ScreenerTable.tsx`: renders a table with columns — Ticker, Name, Sector, Market Cap, Custom Score, Score Delta, Price, Active Events. Each column header is clickable to toggle sort ascending/descending (controlled by `sort_column` and `sort_dir` state in `ScreenerPage`). Visual sort indicator (arrow up/down) on the active sort column. The table uses "load more" cursor pagination: a "Load more" button at the bottom of the table triggers the next page fetch and appends results. On tablet viewports (768px–1024px), Market Cap and Active Events columns collapse to keep the table readable without horizontal scroll on the primary columns (REQ-N-014). Below 768px is out of scope (mobile not required for screener per REQ-N-014 which targets tablet/desktop).

`ScreenerFilterBar.tsx`: renders an "Add filter" button that appends a filter row. Each row has: a column dropdown (populated from `SCREENER_COLUMN_WHITELIST`), an operator dropdown (filtered by column type — numeric columns show gt/lt/eq; text columns show eq/contains), a value input, and an AND/OR selector (hidden for the first filter row). A remove button deletes the row. Filters are applied on user action (an "Apply" button) to avoid firing API calls on every keystroke.

`useScreener.ts`: wraps `useInfiniteQuery` from TanStack Query. `queryKey` includes the full serialised request (filters, sort, event_id). `staleTime: 60_000`, `gcTime: 300_000` (REQ-N-015). `getNextPageParam` extracts `next_cursor` from the last page response.

Add "Screener" to `TopNav.tsx` as a route link to `/screener`.

**Tests to write first (TDD):**
- `ScreenerTable` renders column headers with correct labels
- Clicking a column header calls `onSortChange` with correct column and direction; clicking again reverses direction
- `ScreenerFilterBar` renders an empty state with an "Add filter" button
- Clicking "Add filter" appends a filter row with column/operator/value inputs
- `ScreenerFilterBar` on second filter row shows AND/OR selector; first row does not
- Removing a filter row removes it from state
- `useScreener` calls `GET /api/v1/screener` with correct serialised params on initial render
- `useScreener` appends next page results when `fetchNextPage` is called with a valid cursor
- TanStack Query cache key differs when `event_id` is present vs absent

**AC covered**: AC-001, AC-002, AC-005

---

### TASK-005: CSV export · S/no-TDD · src/frontend/features/screener/screenerUtils.ts, src/frontend/features/screener/ScreenerPage.tsx, tests/frontend/screener/screenerUtils.test.ts

Implement client-side CSV export of the current filtered and sorted screener view. When the user clicks "Export CSV", all currently loaded rows (all pages fetched so far by `useInfiniteQuery`) are serialised to CSV. Column order matches the table display order. The CSV header row uses human-readable labels (e.g. "Custom Score" not "custom_score"). Numeric values use locale-aware formatting with sufficient decimal places (score: 2dp, price: 2dp, market cap: 0dp). The `active_event_categories` array is joined as a semicolon-separated string in its CSV cell.

The serialiser lives in `screenerUtils.ts` as a pure function `rowsToCsv(rows: ScreenerRow[]): string`. The download is triggered in `ScreenerPage.tsx` via a `<a download>` element created and clicked programmatically; no backend round-trip is needed. The exported filename includes the current date: `stokai-screener-YYYY-MM-DD.csv`.

Write unit tests for `rowsToCsv` in `screenerUtils.test.ts` covering: correct header row, correct data rows, numeric formatting, array-to-semicolon join, special characters in company names escaped per RFC 4180.

**AC covered**: AC-004

## Acceptance Criteria Coverage

- AC-001: Screener displays all tracked companies with name, ticker, sector, custom score, current price, and active events count → TASK-001, TASK-004
- AC-002: Two filters with AND/OR composition narrow the company list correctly → TASK-002, TASK-004
- AC-003: Entering from map "show in screener" button pre-filters to event's affected companies sorted by custom score descending → TASK-002, TASK-003, TASK-004
- AC-004: "Export CSV" downloads current filtered and sorted rows with all visible columns → TASK-005
- AC-005: Clicking a column header sorts the table; clicking again reverses sort order → TASK-001, TASK-004

## Risks and Notes

- The `company_score` table uses event-driven snapshots (D4); the screener query must select the most-recent score row per company using a window function or lateral join. Performance-test this query against 200 companies with dense score history before shipping TASK-001.
- The `ScreenerRequest` is sent as a POST body (not GET query params) to avoid URL-length limits when multiple filters are active. The endpoint path remains `/api/v1/screener` but uses `POST` method. Annotate this in OpenAPI docs as a read operation with a body to avoid confusion.
- `SCREENER_COLUMN_WHITELIST` must be the single source of truth shared between backend (Python) and frontend (TypeScript). Define it in `screener_service.py` and regenerate the TypeScript type via OpenAPI codegen or a shared constants file to avoid divergence.
- Filter `operator: "contains"` must use `ilike` (case-insensitive LIKE) to match user expectations; document this in the API schema.
- CSV export is purely client-side and operates on already-fetched rows. If the user has loaded only the first page, the export contains only that page. The "Export CSV" button tooltip must state "Exports currently loaded rows". A future enhancement could trigger a full server-side export with no page limit.
- Score delta (`score_delta`) requires a session-anchor timestamp. For MVP, define a fixed session boundary as midnight UTC of the current day (simple, no user session tracking required). Store this logic in `screener_repository.py` as a configurable constant that can later be replaced with `user.settings`-based session timestamps.
- REQ-N-014 (responsive design) is partially covered: tablet and desktop are in scope. The screener is not required to be functional on mobile viewports per the requirement's NFR scope. Document this explicitly in the component with a `// mobile not required — REQ-N-014 scope: tablet+` comment.
