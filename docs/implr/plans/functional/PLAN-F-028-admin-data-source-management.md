---
plan_id: PLAN-F-028
slug: admin-data-source-management
title: Admin Data Source Management
linked_requirement: REQ-F-028
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-007, reason: "Source config changes must work identically in self-hosted and cloud deployments; no cloud-specific path" }
dependencies:
  - { id: PLAN-F-033, reason: "Admin/operator role and JWT middleware required to gate the admin panel endpoints" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-028 — Admin Data Source Management

## Linked Requirement
**REQ-F-028** — Admin Data Source Management
Status: approved | Jira: —

## Objective

Implement the full admin data-source management plane: the `source_config` and
`market_source_binding` DB tables (D1), a FastAPI router with CRUD and enable/disable
endpoints secured to `role=admin`, a `MarketRegistry` service that holds the runtime
routing view and refreshes from the DB within 60 seconds of any change, a set of
per-source health statistics derived from a Redis counter layer, and a React admin screen
at `/admin/sources` that exposes all capabilities—source list, add-provider form,
market-to-source binding panel, and a dedicated social-sources section with Twitter/X
toggled off by default (D8).  No code deployment or service restart is required for any
configuration change once this plan is implemented.

## Architecture Context

**D1** establishes `source_config` and `market_source_binding` as the DB-backed
authoritative config for the data provider layer (ARCHITECTURE §10 — Admin Config Plane).
The `MARKET_REGISTRY` is not a code dictionary but a runtime view of these two tables,
loaded at startup and refreshable without restart.

**D3** mandates that `credentials_ref` stores a vault-reference string (e.g.
`env:FINNHUB_API_KEY`) resolved at runtime; the secret value never touches the DB or logs.

**D8** specifies Twitter/X is off by default; the admin must explicitly toggle it on.

Layers touched:

- **Layer 3 (Storage):** new Alembic migration, SQLAlchemy models, repositories.
- **Layer 2 (Ingestion):** `MarketRegistry` service consumed by adapter dispatch; health
  counter writer (Redis incr/decr on each provider call).
- **Layer 5 (API):** new FastAPI router under `/api/v1/admin/sources`; requires `role=admin`
  JWT check from PLAN-F-033.
- **Layer 6 (Frontend):** new React page at `/admin/sources` inside the existing `/admin`
  route group, role-gated.

Module ownership per ARCHITECTURE §5:
- `src/admin/` — new sub-package; admin router, schemas, service.
- `src/markets/` — `MarketRegistry` service (runtime routing view).
- `src/storage/` — SQLAlchemy models + repositories for the two new tables.
- `src/data_providers/` — credential resolver (`credentials_ref` → actual key).
- `frontend/src/pages/admin/sources/` — React components.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-007 | All source config changes must work identically in self-hosted and cloud deployments; no cloud-specific code path | `credentials_ref` resolver uses env-var lookup only (no Azure Key Vault SDK call); Docker-compose and cloud deployments share the same resolver; no deployment-specific branching anywhere in this plan |

## Component Design

### New Components

```
src/admin/
  __init__.py
  router.py                  — FastAPI APIRouter: /api/v1/admin/sources
  schemas.py                 — Pydantic request/response models (SourceConfigOut,
                               SourceConfigCreate, BindingOut, BindingUpsert,
                               HealthStatsOut, SourceListOut)
  service.py                 — AdminSourceService: orchestrates repo + registry refresh
  dependencies.py            — require_admin() FastAPI dependency (delegates to PLAN-F-033 JWT)

src/markets/
  registry.py                — MarketRegistry: runtime routing cache; refresh(); get_source()
  registry_refresher.py      — Background task (asyncio periodic or Celery beat) that polls
                               updated_at > last_loaded and calls registry.refresh()

src/storage/models/
  source_config.py           — SQLAlchemy ORM model for source_config
  market_source_binding.py   — SQLAlchemy ORM model for market_source_binding

src/storage/repositories/
  source_config_repo.py      — ISourceConfigRepository + PostgresSourceConfigRepository
  market_source_binding_repo.py — IBindingRepository + PostgresBindingRepository

src/data_providers/
  credentials_resolver.py    — resolve_credentials(ref: str) -> str; supports "env:<VAR>"
                               prefix; raises ConfigurationError on missing var

src/admin/health/
  counter.py                 — HealthCounter: incr_calls, incr_errors, get_stats per source_id
                               backed by Redis HINCRBY with 24-h rolling key

alembic/versions/
  XXXX_add_source_config_and_market_source_binding.py

frontend/src/pages/admin/sources/
  SourcesPage.tsx            — top-level page; tabs: All Sources | Social Sources | Bindings
  SourceList.tsx             — table: display_name, type, enabled toggle, health badge,
                               last_fetch, cost_tier, calls_today, rate_limit_pct,
                               errors_today, est_cost
  AddSourceModal.tsx         — form: display_name, interface_type, credentials_ref,
                               config (JSONB textarea), cost_tier, priority
  SourceHealthCard.tsx       — per-source health detail: calls, rate_limit_pct,
                               error_count, estimated_cost, alert threshold indicator
  SocialSourcesPanel.tsx     — filtered view of social providers;
                               Twitter/X shown with enabled=false badge + tooltip
  BindingsPanel.tsx          — market × interface matrix; primary/fallback dropdowns
  hooks/useSources.ts        — TanStack Query hooks for all source endpoints
  hooks/useBindings.ts       — TanStack Query hook for binding endpoints
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/main.py` (or `app.py`) | Register `admin_router` with prefix `/api/v1/admin` | Wire new router |
| `src/storage/models/__init__.py` | Export new ORM models | Alembic autogenerate picks them up |
| `src/config/settings.py` | No change required — secrets already env-vars | Confirm resolver reads `os.environ` |
| `frontend/src/App.tsx` (or router root) | Add `/admin/sources` route under existing `/admin` guard | Add page to admin section |
| `frontend/src/pages/admin/AdminNav.tsx` | Add "Sources" nav item | Navigation link |

### Interfaces and Contracts

```python
# src/storage/repositories/source_config_repo.py
from abc import ABC, abstractmethod
from uuid import UUID
from src.storage.models.source_config import SourceConfig

class ISourceConfigRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[SourceConfig]: ...

    @abstractmethod
    async def get_by_id(self, source_id: UUID) -> SourceConfig | None: ...

    @abstractmethod
    async def create(self, data: SourceConfigCreate) -> SourceConfig: ...

    @abstractmethod
    async def set_enabled(self, source_id: UUID, enabled: bool) -> SourceConfig: ...

    @abstractmethod
    async def update(self, source_id: UUID, data: SourceConfigUpdate) -> SourceConfig: ...


# src/storage/repositories/market_source_binding_repo.py
from abc import ABC, abstractmethod
from uuid import UUID
from src.storage.models.market_source_binding import MarketSourceBinding

class IBindingRepository(ABC):
    @abstractmethod
    async def list_for_market(self, market_id: UUID) -> list[MarketSourceBinding]: ...

    @abstractmethod
    async def upsert(self, market_id: UUID, interface_type: str,
                     source_id: UUID, role: str) -> MarketSourceBinding: ...

    @abstractmethod
    async def delete(self, market_id: UUID, interface_type: str,
                     source_id: UUID) -> None: ...


# src/markets/registry.py
from typing import Protocol
from uuid import UUID

class IMarketRegistry(Protocol):
    def get_source(self, market_id: UUID, interface_type: str,
                   role: str = "primary") -> "SourceConfig | None": ...

    async def refresh(self) -> None: ...


# src/data_providers/credentials_resolver.py
def resolve_credentials(ref: str) -> str:
    """Resolves a credentials_ref string to the actual secret.
    Supports prefix: 'env:<ENV_VAR_NAME>'.
    Raises ConfigurationError if the variable is absent.
    Never logs or returns partial secrets."""
    ...


# src/admin/health/counter.py
class HealthCounter:
    async def incr_calls(self, source_id: str) -> None: ...
    async def incr_errors(self, source_id: str) -> None: ...
    async def set_rate_limit_pct(self, source_id: str, pct: float) -> None: ...
    async def get_stats(self, source_id: str) -> HealthStats: ...
    # Keys: "health:{source_id}:{YYYYMMDD}:{calls|errors|rate_limit_pct}"
    # TTL: 25 h (covers full 24-h rolling window with margin)
```

## Implementation Tasks

### TASK-001: DB Migration — source_config and market_source_binding tables · M/TDD · alembic/versions/XXXX_add_source_config_and_market_source_binding.py, src/storage/models/source_config.py, src/storage/models/market_source_binding.py

Create the Alembic migration and SQLAlchemy ORM models for `source_config` and
`market_source_binding` exactly as specified in ARCHITECTURE §10.

`source_config` columns: `source_id UUID PK`, `interface_type TEXT NOT NULL`,
`display_name TEXT NOT NULL`, `enabled BOOL NOT NULL DEFAULT false`,
`credentials_ref TEXT NOT NULL`, `config JSONB NOT NULL DEFAULT '{}'`,
`cost_tier TEXT NOT NULL`, `priority INT NOT NULL DEFAULT 0`,
`updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()`.

`market_source_binding` columns: `market_id UUID NOT NULL FK→market`,
`interface_type TEXT NOT NULL`, `source_id UUID NOT NULL FK→source_config`,
`role TEXT NOT NULL CHECK(role IN ('primary','fallback'))`.  Composite PK:
`(market_id, interface_type, source_id)`.

Seed the social stub sources (StockTwits, Reddit, Telegram, Truth Social, Twitter/X) with
`enabled=false` in the migration's seed data block so Twitter/X is off by default (D8).
The five `interface_type` values for social stubs: `SocialProvider`.

**Tests to write first (TDD):**
- Migration applies and rolls back cleanly against a test PostgreSQL instance.
- `source_config.enabled` defaults to `false` on insert.
- Twitter/X seed row has `enabled=false`.
- Composite PK constraint rejects duplicate `(market_id, interface_type, source_id)` tuples.
- `role` check constraint rejects values outside `{primary, fallback}`.

**AC covered:** AC-002 (source appears disabled by default), AC-003 (Twitter/X seeded as disabled)

---

### TASK-002: Repositories — ISourceConfigRepository and IBindingRepository · M/TDD · src/storage/repositories/source_config_repo.py, src/storage/repositories/market_source_binding_repo.py

Implement `PostgresSourceConfigRepository` and `PostgresBindingRepository` behind the
interfaces defined in the Component Design section.  Use SQLAlchemy 2.0 async sessions.
All queries use parameterised statements only.  `set_enabled` must update `updated_at`
to `now()` atomically in the same UPDATE statement so the `MarketRegistry` refresher can
poll on `updated_at`.

**Tests to write first (TDD):**
- `list_all()` returns all rows including disabled ones.
- `create()` persists a row and returns it with a generated `source_id`.
- `set_enabled(id, True)` flips `enabled` and updates `updated_at`; subsequent
  `get_by_id` reflects the change.
- `set_enabled(id, False)` for a source that is already disabled is idempotent (no error).
- `upsert()` on binding creates row on first call and updates `role` on second call with
  same PK triple.
- `delete()` removes the binding; subsequent `list_for_market` does not include it.

**AC covered:** AC-001 (enable flag persisted for routing), AC-002 (create new source), AC-004 (binding change persisted)

---

### TASK-003: MarketRegistry service and background refresher · M/TDD · src/markets/registry.py, src/markets/registry_refresher.py

Implement `MarketRegistry` as an in-process singleton (or dependency-injected singleton
via FastAPI `lifespan`).  It holds a dict keyed by `(market_id, interface_type, role)` →
`SourceConfig`.  On `refresh()` it queries `source_config` JOIN `market_source_binding`
where `source_config.enabled=true`.

`RegistryRefresher` runs as an `asyncio` periodic task (interval: 30 seconds) that checks
whether any `source_config.updated_at` or `market_source_binding` row is newer than
`last_loaded_at`.  If yes, calls `registry.refresh()`.  This guarantees AC-004 (change
visible within 60 seconds: worst case is two 30-s intervals).

`registry.get_source(market_id, interface_type, role="primary")` returns `None` (not
raises) when no binding exists or the source is disabled.  Callers fall back to `role=
"fallback"` and finally to `None` (graceful degradation).

**Tests to write first (TDD):**
- After `refresh()`, `get_source()` returns the primary source for a known binding.
- A disabled source is absent from the registry after `refresh()`.
- Calling `set_enabled(source_id, False)` on a source and then `refresh()` removes it
  from the registry; subsequent `get_source()` returns the fallback.
- `RegistryRefresher` calls `refresh()` when `updated_at` advances.
- `RegistryRefresher` does NOT call `refresh()` when nothing has changed (idempotency).

**AC covered:** AC-001 (disable routes to fallback immediately after refresh), AC-004 (binding change visible within 60 s)

---

### TASK-004: Credentials resolver · S/no-TDD · src/data_providers/credentials_resolver.py

Implement `resolve_credentials(ref: str) -> str`.  Supported scheme: `env:<VAR_NAME>`.
Raises `ConfigurationError(f"Missing env var: {var_name}")` if the variable is absent.
Never logs the resolved value.  Must be pure (no I/O side effects) so it is testable
without network or DB.  Portability requirement (REQ-N-007): no Azure SDK import; only
`os.environ`.

**AC covered:** AC-002 (credentials_ref resolved at runtime without restart)

---

### TASK-005: Health counter service · M/TDD · src/admin/health/counter.py

Implement `HealthCounter` backed by Redis.  Keys follow pattern
`health:{source_id}:{YYYYMMDD}:{metric}` with a 25-hour TTL set on each key after the
first write.  Supported metrics: `calls`, `errors`, `rate_limit_pct` (stored as an integer
× 100 to avoid float keys).  `get_stats(source_id)` returns a `HealthStats` Pydantic
model with: `calls_today`, `errors_today`, `rate_limit_pct_used`, `estimated_cost_today`
(computed as `calls_today × cost_per_call` from `source_config.cost_tier` lookup).

**Tests to write first (TDD):**
- `incr_calls` increments the correct Redis key and returns the new count.
- `incr_errors` is independent of `incr_calls` on the same source.
- `get_stats` returns zeros for a source with no keys (cold state).
- `get_stats` returns correct aggregates after a sequence of incr calls.
- Keys expire after TTL (test with short TTL override in test mode).

**AC covered:** enables AC-001 (health dashboard visible on source list for monitoring fallback routing)

---

### TASK-006: FastAPI admin router and service · L/TDD · src/admin/router.py, src/admin/schemas.py, src/admin/service.py, src/admin/dependencies.py

Implement the `AdminSourceService` and the FastAPI `APIRouter` at
`/api/v1/admin/sources`.  All endpoints require `role=admin` (via `require_admin()`
dependency from PLAN-F-033).

Endpoint surface:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/sources` | List all sources with health stats |
| POST | `/api/v1/admin/sources` | Create new source (enabled=false) |
| GET | `/api/v1/admin/sources/{source_id}` | Get single source + health |
| PATCH | `/api/v1/admin/sources/{source_id}/enable` | Toggle enabled; triggers registry refresh |
| GET | `/api/v1/admin/sources/{source_id}/health` | Per-source health dashboard |
| GET | `/api/v1/admin/bindings` | List all market-source bindings |
| PUT | `/api/v1/admin/bindings` | Upsert a binding; triggers registry refresh |
| DELETE | `/api/v1/admin/bindings` | Remove a binding |

`PATCH .../enable` body: `{ "enabled": true|false }`.  After persisting, calls
`registry.refresh()` synchronously so the change takes effect before the response returns.
This satisfies AC-001 (immediate routing change) and AC-002 (enabling a new source
immediately starts data fetching).

Response envelope: `{ "data": ..., "error": null }` per DEV-STANDARDS §7.

Non-admin request → HTTP 403 (AC-005).

Credentials are never included in any response body (`credentials_ref` field is
write-only: accepted on create, excluded from all GET responses).

**Tests to write first (TDD):**
- `GET /sources` with `role=end_user` token returns 403.
- `GET /sources` with `role=admin` token returns 200 with source list.
- `POST /sources` creates a new source; response has `enabled=false`.
- `PATCH /{id}/enable` with `{ "enabled": false }` disables source; subsequent
  `GET /sources` shows `enabled=false`; registry no longer returns that source.
- `PATCH /{id}/enable` with `{ "enabled": true }` on a newly-created source; registry
  returns that source on `get_source()`.
- `PUT /bindings` upsert creates binding; `GET /bindings` lists it.
- Response body never contains a resolved secret value.
- Twitter/X source initially returns `enabled=false` from `GET /sources`.

**AC covered:** AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-007: React admin sources page — source list and enable/disable · M/TDD · frontend/src/pages/admin/sources/SourcesPage.tsx, frontend/src/pages/admin/sources/SourceList.tsx, frontend/src/pages/admin/sources/hooks/useSources.ts

Build the `SourcesPage` container (tabs: All Sources | Social Sources | Bindings) and the
`SourceList` table component.  Columns: display_name, interface_type, enabled toggle
switch, health indicator badge (green <70% rate_limit, amber 70–80%, red >80%),
last_fetch timestamp, cost_tier, calls_today, rate_limit_pct, errors_today, est_cost.

`useSources` hook wraps `GET /api/v1/admin/sources`; `useToggleSource` mutation calls
`PATCH /{id}/enable` and invalidates the list query on success.  Optimistic UI: the toggle
flips immediately with a loading spinner; reverts on API error with an error toast.

TanStack Query for server state; no global Redux.

**Tests to write first (TDD):**
- `useSources` hook returns source list on successful fetch (msw mock).
- Toggle switch calls PATCH with correct payload.
- On PATCH error, toggle reverts to previous state.
- Twitter/X row shows `enabled=false` toggle (initial state from seed).
- Non-admin user is redirected to `/` (route guard test).

**AC covered:** AC-001 (UI shows routing change), AC-003 (Twitter/X shown disabled), AC-005 (route guard)

---

### TASK-008: React add-provider modal · M/TDD · frontend/src/pages/admin/sources/AddSourceModal.tsx

Form fields: `display_name` (text, required), `interface_type` (select from fixed enum:
PriceProvider | FundamentalsProvider | NewsProvider | FilingsProvider | MacroProvider |
SocialProvider), `credentials_ref` (text, required, placeholder `env:MY_API_KEY`),
`config` (JSON textarea with syntax validation), `cost_tier` (select: free | low | medium |
high), `priority` (number, default 0).

On submit: POST `/api/v1/admin/sources`; close modal; invalidate source list.

Validation: `credentials_ref` must match `^(env|vault):[A-Z0-9_]+$`; `config` must be
valid JSON; `display_name` max 120 characters.

**Tests to write first (TDD):**
- Form with valid data submits and calls POST.
- `credentials_ref` with a plaintext value (no prefix) shows a validation error and does
  not submit.
- Invalid JSON in config field shows a validation error.
- On success, modal closes and source list refetches.

**AC covered:** AC-002 (add provider form with credentials_ref)

---

### TASK-009: React social sources panel · S/no-TDD · frontend/src/pages/admin/sources/SocialSourcesPanel.tsx

Filtered subset of `SourceList` showing only `interface_type=SocialProvider` rows.
Twitter/X row has an additional info tooltip: "Off by default (D8) — explicit admin action
required to enable."  All other behaviour (toggle, health badge) is inherited from
`SourceList`.  No new API calls — uses the same `useSources` data.

**AC covered:** AC-003 (Twitter/X appears off by default with explicit labelling)

---

### TASK-010: React market-to-source bindings panel · M/TDD · frontend/src/pages/admin/sources/BindingsPanel.tsx, frontend/src/pages/admin/sources/hooks/useBindings.ts

Renders a matrix table: rows = markets, columns = interface types.  Each cell shows a
primary and fallback dropdown populated from enabled sources of that interface_type.
Selecting a new source calls `PUT /api/v1/admin/bindings`; clearing a selection calls
`DELETE`.

`useBindings` hook wraps `GET /api/v1/admin/bindings`.

Show a status indicator "Change will take effect within 60 s" after a successful upsert.

**Tests to write first (TDD):**
- Changing primary dropdown calls PUT with correct `{ market_id, interface_type, source_id, role: "primary" }`.
- Clearing a selection calls DELETE.
- Success confirmation indicator appears after PUT resolves.
- Disabled sources do not appear in the dropdown options.

**AC covered:** AC-004 (market binding change takes effect within 60 s; UI confirms)

---

### TASK-011: Wire router into main app and register admin nav entry · XS/no-TDD · src/api/main.py, frontend/src/App.tsx, frontend/src/pages/admin/AdminNav.tsx

Register `admin_router` on the FastAPI app with prefix `/api/v1/admin` and tag `admin`.
Add `/admin/sources` route in the React router under the existing `/admin` role guard.
Add "Data Sources" link in `AdminNav`.

**AC covered:** AC-005 (endpoint exists and is reachable; guard applied at router level)

## Acceptance Criteria Coverage

- AC-001: Given an admin disables a data source, the system immediately routes all affected data requests to the configured fallback source → TASK-003, TASK-006, TASK-007
- AC-002: Given an admin adds a new source with a credentials_ref and config, the source appears in the list in disabled state; enabling it begins using it for data fetching without a restart → TASK-001, TASK-002, TASK-004, TASK-006, TASK-008
- AC-003: Given Twitter/X is listed in the social sources section, it appears with enabled=false by default; an admin must explicitly toggle it on → TASK-001, TASK-006, TASK-007, TASK-009
- AC-004: Given an admin changes the market_source_binding, the change takes effect within 60 seconds without a service restart → TASK-002, TASK-003, TASK-006, TASK-010
- AC-005: Given an end-user attempts to access the admin data source management endpoint, the response is HTTP 403 Forbidden → TASK-006, TASK-007, TASK-011

## Acceptance Notes

Twitter/X `enabled=false` is enforced via the seed data in the Alembic migration
(TASK-001), not via a code guard.  If the migration is re-run against an existing DB that
already has a Twitter/X row, the seed block must use `INSERT ... ON CONFLICT DO NOTHING`
to avoid overwriting an admin's explicit choice.

The `credentials_ref` field is accepted on write but excluded from all read responses.
The dev-executor must apply this exclusion at the Pydantic schema level (`exclude=True` on
the response model field), not via ad-hoc pop logic.

## Risks and Notes

- The `RegistryRefresher` runs inside the FastAPI process (asyncio task launched in
  `lifespan`).  If the API process restarts, the refresher restarts too — acceptable
  because `registry.refresh()` is called at startup.  Ensure the refresher task is
  cancelled cleanly in the `lifespan` shutdown path to avoid asyncio warnings.
- `estimated_cost_today` in `HealthStats` is an approximation (calls × flat rate per tier).
  Exact billing is external.  Do not present it as authoritative cost data in the UI —
  label it "Est. cost" with a footnote.
- The React `AddSourceModal` deliberately does not display or transmit credentials through
  the frontend after submission.  The `credentials_ref` field in API GET responses is
  omitted (see Acceptance Notes above).  Code review must verify this.
- The binding panel only surfaces `enabled=true` sources in dropdowns (TASK-010 contract).
  If the last enabled source for a binding is disabled, the binding remains in the DB but
  the registry stops serving it.  The UI should show a warning badge on the affected
  binding cell.
