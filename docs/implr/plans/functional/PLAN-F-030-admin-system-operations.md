---
plan_id: PLAN-F-030
slug: admin-system-operations
title: Admin System Operations Panel
linked_requirement: REQ-F-030
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-005, reason: "Cost monitor must enforce the $100/month AI + infra budget ceiling (D12)" }
  - { id: REQ-N-006, reason: "Admin endpoints are tenant-scoped; all repository queries must include tenant_id" }
  - { id: REQ-N-012, reason: "Feature-flag changes and budget hard-stop events must be logged to the episodic Layer 1 audit store" }
dependencies:
  - { id: PLAN-F-028, reason: "Admin router scaffolding (src/admin/), require_admin() dependency, and health-counter Redis patterns are established here; this plan extends the same package" }
  - { id: PLAN-F-013, reason: "HIL queue management is surfaced on the System Operations panel; hil_queue_item table and HILQueueRepository must exist" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-030 — Admin System Operations Panel

## Linked Requirement
**REQ-F-030** — Admin System Operations Panel
Status: approved | Jira: —

## Objective

Implement the Admin System Operations panel, the single runtime control surface for
platform operators. The panel aggregates five capability groups: (1) ingestion job list
with manual Celery dispatch; (2) cost monitor that aggregates AI and infrastructure spend
from `cost_record` rows against a configurable monthly budget, displays a warning at 80%
and a hard-stop at 100% that prevents further AI-cost-incurring workflow dispatch;
(3) tracked company universe management that sets the `company.is_tracked` flag without
deleting history; (4) Redis-backed cache inspection and force-refresh per company or data
type; and (5) a feature-flag store persisted in the `feature_flag` DB table with runtime
reads so that toggles take effect without a process restart. All endpoints are secured to
`role=admin` and extend the existing admin router from PLAN-F-028.

## Architecture Context

This plan touches five of the six system layers:

- **Layer 3 (Storage):** Three new tables — `ingestion_job`, `cost_record`, and
  `feature_flag` — backed by SQLAlchemy 2.0 models and repository classes under
  `src/storage/`. The `company` table already carries `is_tracked BOOL` (ARCHITECTURE
  §10 Core Domain Entities); this plan only updates the flag, not the schema.

- **Layer 2 (Ingestion):** `src/ingestion/job_registry.py` — a runtime dictionary of
  registered Celery task names keyed by `job_id`. The manual trigger endpoint dispatches
  by looking up the task name and calling `celery_app.send_task()`. The budget guard is
  enforced in `src/ai/budget_guard.py`, which checks `cost_record` aggregates before
  every AI-cost-incurring Celery task dispatch.

- **Layer 4 (Processing):** `BudgetGuard.assert_under_limit()` raises
  `BudgetHardStopError` when the monthly spend ≥ 100% of threshold, aborting the dispatch
  path. This guard is called at the Celery task entry point, not at the API layer
  (ARCHITECTURE §9 — budget hard-stop enforced at Celery task level).

- **Layer 5 (API):** New FastAPI router at `/api/v1/admin/system/` added to the existing
  admin router registered by PLAN-F-028. All endpoints require `require_admin()` from
  `src/admin/dependencies.py`.

- **Layer 6 (Frontend):** New React page at `/admin/system` with five tab sections:
  Ingestion Jobs, Cost Monitor, Company Universe, Cache, Feature Flags. Uses TanStack
  Query for server state and the existing admin role guard.

Architecture section references: §5 Backend Module Map (`ingestion`, `ai`, `storage`,
`api`), §10 Data Model (Core Domain Entities, Admin Config Plane), §11 Admin Panel
(System Operations section), §12.1 (JWT role guard), §12.6 Cost Governance (three budget
enforcement levels), §13 Technology Decisions (Celery beat for cron triggers).

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-005 | AI + infrastructure spend < $100/month | `BudgetGuard` reads `cost_record` aggregates; hard-stop blocks dispatch at 100%; threshold is configurable from the admin panel, defaulting to $100 |
| REQ-N-006 | All endpoints tenant-scoped | `cost_record`, `ingestion_job`, `feature_flag` queries include `tenant_id`; `company` flag update scoped to tenant |
| REQ-N-012 | Audit log required for operational events | `BudgetGuard` hard-stop events and feature-flag changes write `workflow_run`-level audit rows via `WorkflowRunRepository.append_audit_event()` |

## Component Design

### New Components

```
src/storage/models/
  ingestion_job.py        — SQLAlchemy ORM model for ingestion_job table
  cost_record.py          — SQLAlchemy ORM model for cost_record table
  feature_flag.py         — SQLAlchemy ORM model for feature_flag table

src/storage/repositories/
  ingestion_job_repo.py   — IIngestionJobRepository + PostgresIngestionJobRepository
  cost_record_repo.py     — ICostRecordRepository + PostgresCostRecordRepository
  feature_flag_repo.py    — IFeatureFlagRepository + PostgresFeatureFlagRepository
  company_repo.py         — Extended with set_tracked(company_id, is_tracked) method
                            (adds to existing company repository; may already exist
                            from PLAN-F-024 — check at execution time)

src/ingestion/
  job_registry.py         — JobRegistry: dict[str, str] of job_id → celery_task_name;
                            populated at startup via @register_job decorator; read by
                            manual trigger endpoint

src/ai/
  budget_guard.py         — BudgetGuard: assert_under_limit(tenant_id) reads
                            cost_record aggregate for current month; raises
                            BudgetHardStopError at >= 100% of threshold;
                            logs warning event at >= 80%

src/admin/system/
  __init__.py
  router.py               — FastAPI APIRouter at /api/v1/admin/system
  schemas.py              — Pydantic DTOs: IngestionJobOut, TriggerResponse,
                            CostSummaryOut, CostBreakdownOut, BudgetConfigIn,
                            CompanyUniverseItemOut, PromoteCompanyIn,
                            CacheStatsOut, ForceRefreshIn,
                            FeatureFlagOut, FeatureFlagToggleIn
  service.py              — SystemOpsService: orchestrates repos + guard + Celery dispatch

alembic/versions/
  XXXX_add_system_ops_tables.py
                          — Creates ingestion_job, cost_record, feature_flag tables;
                            seeds default feature flags

frontend/src/pages/admin/system/
  SystemOpsPage.tsx       — Top-level page; five tabs
  IngestionJobsTab.tsx    — Job list table + Manual Trigger button per row
  CostMonitorTab.tsx      — Aggregate gauge, breakdown table, 30-day chart,
                            budget threshold edit form
  CompanyUniverseTab.tsx  — Tracked company list; Promote / Demote actions;
                            inline company search for promote
  CacheInspectionTab.tsx  — Storage size table, force-refresh per type/company,
                            30-day storage growth chart
  FeatureFlagsTab.tsx     — Flag list with toggle switch; environment badge
  hooks/useSystemOps.ts   — TanStack Query hooks for all system-ops endpoints
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/main.py` | Register `system_ops_router` under `/api/v1/admin` | Expose new endpoints |
| `src/config/celery_app.py` | No beat schedule changes needed; manual trigger uses `send_task()` | Ingestion cron jobs are already registered; manual trigger piggy-backs |
| `src/ai/workflows/base_workflow.py` | Call `BudgetGuard.assert_under_limit()` at the start of every Mode B workflow Celery task | Hard-stop enforcement at dispatch layer (ARCHITECTURE §12.6) |
| `src/ingestion/tasks.py` | Call `BudgetGuard.assert_under_limit()` for tasks that incur AI cost; update `ingestion_job.status` to `running` / `failed` on task start / failure | Job status lifecycle |
| `frontend/src/App.tsx` | Add `/admin/system` route under the admin role guard | Mount new page |
| `frontend/src/pages/admin/AdminNav.tsx` | Add "System Operations" nav link | Navigation |

### Interfaces and Contracts

```python
# src/storage/repositories/ingestion_job_repo.py
from abc import ABC, abstractmethod
from uuid import UUID
from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus

class IIngestionJobRepository(ABC):
    @abstractmethod
    async def list_all(self, tenant_id: UUID) -> list[IngestionJob]: ...

    @abstractmethod
    async def get_by_id(self, job_id: UUID, tenant_id: UUID) -> IngestionJob | None: ...

    @abstractmethod
    async def set_status(
        self,
        job_id: UUID,
        status: IngestionJobStatus,
        error_count_delta: int = 0,
    ) -> IngestionJob: ...


# src/storage/repositories/cost_record_repo.py
from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID
from src.storage.models.cost_record import CostRecord

class ICostRecordRepository(ABC):
    @abstractmethod
    async def aggregate_monthly(
        self, tenant_id: UUID, year: int, month: int
    ) -> float: ...
    # Returns total cost_usd for the calendar month

    @abstractmethod
    async def breakdown_by_source(
        self, tenant_id: UUID, year: int, month: int
    ) -> list[dict]: ...
    # Returns list of {source, cost_usd}

    @abstractmethod
    async def breakdown_by_model(
        self, tenant_id: UUID, year: int, month: int
    ) -> list[dict]: ...

    @abstractmethod
    async def breakdown_by_workflow(
        self, tenant_id: UUID, year: int, month: int
    ) -> list[dict]: ...

    @abstractmethod
    async def daily_totals(
        self, tenant_id: UUID, start: date, end: date
    ) -> list[dict]: ...
    # Returns list of {date, cost_usd} for chart rendering

    @abstractmethod
    async def insert(self, record: CostRecord) -> CostRecord: ...


# src/storage/repositories/feature_flag_repo.py
from abc import ABC, abstractmethod
from uuid import UUID

class IFeatureFlagRepository(ABC):
    @abstractmethod
    async def list_all(self, environment: str) -> list["FeatureFlag"]: ...

    @abstractmethod
    async def get(self, flag_id: str, environment: str) -> "FeatureFlag | None": ...

    @abstractmethod
    async def set_enabled(
        self,
        flag_id: str,
        environment: str,
        enabled: bool,
        updated_by: UUID,
    ) -> "FeatureFlag": ...


# src/ingestion/job_registry.py
class JobRegistry:
    """Maps job_id → Celery task name. Populated at startup."""
    def register(self, job_id: str, celery_task_name: str) -> None: ...
    def get_task_name(self, job_id: str) -> str | None: ...
    def all_jobs(self) -> list[str]: ...  # returns job_ids


# src/ai/budget_guard.py
from uuid import UUID

class BudgetGuard:
    async def assert_under_limit(self, tenant_id: UUID) -> None:
        """
        Reads cost_record aggregate for current month.
        Raises BudgetHardStopError when spend >= 100% of threshold.
        Logs BudgetWarningEvent at >= 80%.
        Must be called before any AI-cost-incurring dispatch.
        """
        ...

    async def get_budget_status(self, tenant_id: UUID) -> "BudgetStatus":
        """
        Returns current spend, threshold, pct_used, warning_active, hard_stop_active.
        """
        ...

    async def set_threshold(self, tenant_id: UUID, threshold_usd: float) -> None: ...


class BudgetHardStopError(RuntimeError):
    """Raised when monthly AI + infra budget is exhausted."""
    ...


# src/admin/system/service.py — key method signatures
class SystemOpsService:
    async def list_ingestion_jobs(self, tenant_id: UUID) -> list[IngestionJobOut]: ...

    async def trigger_job(
        self, job_id: UUID, tenant_id: UUID
    ) -> TriggerResponse:
        """Dispatches Celery task via celery_app.send_task(); updates job status
        to running; returns task_id and dispatched_at."""
        ...

    async def get_cost_summary(
        self, tenant_id: UUID
    ) -> CostSummaryOut: ...

    async def set_budget_threshold(
        self, tenant_id: UUID, threshold_usd: float
    ) -> None: ...

    async def list_tracked_companies(
        self, tenant_id: UUID, page: int, page_size: int
    ) -> list[CompanyUniverseItemOut]: ...

    async def set_company_tracked(
        self, company_id: UUID, is_tracked: bool, tenant_id: UUID
    ) -> None: ...

    async def get_cache_stats(self) -> CacheStatsOut: ...

    async def force_refresh_cache(
        self, data_type: str, company_id: UUID | None
    ) -> None:
        """Deletes Redis keys matching the pattern for the given data_type
        and optional company scope. Next read will re-fetch from external source."""
        ...

    async def list_feature_flags(
        self, environment: str
    ) -> list[FeatureFlagOut]: ...

    async def toggle_feature_flag(
        self,
        flag_id: str,
        environment: str,
        enabled: bool,
        updated_by: UUID,
    ) -> FeatureFlagOut: ...
```

## Implementation Tasks

### TASK-001: DB Migration — ingestion_job, cost_record, feature_flag tables · M/TDD · alembic/versions/XXXX_add_system_ops_tables.py, src/storage/models/ingestion_job.py, src/storage/models/cost_record.py, src/storage/models/feature_flag.py

Create Alembic migration and SQLAlchemy ORM models for the three new tables.

**`ingestion_job` columns:** `job_id UUID PK DEFAULT gen_random_uuid()`,
`tenant_id UUID NOT NULL`, `name TEXT NOT NULL`, `schedule TEXT NOT NULL`
(cron expression), `last_run TIMESTAMPTZ`, `next_run TIMESTAMPTZ`,
`status TEXT NOT NULL DEFAULT 'idle' CHECK(status IN ('idle','running','failed'))`,
`error_count INT NOT NULL DEFAULT 0`, `last_error_trace TEXT`,
`updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
Index on `(tenant_id, status)`.

**`cost_record` columns:** `record_id UUID PK DEFAULT gen_random_uuid()`,
`tenant_id UUID NOT NULL`, `date DATE NOT NULL`, `source TEXT NOT NULL`,
`model TEXT`, `workflow_type TEXT`, `cost_usd FLOAT NOT NULL`,
`recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
Index on `(tenant_id, date)` for fast monthly aggregation.

**`feature_flag` columns:** `flag_id TEXT NOT NULL`, `environment TEXT NOT NULL`,
`enabled BOOL NOT NULL DEFAULT false`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
`updated_by UUID REFERENCES "user"(user_id)`.
PK: `(flag_id, environment)`.

Seed the migration with the full set of known feature flags for each standard environment
(`local`, `test`, `staging`, `production`):
- `realtime_mode` (default: `true` for local, `true` for production)
- `morning_brief` (default: `true`)
- `watchlist_scan` (default: `true`)
- `earnings_risk_brief` (default: `true`)
- `event_deep_dive` (default: `true`)
- `social_twitter` (default: `false` per D8)
- `social_stocktwits` (default: `false`)
- `social_reddit` (default: `false`)

Seed uses `INSERT ... ON CONFLICT DO NOTHING` so existing flag values are never overwritten.

**Tests to write first (TDD):**
- Migration applies and rolls back cleanly against a test PostgreSQL instance.
- `ingestion_job.status` CHECK constraint rejects values outside `{idle, running, failed}`.
- `feature_flag` PK `(flag_id, environment)` rejects duplicate inserts.
- `feature_flag` seed row for `social_twitter` has `enabled=false`.
- `cost_record` `(tenant_id, date)` index exists (introspect via `information_schema`).

**AC covered:** AC-001 (job schema prerequisite), AC-002 (cost_record schema), AC-005 (feature_flag schema)

---

### TASK-002: Repositories — IIngestionJobRepository, ICostRecordRepository, IFeatureFlagRepository · M/TDD · src/storage/repositories/ingestion_job_repo.py, src/storage/repositories/cost_record_repo.py, src/storage/repositories/feature_flag_repo.py, tests/unit/storage/test_system_ops_repos.py

Implement the three concrete repository classes behind the interfaces defined in Component
Design. All use SQLAlchemy 2.0 async sessions and parameterised queries only.

`PostgresCostRecordRepository.aggregate_monthly` uses a `SUM(cost_usd)` query grouped by
`tenant_id` + year-month truncation. `breakdown_by_source`, `breakdown_by_model`, and
`breakdown_by_workflow` use `GROUP BY source`, `GROUP BY model`, and
`GROUP BY workflow_type` respectively over the same date range.

`PostgresFeatureFlagRepository.set_enabled` uses an `UPDATE ... SET enabled=:enabled,
updated_at=now(), updated_by=:updated_by WHERE flag_id=:flag_id AND environment=:environment`
and returns the updated row.

**Tests to write first (TDD):**
- `IngestionJobRepo.list_all` returns only rows for the given `tenant_id`.
- `IngestionJobRepo.set_status` transitions `idle → running` and updates `updated_at`.
- `IngestionJobRepo.set_status` with `error_count_delta=1` increments `error_count`.
- `CostRecordRepo.aggregate_monthly` sums across all sources for the given month and returns zero for months with no rows.
- `CostRecordRepo.breakdown_by_source` groups correctly and excludes other tenants.
- `CostRecordRepo.daily_totals` returns one row per day within the range even when a day has no records (left join with a generate_series is acceptable, or filtered list).
- `FeatureFlagRepo.set_enabled(flag_id='morning_brief', environment='production', enabled=False)` persists the change; subsequent `get` reflects `enabled=False`.
- `FeatureFlagRepo.list_all` filters by environment.

**AC covered:** AC-001 (job status update), AC-002 (cost aggregation), AC-003 (is_tracked prerequisite — shared company_repo extension), AC-004 (cache stats prerequisite), AC-005 (feature flag persistence)

---

### TASK-003: Company repository extension — set_tracked · S/no-TDD · src/storage/repositories/company_repo.py

Extend the existing company repository (or create it if not yet present from PLAN-F-024)
with one additional method:

```python
async def set_tracked(
    self, company_id: UUID, is_tracked: bool, tenant_id: UUID
) -> None:
    """UPDATE company SET is_tracked=:is_tracked
       WHERE company_id=:company_id AND tenant_id=:tenant_id"""
```

Also add a `list_tracked` query:

```python
async def list_tracked(
    self, tenant_id: UUID, page: int, page_size: int
) -> list[Company]:
    """Returns companies where is_tracked=true, ordered by name, paginated."""
```

And a `search_by_name_or_ticker` query for the promote-company search:

```python
async def search_by_name_or_ticker(
    self, tenant_id: UUID, query: str, limit: int = 20
) -> list[Company]:
```

**AC covered:** AC-003 (is_tracked flag update + tracked list query)

---

### TASK-004: JobRegistry and manual trigger dispatch · M/TDD · src/ingestion/job_registry.py, src/ingestion/tasks.py, tests/unit/ingestion/test_job_registry.py

Implement `JobRegistry` as a module-level singleton populated at startup. The `@register_job`
decorator is applied to each Celery task in `src/ingestion/tasks.py` to publish its
`job_id` and `celery_task_name` into the registry.

At startup, the registry iterates over `IngestionJobRepository.list_all()` to cross-check
that every DB-registered job has a corresponding registered Celery task; jobs without
matching tasks are logged as warnings (not errors — allows for tasks that have been
decommissioned but not yet removed from the DB).

The `SystemOpsService.trigger_job` method:
1. Looks up `celery_task_name = registry.get_task_name(str(job_id))`.
2. Raises `JobNotFoundError` if the task is not registered.
3. Calls `celery_app.send_task(celery_task_name)`.
4. Calls `IngestionJobRepository.set_status(job_id, IngestionJobStatus.RUNNING)`.
5. Returns `TriggerResponse(task_id=..., dispatched_at=utcnow())`.

The Celery task wrapper in `tasks.py` must update job status to `idle` on success and
`failed` (with `error_count_delta=1`) in the `on_failure` callback.

**Tests to write first (TDD):**
- `JobRegistry.get_task_name` returns the correct task name for a registered job.
- `JobRegistry.get_task_name` returns `None` for an unknown `job_id`.
- `SystemOpsService.trigger_job` calls `celery_app.send_task` with the correct task name (mock Celery).
- `SystemOpsService.trigger_job` raises `JobNotFoundError` when job_id is not in registry.
- `SystemOpsService.trigger_job` calls `IngestionJobRepository.set_status(..., RUNNING)` after dispatching.
- Celery `on_failure` callback sets job status to `failed` and increments `error_count` by 1.

**AC covered:** AC-001 (manual trigger dispatched to Celery; status updates to running)

---

### TASK-005: BudgetGuard — cost enforcement and threshold management · L/TDD · src/ai/budget_guard.py, tests/unit/ai/test_budget_guard.py

Implement `BudgetGuard` backed by `ICostRecordRepository`. The guard reads the current
month's aggregate via `aggregate_monthly` and compares against the configured threshold.

Budget threshold is stored in the `feature_flag` table using the reserved flag ID
`budget_threshold_usd` with `environment` set to the active environment, and the `enabled`
column repurposed as a sentinel (`true`); the threshold value is stored as a JSONB
extension column OR alternatively in a separate `tenant_config` JSONB field on the `user`
table. Given the data model already has `user.settings JSONB`, the threshold is stored as
`user.settings['budget_threshold_usd']` for the admin user of the tenant, defaulting to
100.0. The `BudgetGuard.set_threshold` method updates this settings key.

`assert_under_limit` logic:
```
pct = (current_month_spend / threshold_usd) * 100
if pct >= 100:
    append_audit_event(event_type='budget_hard_stop', payload={pct, spend, threshold})
    raise BudgetHardStopError(f"Budget exhausted: ${spend:.2f} of ${threshold:.2f}")
if pct >= 80:
    append_audit_event(event_type='budget_warning', payload={pct, spend, threshold})
    # does not raise — workflow proceeds with warning logged
```

The audit event is written via `WorkflowRunRepository.append_audit_event()` (from
PLAN-F-013's episodic Layer 1 log pattern). If no active `workflow_id` exists in the call
context, write a standalone `workflow_run` sentinel row with `workflow_type='budget_check'`.

**Tests to write first (TDD):**
- `assert_under_limit` does not raise when spend is 0% of threshold.
- `assert_under_limit` does not raise when spend is 79% of threshold; verifies warning audit event is written.
- `assert_under_limit` does not raise when spend is exactly 80%; verifies warning audit event written.
- `assert_under_limit` raises `BudgetHardStopError` when spend is 100% of threshold; verifies hard-stop audit event written.
- `assert_under_limit` raises `BudgetHardStopError` when spend exceeds 100%.
- `get_budget_status` returns correct `pct_used`, `warning_active=True` at 82%, `hard_stop_active=False`.
- `get_budget_status` returns `hard_stop_active=True` at 100%.
- `set_threshold` persists new threshold value; subsequent `get_budget_status` uses updated threshold.
- Integration: `assert_under_limit` called from a mocked Celery task entry point raises `BudgetHardStopError` and prevents the task body from executing.

**AC covered:** AC-002 (80% warning alert; 100% hard-stop; no further AI workflows dispatched)

---

### TASK-006: Cache inspection and force-refresh service · M/TDD · src/admin/system/cache_service.py, tests/unit/admin/test_cache_service.py

Implement `CacheInspectionService` backed by the Redis client and the PostgreSQL storage
layer for storage-size statistics.

`get_cache_stats()` returns a `CacheStatsOut` Pydantic model with:
- `price_bars_keys` — count of Redis keys matching `price_bar:*`
- `embeddings_keys` — count matching `embedding:*`
- `event_data_keys` — count matching `event:*`
- `total_redis_memory_bytes` — from `INFO memory` (`used_memory`)
- `daily_growth` — list of `{date, memory_bytes}` for the last 30 days sourced from a
  daily snapshot table or approximated from `price_bar` row counts.

`force_refresh_cache(data_type, company_id)` deletes Redis keys matching the pattern:
- `data_type='price_bars'`, `company_id=None` → `DEL price_bar:*`
- `data_type='price_bars'`, `company_id=<uuid>` → `DEL price_bar:<uuid>:*`
- `data_type='embeddings'`, `company_id=None` → `DEL embedding:*`
- `data_type='event_data'`, `company_id=None` → `DEL event:*`

Uses Redis `SCAN` + `DEL` pipeline (not `KEYS`) to avoid blocking. After deletion,
subsequent data access by ingestion/cache-or-fetch logic will miss and re-fetch from
the external source.

Supported `data_type` values: `price_bars`, `embeddings`, `event_data`. Any other value
raises `InvalidDataTypeError`.

**Tests to write first (TDD):**
- `force_refresh_cache('price_bars', None)` deletes all `price_bar:*` keys (mock Redis; verify SCAN + DEL called).
- `force_refresh_cache('price_bars', company_id=some_uuid)` deletes only `price_bar:{uuid}:*` keys.
- `force_refresh_cache('embeddings', None)` deletes `embedding:*` keys.
- `force_refresh_cache('invalid_type', None)` raises `InvalidDataTypeError`.
- `get_cache_stats()` returns non-negative integer counts for all three key families.
- `get_cache_stats()` returns `total_redis_memory_bytes > 0` when Redis is populated.

**AC covered:** AC-004 (force-refresh clears cache; next access fetches fresh from external source)

---

### TASK-007: Feature flag runtime reader — FeatureFlagService · M/TDD · src/admin/system/feature_flag_service.py, tests/unit/admin/test_feature_flag_service.py

Implement `FeatureFlagService` with an in-process cache so that flag reads are cheap
(< 1 ms) at every Celery task entry point. The cache is a simple `dict[tuple[str,str], bool]`
loaded on startup and refreshed within 5 seconds of any `set_enabled` call via a Redis
pub/sub channel `feature_flags_updated`.

Public interface:
```python
class FeatureFlagService:
    def is_enabled(self, flag_id: str, environment: str) -> bool:
        """Returns cached flag value. Defaults to True if flag unknown (safe default
        for workflow flags); returns False for social source flags (safe default per D8)."""

    async def set_enabled(
        self, flag_id: str, environment: str, enabled: bool, updated_by: UUID
    ) -> FeatureFlag:
        """Persists via IFeatureFlagRepository; publishes 'feature_flags_updated'
        message to Redis pub/sub channel; updates local cache."""

    async def reload(self) -> None:
        """Reloads all flags from DB into local cache. Called on startup and on
        pub/sub message received."""
```

The Celery beat task for Morning Brief checks `feature_flag_service.is_enabled('morning_brief', env)` before dispatching. If `False`, the task logs and returns without dispatching any workflow. The same pattern applies to all workflow-gating flags.

Integration point: ARCHITECTURE §11 Feature Flag System — "Changes apply at runtime without restart." The pub/sub mechanism (Redis) ensures all worker processes receive the invalidation within 5 seconds.

**Tests to write first (TDD):**
- `is_enabled('morning_brief', 'production')` returns `True` after loading a `True` flag from DB.
- `is_enabled('social_twitter', 'production')` returns `False` after loading a `False` flag.
- `is_enabled('unknown_flag', 'production')` returns `True` (safe default for workflow flags).
- `set_enabled('morning_brief', 'production', False, user_id)` persists to DB and publishes to Redis pub/sub.
- After `set_enabled`, `is_enabled` returns the updated value from local cache.
- `reload()` updates local cache to reflect DB state (mock DB returning updated flag).
- Celery beat task: when `is_enabled('morning_brief', env)` is `False`, the task returns without calling workflow dispatch (mock FeatureFlagService).

**AC covered:** AC-005 (Morning Brief feature flag toggle prevents task dispatch; applies at runtime)

---

### TASK-008: FastAPI system operations router · L/TDD · src/admin/system/router.py, src/admin/system/schemas.py, src/admin/system/service.py, tests/integration/api/test_system_ops_endpoints.py

Implement `SystemOpsService` and the FastAPI `APIRouter` at `/api/v1/admin/system`.
All endpoints require `require_admin()` from `src/admin/dependencies.py` (established by
PLAN-F-028).

**Endpoint surface:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/admin/system/jobs` | List all ingestion jobs with current status |
| POST | `/api/v1/admin/system/jobs/{job_id}/trigger` | Manually dispatch job to Celery |
| GET | `/api/v1/admin/system/cost` | Cost summary: aggregate + breakdown + budget status |
| PATCH | `/api/v1/admin/system/cost/threshold` | Update budget threshold (body: `{threshold_usd: float}`) |
| GET | `/api/v1/admin/system/companies` | List tracked companies (paginated) |
| POST | `/api/v1/admin/system/companies/{company_id}/track` | Set `is_tracked=true` |
| DELETE | `/api/v1/admin/system/companies/{company_id}/track` | Set `is_tracked=false` |
| GET | `/api/v1/admin/system/companies/search` | Search by name/ticker (query param `q`) |
| GET | `/api/v1/admin/system/cache` | Cache stats (key counts, memory, daily growth) |
| POST | `/api/v1/admin/system/cache/refresh` | Force-refresh cache (body: `{data_type, company_id?}`) |
| GET | `/api/v1/admin/system/flags` | List all feature flags for the active environment |
| PATCH | `/api/v1/admin/system/flags/{flag_id}` | Toggle feature flag (body: `{enabled: bool}`) |

Response envelope: `{"data": ..., "meta": {}, "error": null}` per DEV-STANDARDS §7.
Non-admin → HTTP 403. Job not found → HTTP 404. Invalid data_type → HTTP 422.

Environment for feature flags is derived from the `ENVIRONMENT` env var read at startup;
it is not accepted from the request body (prevents cross-environment manipulation).

**Tests to write first (TDD):**
- `POST /jobs/{job_id}/trigger` with `role=end_user` returns 403.
- `POST /jobs/{job_id}/trigger` with `role=admin` returns 200 with `task_id` in response.
- `POST /jobs/{known_job_id}/trigger` dispatches Celery task (mock Celery; verify `send_task` called).
- `POST /jobs/{unknown_job_id}/trigger` returns 404.
- `GET /cost` returns `aggregate_spend_usd`, `threshold_usd`, `pct_used`, `warning_active`, `hard_stop_active`.
- `PATCH /cost/threshold` with `{threshold_usd: 80.0}` persists and subsequent `GET /cost` reflects new threshold.
- `POST /companies/{company_id}/track` returns 200 and sets `is_tracked=true` in DB.
- `DELETE /companies/{company_id}/track` returns 200 and sets `is_tracked=false` in DB.
- `POST /cache/refresh` with `{data_type: "price_bars"}` calls `force_refresh_cache` (mock CacheInspectionService).
- `POST /cache/refresh` with `{data_type: "invalid"}` returns 422.
- `PATCH /flags/morning_brief` with `{enabled: false}` returns 200; subsequent `GET /flags` shows `enabled=false`.
- `GET /flags` returns only flags for the active environment.

**AC covered:** AC-001 (trigger endpoint), AC-002 (cost endpoint + threshold update), AC-003 (track/untrack endpoints), AC-004 (cache refresh endpoint), AC-005 (flag toggle endpoint)

---

### TASK-009: Frontend system operations page — ingestion jobs and cost monitor · M/TDD · frontend/src/pages/admin/system/SystemOpsPage.tsx, frontend/src/pages/admin/system/IngestionJobsTab.tsx, frontend/src/pages/admin/system/CostMonitorTab.tsx, frontend/src/pages/admin/system/hooks/useSystemOps.ts

Build the `SystemOpsPage` (tab container) and the first two tabs.

`IngestionJobsTab`: table columns — name, schedule (cron expression), last_run (formatted),
next_run (formatted), status (badge: idle=grey, running=blue spinner, failed=red), error_count.
"Manual Trigger" button per row; disabled when `status=running`. On click: calls
`POST .../trigger`; button shows spinner during request; on success toasts "Job dispatched";
on error toasts error message.

`CostMonitorTab`: Aggregate gauge showing `pct_used` with color bands (green < 80%,
amber 80–99%, red ≥ 100%). Hard-stop banner appears when `hard_stop_active=true`.
Three breakdown tables: by source, by model, by workflow. 30-day cost bar chart
(Recharts). Budget threshold edit: inline number input + Save button.

`useSystemOps.ts`: TanStack Query hooks for all system-ops endpoints. `useTriggerJob`
mutation invalidates `useIngestionJobs` query on success. `useUpdateThreshold` mutation
invalidates `useCostSummary`.

**Tests to write first (TDD):**
- `IngestionJobsTab`: renders job list from mock data; "Manual Trigger" button visible per row.
- `IngestionJobsTab`: clicking trigger calls `POST .../trigger` (mock hook); button disabled during loading.
- `IngestionJobsTab`: `status=failed` row shows red badge and non-zero error_count.
- `CostMonitorTab`: renders budget gauge with correct percentage from mock data.
- `CostMonitorTab`: renders hard-stop banner when `hard_stop_active=true`.
- `CostMonitorTab`: updating threshold calls `PATCH /cost/threshold` with new value.
- `useSystemOps`: `useTriggerJob` calls correct endpoint and invalidates job list query.

**AC covered:** AC-001 (trigger UI; status visible), AC-002 (cost monitor gauge + hard-stop banner)

---

### TASK-010: Frontend system operations page — company universe, cache, feature flags · M/TDD · frontend/src/pages/admin/system/CompanyUniverseTab.tsx, frontend/src/pages/admin/system/CacheInspectionTab.tsx, frontend/src/pages/admin/system/FeatureFlagsTab.tsx

Build the remaining three tabs.

`CompanyUniverseTab`: Paginated table of tracked companies (market_cap, sector, status).
"Remove from tracked" button per row (calls `DELETE .../track`). "Add company" inline
search bar (calls `GET .../companies/search?q=<text>`); search results appear in a
dropdown; clicking a result calls `POST .../track`. TanStack Query infinite scroll or
standard pagination.

`CacheInspectionTab`: Table of `{data_type, key_count, estimated_size}`. "Force Refresh"
button per row (calls `POST .../cache/refresh` with `data_type`). Optional
`company_id` input shown for `price_bars` type. 30-day storage growth chart (Recharts).

`FeatureFlagsTab`: Table of `{flag_id, environment, enabled, updated_at, updated_by}`.
Toggle switch per row. Toggle calls `PATCH .../flags/{flag_id}`. Optimistic UI: switch
flips immediately, reverts on error. `social_twitter` row shows a "Off by default (D8)"
tooltip.

**Tests to write first (TDD):**
- `CompanyUniverseTab`: renders tracked company list from mock; "Remove" button calls `DELETE .../track`.
- `CompanyUniverseTab`: search input debounces and calls `GET /search?q=...`; result dropdown appears.
- `CacheInspectionTab`: "Force Refresh" button for `price_bars` calls `POST /cache/refresh` with correct payload.
- `FeatureFlagsTab`: toggle switch for `morning_brief` calls `PATCH /flags/morning_brief` with `{enabled: false}`.
- `FeatureFlagsTab`: optimistic toggle reverts on API error.
- `FeatureFlagsTab`: `social_twitter` row renders "Off by default" tooltip.

**AC covered:** AC-003 (company promote/demote UI), AC-004 (cache force-refresh UI), AC-005 (feature flag toggle UI)

---

### TASK-011: Wire router into main app and register admin nav entry · XS/no-TDD · src/api/main.py, frontend/src/App.tsx, frontend/src/pages/admin/AdminNav.tsx

Register `system_ops_router` on the FastAPI app under `/api/v1/admin`.
Add `/admin/system` route in the React router under the existing admin role guard.
Add "System Operations" nav link in `AdminNav`.

Wire `BudgetGuard.assert_under_limit()` into `src/ai/workflows/base_workflow.py` startup
hook. Wire `FeatureFlagService.is_enabled()` check into Celery beat task functions for
all five workflow types.

**AC covered:** AC-001 (endpoint reachable), AC-002 (budget guard active in workflow dispatch), AC-005 (feature flag check active in Celery beat)

---

## Acceptance Criteria Coverage

- AC-001: Admin clicks "Manual Trigger" on an ingestion job → job dispatched immediately to Celery queue; status updates to "running" within 5 seconds → TASK-004, TASK-008, TASK-009
- AC-002: Aggregate AI + infrastructure spend reaches 80% of configured budget threshold → cost monitor displays warning alert; at 100% displays hard-stop indicator and no further AI-cost-incurring workflows dispatched → TASK-005, TASK-008, TASK-009, TASK-011
- AC-003: Admin promotes on-demand company to tracked status → is_tracked flag set to true; company included in subsequent ingestion, scoring, and exposure mapping runs → TASK-003, TASK-008, TASK-010
- AC-004: Admin force-refreshes cache for specific data type → next data access for that type fetches fresh data from external source rather than cached value → TASK-006, TASK-008, TASK-010
- AC-005: Admin toggles "Morning Brief" feature flag to disabled → no Morning Brief Celery tasks dispatched on subsequent cron fires until re-enabled → TASK-001, TASK-002, TASK-007, TASK-008, TASK-010, TASK-011

## Acceptance Notes

The `BudgetGuard.assert_under_limit()` call must be placed at the Celery task entry point
(inside the task function body, before any AI API calls), not at the FastAPI API layer.
ARCHITECTURE §12.6 is explicit: hard-stop enforcement is at the Celery task level. The API
cost endpoint is read-only reporting.

For `force_refresh_cache`, Redis key deletion uses `SCAN` + pipeline `DEL` to avoid
blocking the server with a `KEYS *` call. The dev-executor must enforce this pattern and
not use `redis.keys()`.

The `ENVIRONMENT` env var (`local | test | staging | production`) determines which set of
feature flags is loaded and toggled. The frontend reads the active environment from the API
response (`GET /api/v1/admin/system/flags` returns flags for the server's active environment)
and displays an environment badge.

Budget threshold storage uses `user.settings JSONB` for the tenant admin user because no
dedicated tenant config table exists in the current data model. The key is
`budget_threshold_usd` (float). Default: `100.0`. If the settings JSON does not contain
this key, `BudgetGuard` treats the threshold as `100.0`.

## Risks and Notes

- **Budget guard and workflow concurrency:** If two workflows start simultaneously just
  below the budget limit, both may pass the guard before either records its cost. A
  `SELECT ... FOR UPDATE` on an aggregate is impractical. Accept the slight overshoot risk
  at MVP; document it as a known limitation. The daily aggregation approach means the
  worst-case overshoot is one workflow's cost (~$2.00), within acceptable bounds for a
  $100/month ceiling.

- **`is_tracked` impact on ingestion:** Setting `is_tracked=true` for a company causes it
  to be picked up by the next scheduled ingestion run. There is no immediate back-fill.
  The UI should communicate this with a note: "Company will be included in the next
  scheduled ingestion cycle." No separate back-fill task is in scope for this plan.

- **Cache key namespace:** This plan assumes Redis keys follow the patterns
  `price_bar:<company_id>:*`, `embedding:<entity_id>:*`, and `event:<event_id>:*`. If
  PLAN-F-032 (Cache-or-Fetch) uses different key namespaces, TASK-006 must be updated
  before execution. The dev-executor must verify key patterns against the PLAN-F-032
  implementation before writing TASK-006.

- **`FeatureFlagService` pub/sub fan-out:** Redis pub/sub works within a single Redis
  instance. Each Celery worker process subscribes independently. In a multi-worker
  deployment, each worker receives the invalidation and calls `reload()`. If a worker is
  restarting during a flag toggle, it will reload from DB on startup — safe.

- **PLAN-F-033 dependency (JWT auth):** `require_admin()` from PLAN-F-028 delegates to
  PLAN-F-033's JWT middleware. If PLAN-F-033 is not yet executed at integration test time,
  mock the dependency using FastAPI's `dependency_overrides`.

- **`ingestion_job` initial population:** The migration seeds the `ingestion_job` table
  with the known Celery beat jobs (GDELT poll, EDGAR feed, price bar fetch, etc.) for the
  default tenant. The dev-executor must enumerate these from `src/config/celery_app.py`
  beat schedule at execution time and include them in the migration seed block using
  `INSERT ... ON CONFLICT DO NOTHING`.
