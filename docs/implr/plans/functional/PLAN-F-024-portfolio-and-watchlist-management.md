---
plan_id: PLAN-F-024
slug: portfolio-and-watchlist-management
title: Portfolio and Watchlist Management
linked_requirement: REQ-F-024
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "tenant_id must appear in every portfolio, position, and watchlist query" }
dependencies:
  - { id: PLAN-F-033, reason: "User identity (user_id, tenant_id) is required before a portfolio can be created or queried" }
brainstorm_decisions:
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-024 — Portfolio and Watchlist Management

## Linked Requirement
**REQ-F-024** — Portfolio and Watchlist Management
Status: approved | Jira: (blank)

## Objective

Implement full portfolio and watchlist management for StokAI MVP. This plan delivers:
(1) Alembic migrations for `portfolio`, `position`, and `watchlist_item` tables, all
carrying `tenant_id` for multi-tenant isolation; (2) SQLAlchemy 2.0 async repository
classes for each entity; (3) service-layer classes encapsulating portfolio CRUD, CSV import
with per-row validation and error reporting, and watchlist add/remove; (4) FastAPI routers
exposing `POST/GET/DELETE /api/v1/portfolios`, `POST/GET/DELETE /api/v1/portfolios/{id}/positions`,
`POST /api/v1/portfolios/import`, and `POST/GET/DELETE /api/v1/watchlist`; (5) a
first-run onboarding guard that detects an empty portfolio on first login and prevents map
navigation until at least one holding is added or the user explicitly skips; (6) a React
portfolio summary card plus position list with cost basis and P&L display; (7) a watchlist
table with an empty-state guided prompt; and (8) a context propagation hook that keeps the
map overlay's portfolio context in sync after any portfolio or position mutation.

## Architecture Context

This plan spans three backend modules and the frontend presentation layer (Architecture §4–5, §11):

- **`storage`** (Architecture §5) — three new repository implementations: `PortfolioRepository`,
  `PositionRepository`, `WatchlistItemRepository`. All extend the repository pattern; all
  accept `tenant_id` as a mandatory filter on every query. No business logic.
- **`api`** (Architecture §5) — two new FastAPI sub-routers: `portfolio_router` (portfolios +
  positions + import) and `watchlist_router`. Entry layer only; no business logic.
- **New `portfolio` module** (Architecture §5 module map) — `PortfolioService`,
  `WatchlistService`, `CsvImportService`. Services consume repository interfaces injected
  through constructors (Dependency Inversion, Architecture Principle 1).
- **Alembic migrations** (Architecture §10) — migrations for `portfolio`, `position`, and
  `watchlist_item` tables matching the canonical data model in Architecture §10.
- **Frontend** (Architecture §11) — new React components under `src/frontend/`:
  `PortfolioCard`, `PositionList`, `WatchlistTable`, `OnboardingFlow`. Uses TanStack Query
  for server state; WebSocket subscription manager is notified after mutations to trigger
  map overlay refresh.

Architecture Principle 3 (§2, §12.3): every table carries `tenant_id` from day one. All
repository queries include `tenant_id` in the WHERE clause. No shortcut bypasses this.

Architecture §12.1 (D2): all endpoints are JWT-protected via the `get_current_user`
dependency from PLAN-F-033. Resource ownership is verified on every lookup.

Architecture §10 canonical schema is the authoritative source for column names and types.
The requirement's `Data Models` section extends the architecture schema with `user_id`,
`position_id`, `ticker`, `source`, and `item_id`; these additions are compatible and are
included in the migration.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-006 | `tenant_id` on every portfolio, position, and watchlist query | All three repository classes accept `tenant_id` as a mandatory parameter; no query may omit it. Index on `(tenant_id, portfolio_id)` and `(tenant_id, company_id)` added in TASK-001 migration. |

## Component Design

### New Components

```
Module: portfolio  (src/portfolio/)
  ├── PortfolioService       — portfolio + position CRUD business logic
  ├── WatchlistService       — watchlist add/remove/list business logic
  ├── CsvImportService       — CSV validation, row-level error collection, bulk insert
  └── Interfaces:
      ├── IPortfolioRepository
      ├── IPositionRepository
      └── IWatchlistItemRepository

Module: storage additions  (src/storage/)
  ├── PortfolioRepository    — SQLAlchemy 2.0 async; implements IPortfolioRepository
  ├── PositionRepository     — SQLAlchemy 2.0 async; implements IPositionRepository
  └── WatchlistItemRepository — SQLAlchemy 2.0 async; implements IWatchlistItemRepository

Module: api additions  (src/api/routers/)
  ├── portfolio_router.py    — /api/v1/portfolios (portfolios + positions + CSV import)
  └── watchlist_router.py   — /api/v1/watchlist

Frontend  (src/frontend/features/portfolio/)
  ├── PortfolioCard.tsx      — summary card: name, position count, total cost basis
  ├── PositionList.tsx       — tabular list of positions with avg cost + P&L placeholder
  ├── WatchlistTable.tsx     — watchlist with empty-state guided prompt
  └── OnboardingFlow.tsx     — multi-step first-run wizard (profile select → add holdings → preview)

Frontend  (src/frontend/hooks/)
  └── usePortfolioContext.ts — invalidates map overlay query on portfolio/position mutation
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/main.py` | Register `portfolio_router` and `watchlist_router` | Wire new routers into the FastAPI app |
| `src/frontend/app/routes.tsx` | Add onboarding guard: redirect to `/onboarding` if `portfolio_empty && !onboarding_skipped` | Enforce AC-001 first-run gate |
| `src/frontend/features/map/MapOverlay.tsx` | Subscribe to `usePortfolioContext` invalidation signal | AC-002, AC-005: map updates after any portfolio change |

### Interfaces and Contracts

```python
# src/portfolio/interfaces.py

class IPortfolioRepository(Protocol):
    async def create(self, tenant_id: UUID, user_id: UUID, name: str) -> Portfolio: ...
    async def list_by_user(self, tenant_id: UUID, user_id: UUID) -> list[Portfolio]: ...
    async def get(self, tenant_id: UUID, portfolio_id: UUID) -> Portfolio | None: ...
    async def delete(self, tenant_id: UUID, portfolio_id: UUID) -> None: ...

class IPositionRepository(Protocol):
    async def create(self, tenant_id: UUID, portfolio_id: UUID, **kwargs) -> Position: ...
    async def list_by_portfolio(self, tenant_id: UUID, portfolio_id: UUID) -> list[Position]: ...
    async def get(self, tenant_id: UUID, position_id: UUID) -> Position | None: ...
    async def delete(self, tenant_id: UUID, position_id: UUID) -> None: ...
    async def bulk_create(self, tenant_id: UUID, portfolio_id: UUID, rows: list[PositionCreate]) -> list[Position]: ...

class IWatchlistItemRepository(Protocol):
    async def add(self, tenant_id: UUID, user_id: UUID, company_id: UUID, ticker: str) -> WatchlistItem: ...
    async def list_by_user(self, tenant_id: UUID, user_id: UUID) -> list[WatchlistItem]: ...
    async def remove(self, tenant_id: UUID, user_id: UUID, company_id: UUID) -> None: ...
    async def exists(self, tenant_id: UUID, user_id: UUID, company_id: UUID) -> bool: ...
```

```python
# src/portfolio/csv_import.py — CsvImportResult contract

class CsvRowError(BaseModel):
    row_number: int
    ticker: str
    error: str

class CsvImportResult(BaseModel):
    positions_created: int
    errors: list[CsvRowError]   # empty list when all rows valid
```

## Implementation Tasks

### TASK-001: DB migrations for portfolio, position, watchlist_item · M/TDD · alembic/versions/xxxx_portfolio_watchlist.py

Create two Alembic migration scripts (or one combined migration):

- `portfolio` table: `portfolio_id UUID PK`, `tenant_id UUID NOT NULL`, `user_id UUID NOT NULL FK→user`,
  `name VARCHAR(255) NOT NULL`, `created_at TIMESTAMPTZ DEFAULT now()`.
  Index: `(tenant_id, user_id)`.

- `position` table: `position_id UUID PK`, `portfolio_id UUID NOT NULL FK→portfolio`,
  `company_id UUID NOT NULL FK→company`, `ticker VARCHAR(20) NOT NULL`,
  `shares FLOAT NOT NULL`, `cost_basis FLOAT NULL`, `added_at TIMESTAMPTZ DEFAULT now()`,
  `source VARCHAR(20) NOT NULL CHECK IN ('manual','csv','broker')`.
  Unique constraint on `(portfolio_id, company_id)`.
  Index: `(portfolio_id)`.

- `watchlist_item` table: `item_id UUID PK`, `tenant_id UUID NOT NULL`,
  `user_id UUID NOT NULL FK→user`, `company_id UUID NOT NULL FK→company`,
  `ticker VARCHAR(20) NOT NULL`, `added_at TIMESTAMPTZ DEFAULT now()`.
  Unique constraint on `(tenant_id, user_id, company_id)`.
  Index: `(tenant_id, user_id)`.

Down migration must cleanly drop all three tables.

**Tests to write first (TDD)**:
- Migration applies and rolls back cleanly against a test database (using Alembic's `command.upgrade` / `command.downgrade`).
- All NOT NULL constraints are enforced (insert without `tenant_id` raises `IntegrityError`).
- Unique constraint on `(portfolio_id, company_id)` rejects duplicates.

**AC covered**: enables AC-002, AC-003, AC-004, AC-005 (tables must exist before service/API layers can function)

---

### TASK-002: Repository implementations — PortfolioRepository, PositionRepository, WatchlistItemRepository · M/TDD · src/storage/portfolio_repository.py, src/storage/position_repository.py, src/storage/watchlist_item_repository.py

Implement all three repositories using SQLAlchemy 2.0 async session factory. Each must:

- Accept `tenant_id` as a required parameter on every query method.
- Use parameterised queries only (no string interpolation).
- `PortfolioRepository.list_by_user`: `WHERE tenant_id = :tid AND user_id = :uid`.
- `PositionRepository.list_by_portfolio`: join to portfolio to verify `tenant_id` ownership
  before returning rows (IDOR prevention).
- `WatchlistItemRepository.list_by_user`: `WHERE tenant_id = :tid AND user_id = :uid`.
- `PositionRepository.bulk_create`: single `INSERT ... VALUES (...)` statement; returns
  list of created `Position` objects.

Define SQLAlchemy ORM models (`Portfolio`, `Position`, `WatchlistItem`) in `src/storage/models.py`.

**Tests to write first (TDD)**:
- `test_portfolio_repo_create`: creates portfolio; returned object has correct `tenant_id` and `user_id`.
- `test_portfolio_repo_list_isolation`: two tenants; each can only see their own portfolios.
- `test_position_repo_tenant_isolation`: position owned by tenant A is not returned when queried with tenant B's `tenant_id`.
- `test_position_repo_bulk_create`: bulk-inserts 3 rows; returns 3 Position objects.
- `test_watchlist_repo_remove`: add then remove; subsequent `list_by_user` returns empty list.
- `test_watchlist_repo_exists`: returns True after add, False after remove.

**AC covered**: enables AC-002, AC-003, AC-004, AC-005

---

### TASK-003: PortfolioService and WatchlistService · M/TDD · src/portfolio/portfolio_service.py, src/portfolio/watchlist_service.py

Implement `PortfolioService` (constructor-injected `IPortfolioRepository`, `IPositionRepository`)
and `WatchlistService` (constructor-injected `IWatchlistItemRepository`).

`PortfolioService` methods:
- `create_portfolio(tenant_id, user_id, name) → Portfolio`
- `list_portfolios(tenant_id, user_id) → list[Portfolio]`
- `get_portfolio(tenant_id, portfolio_id, user_id) → Portfolio` — raises `NotFoundError` if absent or owned by another user.
- `delete_portfolio(tenant_id, portfolio_id, user_id) → None` — cascades to positions.
- `add_position(tenant_id, portfolio_id, user_id, ticker, shares, cost_basis, source) → Position` — resolves `company_id` from ticker via `ICompanyLookup` (injected stub for MVP).
- `delete_position(tenant_id, position_id, portfolio_id, user_id) → None`.
- `has_any_holding(tenant_id, user_id) → bool` — used by onboarding guard.

`WatchlistService` methods:
- `add_to_watchlist(tenant_id, user_id, ticker) → WatchlistItem` — idempotent; returns existing item if already present.
- `remove_from_watchlist(tenant_id, user_id, company_id) → None`.
- `list_watchlist(tenant_id, user_id) → list[WatchlistItem]` — returns empty list (not error) when no items.

All methods validate ownership via `tenant_id` before mutating. Never raise raw SQLAlchemy exceptions to callers; wrap in domain errors (`NotFoundError`, `ConflictError`).

**Tests to write first (TDD)**:
- `test_add_position_resolves_company_id`: stub `ICompanyLookup` returns fixed UUID; position created with that UUID.
- `test_delete_portfolio_cascades_positions`: delete portfolio; subsequent list of positions returns empty.
- `test_get_portfolio_wrong_tenant_raises`: `get_portfolio` with wrong `tenant_id` raises `NotFoundError`.
- `test_has_any_holding_false_when_empty`: freshly created user has no holdings; returns False.
- `test_add_to_watchlist_idempotent`: calling `add_to_watchlist` twice returns item without duplicate.
- `test_list_watchlist_empty_returns_empty_list`: no error on empty watchlist; returns `[]`.

**AC covered**: AC-002 (manual add creates position), AC-004 (empty watchlist → empty list), AC-005 (delete position)

---

### TASK-004: CsvImportService · M/TDD · src/portfolio/csv_import_service.py

Implement `CsvImportService` (constructor-injected `IPositionRepository`, `ICompanyLookup`).

Required CSV columns: `ticker`, `shares`, `cost_basis` (cost_basis optional per row).
Processing rules:
- Skip header row.
- Per-row validation: `ticker` must be non-empty string; `shares` must be a positive float;
  `cost_basis` must be a positive float or empty/null.
- Ticker-to-company resolution via `ICompanyLookup`; unresolvable ticker → row error, do not block other rows.
- Valid rows are bulk-inserted via `IPositionRepository.bulk_create` in a single transaction.
- Invalid rows accumulate in `CsvImportResult.errors` with 1-based `row_number` and `error` string.
- Maximum 500 rows per import; file exceeding this limit is rejected entirely with a single top-level error.
- Source field on created positions: `"csv"`.

Return type: `CsvImportResult` (see Interfaces section).

**Tests to write first (TDD)**:
- `test_csv_import_all_valid`: 3-row CSV; returns `positions_created=3`, `errors=[]`.
- `test_csv_import_partial_errors`: 3 rows, row 2 has invalid shares `"abc"`; returns `positions_created=2`, `errors=[{row_number:2, ...}]`.
- `test_csv_import_unresolvable_ticker`: ticker not in company lookup; row becomes error, others succeed.
- `test_csv_import_exceeds_limit`: 501-row CSV; raises `ValidationError` before any insert.
- `test_csv_import_missing_required_column`: CSV without `ticker` column; raises `ValidationError`.
- `test_csv_import_cost_basis_optional`: row with empty `cost_basis`; creates position with `cost_basis=None`.

**AC covered**: AC-003 (CSV import with per-row error report)

---

### TASK-005: Portfolio and Watchlist API routers · M/TDD · src/api/routers/portfolio_router.py, src/api/routers/watchlist_router.py, src/api/main.py

Implement two FastAPI routers protected by `get_current_user` (from PLAN-F-033).

**`portfolio_router` endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/portfolios` | Create portfolio; body: `{name}` |
| `GET` | `/api/v1/portfolios` | List portfolios for current user |
| `GET` | `/api/v1/portfolios/{portfolio_id}` | Get single portfolio |
| `DELETE` | `/api/v1/portfolios/{portfolio_id}` | Delete portfolio + cascade positions |
| `POST` | `/api/v1/portfolios/{portfolio_id}/positions` | Add position; body: `{ticker, shares, cost_basis?, source?}` |
| `GET` | `/api/v1/portfolios/{portfolio_id}/positions` | List positions |
| `DELETE` | `/api/v1/portfolios/{portfolio_id}/positions/{position_id}` | Delete position |
| `POST` | `/api/v1/portfolios/import` | CSV import; multipart form-data `file` field |

**`watchlist_router` endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/watchlist` | Add ticker to watchlist; body: `{ticker}` |
| `GET` | `/api/v1/watchlist` | List watchlist items |
| `DELETE` | `/api/v1/watchlist/{company_id}` | Remove item |

Response envelope: `{ "data": ..., "meta": null, "error": null }` (success) /
`{ "data": null, "error": { "code": "...", "message": "..." } }` (error).

All endpoints extract `tenant_id` and `user_id` from the JWT claims provided by `get_current_user`.
Controllers never pass raw DB entities to responses; map to Pydantic response DTOs.
Rate limiting applied to `POST` endpoints via SlowAPI (shared with auth rate limiter).

Register both routers in `src/api/main.py`.

**Tests to write first (TDD)**:
- `test_create_portfolio_returns_201`: authenticated request; response contains portfolio data.
- `test_list_portfolios_empty`: no portfolios; returns `{ "data": [] }`.
- `test_add_position_returns_201`: valid body; position appears in subsequent GET.
- `test_delete_position_removes_from_list`: DELETE then GET positions; deleted item absent.
- `test_csv_import_partial_errors_returns_200_with_error_report`: partial import; HTTP 200 with `errors` array in `data`.
- `test_portfolio_router_requires_auth`: unauthenticated request returns 401.
- `test_watchlist_add_returns_201`: authenticated POST to `/api/v1/watchlist`.
- `test_watchlist_get_empty_returns_empty_array`: GET watchlist before adding anything.
- `test_watchlist_delete_removes_item`: DELETE then GET; item absent.

**AC covered**: AC-002 (POST position), AC-003 (POST import), AC-004 (GET watchlist empty), AC-005 (DELETE position)

---

### TASK-006: First-run onboarding API endpoint and guard · M/TDD · src/api/routers/onboarding_router.py, src/portfolio/onboarding_service.py

Implement `OnboardingService` and a dedicated `onboarding_router`.

`OnboardingService`:
- `get_onboarding_state(tenant_id, user_id) → OnboardingState` — returns `{is_complete: bool, skipped: bool, has_holding: bool, scoring_profile_id: UUID | None}`.
- `select_scoring_profile(tenant_id, user_id, profile_id: UUID) → None` — writes `scoring_profile_default` to `user.settings` JSONB via `IUserSettingsRepository` (thin wrapper over user table, borrowed from PLAN-F-033 user entity).
- `mark_skipped(tenant_id, user_id) → None` — sets `onboarding_skipped = true` in `user.settings`.
- `is_onboarding_required(tenant_id, user_id) → bool` — returns True when `has_holding=False AND skipped=False`.

`onboarding_router` endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/onboarding/state` | Return current onboarding state |
| `POST` | `/api/v1/onboarding/profile` | Select preset scoring profile; body: `{profile_id}` |
| `POST` | `/api/v1/onboarding/skip` | Mark onboarding as skipped |

Preset scoring profile IDs (three fixed UUIDs seeded in a migration or config): `value_investor`, `growth_hunter`, `macro_aware`. These are references to `indicator` rows that will be seeded by PLAN-F-017 (Scoring Engine); for MVP, accept any non-null UUID and store it.

**Tests to write first (TDD)**:
- `test_onboarding_required_when_empty_portfolio_not_skipped`: fresh user; `is_onboarding_required` returns True.
- `test_onboarding_not_required_after_skip`: after `mark_skipped`; returns False.
- `test_onboarding_not_required_after_holding`: after one position added; returns False.
- `test_select_scoring_profile_persists`: profile ID stored in `user.settings.scoring_profile_default`.
- `test_onboarding_state_endpoint_returns_200`: authenticated GET; returns valid `OnboardingState`.

**AC covered**: AC-001 (onboarding state drives first-run gate)

---

### TASK-007: React portfolio summary card and position list · M/TDD · src/frontend/features/portfolio/PortfolioCard.tsx, src/frontend/features/portfolio/PositionList.tsx, src/frontend/hooks/usePortfolioContext.ts

Implement the `PortfolioCard` and `PositionList` React components using TanStack Query.

`PortfolioCard`:
- Displays: portfolio name, count of positions, sum of `(shares * cost_basis)` as total cost basis.
- `Edit name` and `Delete portfolio` actions.
- Uses `useQuery` from TanStack Query against `GET /api/v1/portfolios/{id}`.

`PositionList`:
- Tabular display: ticker, shares, avg cost, current value placeholder (`—` until market data available), P&L placeholder.
- `Delete` action per row: calls `DELETE /api/v1/portfolios/{id}/positions/{pid}`, then invalidates the portfolio query.
- Empty state: "No positions yet. Add your first holding."

`usePortfolioContext`:
- Custom hook that exports `invalidatePortfolioContext()`.
- Calls `queryClient.invalidateQueries(['portfolio'])` and emits a custom event `portfolio:changed` for the map overlay to consume.
- Called by `PositionList` after any add/delete mutation and by `CsvImportPanel` after import.

**Tests to write first (TDD)**:
- `test_portfolio_card_renders_name_and_position_count`: mock API returns portfolio with 3 positions; card shows "3 positions".
- `test_position_list_renders_rows`: mock response with 2 positions; 2 rows rendered.
- `test_delete_position_calls_api_and_invalidates`: user clicks delete; DELETE API called; `invalidateQueries` triggered.
- `test_position_list_empty_state`: no positions; empty-state message shown.

**AC covered**: AC-002 (position visible after creation), AC-005 (map overlay updated via `portfolio:changed` event after delete)

---

### TASK-008: React watchlist table with empty-state prompt · S/no-TDD · src/frontend/features/portfolio/WatchlistTable.tsx

Implement the `WatchlistTable` React component.

- Uses `useQuery` against `GET /api/v1/watchlist`.
- When watchlist is empty (`data.length === 0`): render guided prompt "Add companies to see geopolitical events affecting your holdings" with a prominent "Add Company" CTA button (opens a ticker search modal, out of scope for this task — button is a placeholder that opens a TODO modal).
- When watchlist has items: render table with columns: Ticker, Company Name, Added Date, Remove action.
- `Remove` button calls `DELETE /api/v1/watchlist/{company_id}` and invalidates the watchlist query.

**AC covered**: AC-004 (empty watchlist shows guided prompt)

---

### TASK-009: React first-run onboarding flow · M/TDD · src/frontend/features/onboarding/OnboardingFlow.tsx, src/frontend/app/routes.tsx

Implement the `OnboardingFlow` multi-step wizard and the route-level onboarding guard.

`OnboardingFlow` (3 steps):
- **Step 1 — Choose scoring profile**: three preset cards (Value Investor, Growth Hunter, Macro Aware). Selecting one calls `POST /api/v1/onboarding/profile`. "Next" disabled until profile selected.
- **Step 2 — Add first holdings**: renders `PositionList` in edit mode plus a file upload for CSV import (`POST /api/v1/portfolios/import`). "Next" enabled only after `has_holding = true` (re-checked via `GET /api/v1/onboarding/state`). "Skip for now" button calls `POST /api/v1/onboarding/skip` and navigates to map.
- **Step 3 — Preview**: static informational screen showing a map thumbnail placeholder ("Your map will show portfolio context here"). "Go to Map" button navigates to `/`.

Route-level guard in `src/frontend/app/routes.tsx`:
- On authenticated route load, call `GET /api/v1/onboarding/state`.
- If `is_onboarding_required === true`, redirect to `/onboarding` before rendering any map route.
- If `is_onboarding_required === false`, proceed normally.

**Tests to write first (TDD)**:
- `test_onboarding_step1_next_disabled_until_profile_selected`: "Next" button is disabled before any card is clicked.
- `test_onboarding_step1_selects_profile_and_advances`: click a card; POST called; step advances to 2.
- `test_onboarding_step2_skip_navigates_to_map`: click "Skip for now"; skip API called; redirect to `/`.
- `test_onboarding_step2_next_disabled_until_holding`: `has_holding=false`; "Next" button is disabled.
- `test_route_guard_redirects_to_onboarding`: `is_onboarding_required=true`; attempting `/` navigates to `/onboarding`.
- `test_route_guard_allows_map_when_complete`: `is_onboarding_required=false`; `/` renders map normally.

**AC covered**: AC-001 (onboarding gate, profile selection, skip behaviour)

---

### TASK-010: CSV import UI panel · S/no-TDD · src/frontend/features/portfolio/CsvImportPanel.tsx

Implement `CsvImportPanel` — a React component used in both the onboarding flow (step 2) and the portfolio management screen.

- File input accepting `.csv` files only.
- On submit: `POST /api/v1/portfolios/import` (multipart).
- On success with `errors.length === 0`: show "All rows imported" toast.
- On success with `errors.length > 0`: show per-row error list below the file input; valid rows are confirmed as imported. User can download a CSV of failed rows.
- On HTTP error: show generic error message.
- "Import" button disabled while upload in progress.
- After successful (even partial) import, calls `invalidatePortfolioContext()`.

**AC covered**: AC-003 (error report displayed per row without blocking valid rows)

---

## Acceptance Criteria Coverage

- AC-001: Given a first-time user logs in with an empty portfolio, the onboarding flow is presented offering three preset scoring profiles; the user cannot navigate directly to the map until they add at least one holding or explicitly click "Skip" → TASK-006, TASK-009
- AC-002: Given a user manually enters a ticker, shares, and cost basis, a portfolio position is created and the company appears in the map's portfolio overlay context → TASK-003, TASK-005, TASK-007
- AC-003: Given a user uploads a CSV file with ticker, shares, and cost_basis columns, valid rows create positions; invalid rows produce a per-row error report without blocking valid rows → TASK-004, TASK-005, TASK-010
- AC-004: Given the watchlist is empty, the watchlist section displays a guided prompt to add companies, not a blank state → TASK-003, TASK-005, TASK-008
- AC-005: Given a user deletes a position, the position is removed and the map overlay updates to exclude that company from portfolio context → TASK-003, TASK-005, TASK-007

## Risks and Notes

- **Company lookup in MVP**: `ICompanyLookup` resolves a ticker string to a `company_id` UUID via a DB lookup against the `company` table. If the ticker is not in the tracked universe (~100–200 companies per Architecture §11), the service must return a descriptive error to the user ("Ticker XYZ is not in the tracked universe"). This is injected as a stub for unit tests and the real implementation reuses the `company` repository from `storage`.
- **Cascade delete**: deleting a portfolio must cascade to all its positions. Implement via `ON DELETE CASCADE` in the migration FK definition, not application-layer loops, to avoid partial deletes on failure.
- **CSV file size**: enforce the 500-row limit in `CsvImportService` before any DB work. Also enforce a maximum file size of 1 MB at the router layer (FastAPI `UploadFile` size check) to prevent memory exhaustion.
- **Onboarding skip persistence**: `onboarding_skipped` is stored in `user.settings JSONB` (Architecture §10 Auth schema). This reuses the `user` table without a schema migration. The `IUserSettingsRepository` is a thin wrapper that performs a JSONB merge update.
- **P&L display**: positions display avg cost and shares. Current market value and realized P&L require live price data (Finnhub, PLAN-F-032). In this plan, current value and P&L columns render as `—` (dash). This is correct MVP behaviour — do not block this plan on market data.
- **Map overlay propagation**: the `portfolio:changed` custom DOM event is the coupling point between the portfolio feature and the map overlay. The map overlay listens for this event and calls `queryClient.invalidateQueries(['map-portfolio-context'])`. This is intentionally loose coupling; a stronger contract (e.g. shared Zustand store) can replace it post-MVP.
- **tenant_id source**: all service methods receive `tenant_id` extracted from the JWT claims by `get_current_user`. Services must never accept `tenant_id` from the request body.
