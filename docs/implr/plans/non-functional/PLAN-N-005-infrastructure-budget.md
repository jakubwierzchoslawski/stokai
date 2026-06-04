---
plan_id: PLAN-N-005
slug: infrastructure-budget
title: MVP Infrastructure and AI Total Budget
linked_requirement: REQ-N-005
type: non-functional
status: done
blocked_reason:
complexity: S
tdd_required: false
linked_nfrs:
  - { id: REQ-N-003, reason: "Mode A per-event costs feed into the monthly AI total tracked by this plan" }
  - { id: REQ-N-004, reason: "Mode B per-report costs and per-user daily budget feed into the monthly AI total tracked by this plan" }
dependencies:
  - { id: PLAN-N-003, reason: "Establishes cost_record writes for Mode A pipeline runs; this plan's monitor queries those rows" }
  - { id: PLAN-N-004, reason: "Establishes cost_record writes for Mode B workflow runs and the cost_limited flag; this plan's monitor queries those rows" }
  - { id: PLAN-F-030, reason: "Admin System Operations plan introduces the cost_record table, ICostRecordRepository, and the admin cost monitor UI skeleton; this plan extends them with infrastructure cost tracking and budget threshold alerting" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-03T00:00:00Z
---

# PLAN-N-005 — MVP Infrastructure and AI Total Budget

## Linked Requirement
**REQ-N-005** — MVP Infrastructure and AI Total Budget
Status: approved | Jira: —

## Objective

Extend the existing admin cost monitor (introduced by PLAN-F-030 and populated by PLAN-N-003 and
PLAN-N-004) with infrastructure cost tracking and two budget-threshold alerts so that the combined
AI plus infrastructure monthly spend is always visible and never silently exceeds $100. Concretely,
this plan introduces: (1) an `infrastructure_cost` table and its repository for recording hosting,
Redis, and managed-database charges entered by an admin; (2) a `MonthlyBudgetMonitor` service that
aggregates AI costs from `cost_record` and infrastructure costs from `infrastructure_cost` into a
single monthly total; (3) a FastAPI admin endpoint that exposes the breakdown by model and by
infrastructure line item alongside a current-month percentage-of-$100 indicator; and (4) a Celery
beat task that fires a structured budget-alert event and an admin notification email when monthly
spend reaches $80 (80%) and logs a hard-limit alert when it reaches $100. No automatic system
shutdown is implemented — the $100 threshold generates an alert, not a kill switch.

## Architecture Context

This plan operates at the intersection of Layer 3 (Storage), Layer 4 (Processing), and Layer 5
(Serving — Admin API) of the six-layer model (ARCHITECTURE.md §4).

**Layer 3 — Storage (`src/storage/`)**: PLAN-F-030 introduces `cost_record` (AI API spend per
workflow or pipeline run) and `ICostRecordRepository`. This plan introduces `infrastructure_cost`
(monthly hosting entries keyed by cost category) and `IInfrastructureCostRepository`. Both tables
feed `MonthlyBudgetMonitor`.

**Layer 4 — Processing (`src/admin/`)**: `MonthlyBudgetMonitor` aggregates the two cost sources
into a `MonthlyBudgetSummary` Pydantic model. A Celery beat task (`check_monthly_budget_task`)
runs daily at 09:00 UTC, reads the current-month summary, and dispatches alert notifications at
the 80% and 100% thresholds. This task lives in the `admin` module, consistent with PLAN-F-030's
placement of ingestion-job monitoring tasks.

**Layer 5 — Serving (`src/api/routers/admin/`)**: A new endpoint `GET /api/v1/admin/cost-monitor`
extends the admin System Operations panel (ARCHITECTURE.md §11 Admin Panel, System Operations
section). The endpoint returns the full `MonthlyBudgetSummary` — AI costs broken down by model,
infrastructure costs broken down by category, running total, and a `pct_of_budget` field (0–100)
used by the UI to render the visual indicator (AC-002).

**Cost Governance (ARCHITECTURE.md §12.6)**: D12 sets the hard budget ceiling at $100/month
combined AI + infrastructure. The three-level enforcement hierarchy (per-agent → per-workflow →
per-user/day) established by PLAN-N-003 and PLAN-N-004 covers per-run controls. This plan adds
the fourth, outermost level: the total monthly ceiling with an 80% early-warning alert.

**Portability (ARCHITECTURE.md §12.5)**: The `infrastructure_cost` table is manually populated
by the admin rather than polled from a cloud billing API. This ensures the monitoring layer works
identically in self-hosted Docker and Azure deployments without cloud-provider SDK dependencies,
consistent with Principle 4.

**Module ownership for this plan:**
- `src/storage/models/infrastructure_cost.py` — SQLAlchemy ORM model
- `src/storage/repositories/infrastructure_cost_repo.py` — `IInfrastructureCostRepository` + Postgres implementation
- `src/storage/migrations/` — Alembic migration for `infrastructure_cost` table
- `src/admin/budget_monitor.py` — `MonthlyBudgetMonitor` service and `MonthlyBudgetSummary` schema
- `src/admin/tasks/check_monthly_budget.py` — Celery beat task
- `src/api/routers/admin/cost_monitor.py` — FastAPI admin endpoint
- `src/config/celery_app.py` — beat schedule entry for the daily budget check task

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-003 | AI costs from Mode A pipeline runs written to `cost_record` | `MonthlyBudgetMonitor` reads `cost_record` for AI sub-total; no modification to PLAN-N-003 output |
| REQ-N-004 | AI costs from Mode B workflow runs written to `cost_record` | `MonthlyBudgetMonitor` reads `cost_record` for AI sub-total; no modification to PLAN-N-004 output |
| REQ-N-005 (self) | Combined AI + infrastructure < $100/month; alert at $80; hard-limit notification at $100 | All tasks in this plan exist to satisfy AC-001, AC-002, and AC-003 |

## Component Design

### New Components

```
src/storage/models/
  infrastructure_cost.py     — SQLAlchemy ORM model for infrastructure_cost table

src/storage/repositories/
  infrastructure_cost_repo.py
    IInfrastructureCostRepository  — abstract base class (interface)
    PostgresInfrastructureCostRepo — implementation

src/storage/migrations/
  NNNN_create_infrastructure_cost.py  — Alembic migration; creates infrastructure_cost table

src/admin/
  budget_monitor.py
    MonthlyBudgetSummary   — Pydantic response model (AI breakdown + infra breakdown + totals)
    AiModelCostLine        — Pydantic sub-model: model_id, cost_usd, call_count
    InfraCostLine          — Pydantic sub-model: category, description, cost_usd
    MonthlyBudgetMonitor   — service: aggregates cost_record + infrastructure_cost

src/admin/tasks/
  check_monthly_budget.py
    check_monthly_budget_task  — Celery task; fires at 09:00 UTC daily via beat schedule

src/api/routers/admin/
  cost_monitor.py
    router                 — FastAPI APIRouter; GET /api/v1/admin/cost-monitor
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/storage/repositories/cost_record_repo.py` | Add `monthly_total_by_model(year: int, month: int, tenant_id: UUID) -> dict[str, tuple[float, int]]` method to `ICostRecordRepository` | `MonthlyBudgetMonitor` needs AI costs broken down by model and call count for AC-002 breakdown display |
| `src/api/routers/admin/__init__.py` | Register the new `cost_monitor` router | Wire the endpoint into the admin router group |
| `src/config/celery_app.py` | Add `check_monthly_budget_task` to Celery beat schedule: daily at 09:00 UTC | Enables daily automated threshold checks |
| `src/admin/data_sources/health_flush_task.py` | No change — reference only; confirms the Celery task pattern this plan follows | N/A |

### Interfaces and Contracts

```python
# src/storage/models/infrastructure_cost.py

import enum
from datetime import date
from uuid import UUID, uuid4
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from src.storage.models.base import Base

class InfraCostCategory(str, enum.Enum):
    HOSTING = "hosting"           # compute: VM, container service
    DATABASE = "database"         # managed PostgreSQL / TimescaleDB
    REDIS = "redis"               # managed Redis
    OBSERVABILITY = "observability"  # Langfuse infra (ClickHouse + Langfuse DB)
    STORAGE = "storage"           # blob / object storage
    NETWORKING = "networking"     # egress, load balancer
    OTHER = "other"

class InfrastructureCost(Base):
    __tablename__ = "infrastructure_cost"

    cost_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(sa.ForeignKey("user.tenant_id"), nullable=True)
    billing_month: Mapped[date]          # first day of the billing month, e.g. 2026-06-01
    category: Mapped[InfraCostCategory]
    description: Mapped[str]             # free-text label, e.g. "Azure Container Apps – api"
    cost_usd: Mapped[float]              # actual or estimated monthly cost in USD
    recorded_at: Mapped[sa.DateTime]     # when the admin entered this record
    recorded_by: Mapped[UUID]            # user_id of the admin who entered it
```

```python
# src/storage/repositories/infrastructure_cost_repo.py

from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID
from src.storage.models.infrastructure_cost import InfrastructureCost, InfraCostCategory

class IInfrastructureCostRepository(ABC):

    @abstractmethod
    async def insert(self, record: InfrastructureCost) -> InfrastructureCost:
        """Persist a new infrastructure cost record."""
        ...

    @abstractmethod
    async def monthly_total(
        self,
        billing_month: date,
        tenant_id: UUID | None = None,
    ) -> float:
        """Return sum of cost_usd for the given billing_month.
        billing_month must be the first day of the month (normalised internally).
        If tenant_id is None, returns the global total (single-tenant MVP)."""
        ...

    @abstractmethod
    async def monthly_by_category(
        self,
        billing_month: date,
        tenant_id: UUID | None = None,
    ) -> list[tuple[InfraCostCategory, str, float]]:
        """Return [(category, description, cost_usd)] rows for the billing month,
        ordered by cost_usd descending."""
        ...
```

```python
# src/storage/repositories/cost_record_repo.py  (new method on existing interface)

# Added to ICostRecordRepository and PostgresCostRecordRepository:

@abstractmethod
async def monthly_total_by_model(
    self,
    year: int,
    month: int,
    tenant_id: UUID | None = None,
) -> dict[str, tuple[float, int]]:
    """Return {model_id: (total_cost_usd, call_count)} for the given calendar month.
    Aggregates all cost_record rows where EXTRACT(year)=year AND EXTRACT(month)=month.
    If tenant_id is None, aggregates across all tenants (global view for single-tenant MVP)."""
    ...
```

```python
# src/admin/budget_monitor.py

from __future__ import annotations
from datetime import date
from uuid import UUID
from pydantic import BaseModel

MONTHLY_BUDGET_USD: float = 100.0
ALERT_THRESHOLD_USD: float = 80.0   # 80% of MONTHLY_BUDGET_USD

class AiModelCostLine(BaseModel):
    model_id: str        # e.g. "claude-haiku-4-5", "claude-sonnet-4-6", "text-embedding-3-small"
    cost_usd: float
    call_count: int

class InfraCostLine(BaseModel):
    category: str        # InfraCostCategory.value
    description: str
    cost_usd: float

class MonthlyBudgetSummary(BaseModel):
    billing_month: date          # first day of the month, e.g. 2026-06-01
    ai_costs: list[AiModelCostLine]
    ai_total_usd: float
    infra_costs: list[InfraCostLine]
    infra_total_usd: float
    combined_total_usd: float
    budget_usd: float            # always MONTHLY_BUDGET_USD ($100.00)
    pct_of_budget: float         # 0.0 – 100.0+ (can exceed 100 if over budget)
    alert_threshold_usd: float   # always ALERT_THRESHOLD_USD ($80.00)
    over_alert_threshold: bool
    over_budget: bool

class MonthlyBudgetMonitor:
    """
    Aggregates AI costs (from cost_record via ICostRecordRepository) and
    infrastructure costs (from infrastructure_cost via IInfrastructureCostRepository)
    into a single MonthlyBudgetSummary.

    No external API calls. No side effects. Read-only service.
    """

    def __init__(
        self,
        cost_record_repo: "ICostRecordRepository",
        infra_cost_repo: "IInfrastructureCostRepository",
    ) -> None: ...

    async def summarise(
        self,
        billing_month: date,
        tenant_id: UUID | None = None,
    ) -> MonthlyBudgetSummary:
        """
        1. Calls cost_record_repo.monthly_total_by_model(year, month, tenant_id)
           → builds ai_costs list and ai_total_usd.
        2. Calls infra_cost_repo.monthly_by_category(billing_month, tenant_id)
           → builds infra_costs list and infra_total_usd.
        3. Computes combined_total_usd, pct_of_budget, over_alert_threshold, over_budget.
        4. Returns MonthlyBudgetSummary.
        billing_month must be the first day of the month; raises ValueError otherwise.
        """
        ...
```

```python
# src/admin/tasks/check_monthly_budget.py

from celery import shared_task
from datetime import date

@shared_task(name="admin.check_monthly_budget", bind=True, max_retries=3)
def check_monthly_budget_task(self) -> None:
    """
    Daily Celery beat task (09:00 UTC).
    1. Calls MonthlyBudgetMonitor.summarise(billing_month=first_day_of_current_month()).
    2. If summary.over_budget:
         - Logs ERROR with structured fields: combined_total_usd, budget_usd, pct_of_budget.
         - Sends admin email via SendGrid: subject "STOKAI BUDGET HARD LIMIT: $100/month reached".
    3. If summary.over_alert_threshold and not summary.over_budget:
         - Logs WARNING with structured fields.
         - Sends admin email via SendGrid: subject "StokAI budget alert: 80% of $100/month used".
    4. If neither threshold is crossed: logs INFO with current combined_total_usd.
    No automatic system shutdown is triggered.
    """
    ...
```

```python
# src/api/routers/admin/cost_monitor.py

from fastapi import APIRouter, Depends
from src.admin.budget_monitor import MonthlyBudgetSummary

router = APIRouter(prefix="/admin/cost-monitor", tags=["admin"])

@router.get(
    "",
    response_model=MonthlyBudgetSummary,
    summary="Monthly AI + infrastructure cost breakdown vs $100 budget",
)
async def get_cost_monitor(
    # Dependency-injected: MonthlyBudgetMonitor, current_admin_user (role == "admin")
) -> MonthlyBudgetSummary:
    """
    Returns the current-month MonthlyBudgetSummary.
    - billing_month defaults to the first day of the current calendar month.
    - Requires admin role (JWT, role="admin").
    - No query parameters for MVP (single-tenant; month is always current month).
    """
    ...
```

## Implementation Tasks

### TASK-001: infrastructure_cost table — ORM model and Alembic migration · S/no-TDD · src/storage/models/infrastructure_cost.py, src/storage/migrations/NNNN_create_infrastructure_cost.py

Implement the `InfrastructureCost` SQLAlchemy ORM model exactly as specified in Interfaces and
Contracts. Write an Alembic migration that creates the `infrastructure_cost` table with columns:
`cost_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `tenant_id UUID NULLABLE`,
`billing_month DATE NOT NULL`, `category VARCHAR(32) NOT NULL`, `description TEXT NOT NULL`,
`cost_usd NUMERIC(10,4) NOT NULL CHECK (cost_usd >= 0)`, `recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
`recorded_by UUID NOT NULL`. Add a non-unique index on `(billing_month, tenant_id)` to support
the monthly aggregation queries efficiently. The `downgrade()` must drop the table and the index.
The `InfraCostCategory` enum string values match the `category` column — no separate DB enum
type; store as VARCHAR to avoid migration complexity on category additions.

**AC covered**: AC-002 (enables infrastructure cost line-items in the monitor breakdown)

---

### TASK-002: IInfrastructureCostRepository — interface and Postgres implementation · S/no-TDD · src/storage/repositories/infrastructure_cost_repo.py

Implement `IInfrastructureCostRepository` (abstract base class) and
`PostgresInfrastructureCostRepository` (SQLAlchemy async implementation) with three methods as
specified in Interfaces and Contracts. Key behaviour:
- `insert`: persists the record; returns the persisted instance with `cost_id` populated.
- `monthly_total`: normalises `billing_month` to the first day of its month internally (raises
  `ValueError` if the input date is not the first of a month — caller is responsible); sums
  `cost_usd` for all rows in that month; returns `0.0` when no rows exist.
- `monthly_by_category`: same month normalisation; returns one row per `(category, description)`
  pair, ordered by `cost_usd` DESC. Multiple rows with the same category are returned individually
  (not merged) — the UI groups by category.

**AC covered**: AC-002 (infrastructure cost data available to the monitor)

---

### TASK-003: monthly_total_by_model — cost_record repository extension · S/no-TDD · src/storage/repositories/cost_record_repo.py

Add `monthly_total_by_model(year, month, tenant_id) -> dict[str, tuple[float, int]]` to the
`ICostRecordRepository` abstract interface and implement it on `PostgresCostRecordRepository`.
The query groups `cost_record` rows by `model_id` (or `workflow_type` if `model_id` is not a
column on `cost_record` — align with whatever column PLAN-F-030 establishes; use `source_model`
or `workflow_type` as the grouping key, emitting one line per distinct value). Each entry in the
returned dict maps the grouping key to `(sum(cost_usd), count(*))`. If no rows exist for the
month, return an empty dict. This method is additive — it does not modify any existing method
on the interface.

**AC covered**: AC-002 (AI cost breakdown by model available to the monitor)

---

### TASK-004: MonthlyBudgetMonitor service · S/no-TDD · src/admin/budget_monitor.py

Implement `MonthlyBudgetMonitor.summarise` as specified in Interfaces and Contracts. The method
is purely read-only and has no side effects. It converts the raw repository output into the
`MonthlyBudgetSummary` Pydantic model. Precision rule: all intermediate arithmetic uses Python
`decimal.Decimal` to avoid float drift when summing multiple cost lines; the final `MonthlyBudgetSummary`
fields are `float` for JSON serialisation compatibility. `pct_of_budget` is computed as
`(combined_total_usd / MONTHLY_BUDGET_USD) * 100`, rounded to two decimal places.
`over_alert_threshold` is `combined_total_usd >= ALERT_THRESHOLD_USD`. `over_budget` is
`combined_total_usd >= MONTHLY_BUDGET_USD`. Both thresholds use `>=` (inclusive) so a spend of
exactly $80.00 triggers the alert and a spend of exactly $100.00 triggers the hard-limit
notification. `billing_month` passed to `summarise` must be the first day of a month; raise
`ValueError` otherwise.

**AC covered**: AC-001 (combined total computed correctly), AC-002 (breakdown structure for the API endpoint), AC-003 (over_alert_threshold and over_budget flags used by TASK-005 and TASK-006)

---

### TASK-005: GET /api/v1/admin/cost-monitor endpoint · S/no-TDD · src/api/routers/admin/cost_monitor.py, src/api/routers/admin/__init__.py

Implement the FastAPI endpoint as specified in Interfaces and Contracts. Requirements:
- Requires `role == "admin"` JWT authentication (use the existing `require_admin` dependency from
  PLAN-F-033 / PLAN-F-030 — do not implement a new auth check).
- Computes `billing_month` as the first day of `date.today()`'s year-month (e.g. if today is
  2026-06-15, `billing_month = date(2026, 6, 1)`).
- Calls `MonthlyBudgetMonitor.summarise(billing_month)` with `tenant_id=None` (global view,
  single-tenant MVP).
- Returns the `MonthlyBudgetSummary` serialised to JSON using the standard success envelope:
  `{"data": <MonthlyBudgetSummary>, "meta": null, "error": null}`.
- Register the router in `src/api/routers/admin/__init__.py` under the existing admin prefix.
- The `pct_of_budget` field (0–100+) is the primary signal for the UI visual indicator (AC-002).

**AC covered**: AC-002 (endpoint provides breakdown and visual indicator data to the admin UI)

---

### TASK-006: Celery beat task — daily budget threshold check and admin email · S/no-TDD · src/admin/tasks/check_monthly_budget.py, src/config/celery_app.py

Implement `check_monthly_budget_task` as specified in Interfaces and Contracts. Key behaviour:
- Uses the same `MonthlyBudgetMonitor.summarise` call as TASK-005 (the service is the single
  source of truth for the threshold logic — no duplicated threshold comparisons in the task).
- Threshold evaluation: if `summary.over_budget` is True, log `ERROR` and send admin email with
  subject "StokAI budget HARD LIMIT: $100/month reached — immediate review required" via
  `send_admin_email` (reuse the email helper introduced in PLAN-F-030 or equivalent). If
  `summary.over_alert_threshold and not summary.over_budget`, log `WARNING` and send admin email
  with subject "StokAI budget alert: 80% of $100/month used ($X.XX spent)". If neither, log
  `INFO` with `combined_total_usd`.
- Both email bodies include the full cost breakdown (AI by model, infra by category) from the
  summary, formatted as plain text.
- The task uses `max_retries=3` with exponential backoff; if SendGrid is unavailable, the
  structured log is the fallback (never suppress the log on email failure).
- Add the task to the Celery beat schedule in `src/config/celery_app.py`:
  `"check-monthly-budget": {"task": "admin.check_monthly_budget", "schedule": crontab(hour=9, minute=0)}`.
- The task is idempotent — running it multiple times on the same day produces at most one alert
  email per day (use a Redis key `budget_alert_sent:{YYYY-MM}` with a 25-hour TTL as a
  deduplication guard; if the key exists, skip the email but still log).

**AC covered**: AC-003 (alert when spend reaches 80%; hard-limit notification when spend reaches 100%)

---

### TASK-007: Admin UI — cost monitor screen wiring (frontend) · S/no-TDD · src/frontend/admin/CostMonitor.tsx (or equivalent React component path)

Wire the `GET /api/v1/admin/cost-monitor` response into the Admin System Operations panel. The
component must:
- Display a progress bar or gauge showing `pct_of_budget` (0–100+) against the $100 threshold.
  Use green below 80%, amber at 80–99%, red at 100%+.
- Display two tables side by side: "AI Costs by Model" (columns: Model, Cost USD, Call Count)
  and "Infrastructure Costs" (columns: Category, Description, Cost USD).
- Show the combined total prominently with the current-month billing date range (e.g.
  "June 2026 total: $47.32 / $100.00").
- Fetch via TanStack Query with a 5-minute stale time (cost data does not need real-time
  updates).
- The component is placed under the existing "System Operations" admin section (ARCHITECTURE.md
  §11 Admin Panel), consistent with the cost monitor spec in ARCHITECTURE.md §11.
- Requires no new auth — the admin layout already enforces `role == "admin"`.

**AC covered**: AC-002 (visual indicator showing current month spend vs $100 threshold; breakdown by model and infra category)

---

## Acceptance Criteria Coverage

- AC-001: Given 30 days of production operation at expected MVP load, the total combined AI + infrastructure cost is documented as < $100 → TASK-004 (`MonthlyBudgetMonitor` computes combined total), TASK-005 (endpoint exposes it), TASK-006 (daily task verifies and alerts if approaching or over)
- AC-002: Given the admin cost monitor, it displays a breakdown of AI costs by model (Haiku/Sonnet/Opus/OpenAI embedding) and infrastructure costs, with a visual indicator showing current month spend vs $100 threshold → TASK-003 (AI cost by model query), TASK-001 (infra cost table), TASK-002 (infra cost repo), TASK-004 (summary aggregation), TASK-005 (API endpoint), TASK-007 (frontend component with visual indicator)
- AC-003: Given total spend reaches 80% of $100/month ($80), the admin receives an alert notification → TASK-004 (`over_alert_threshold` flag), TASK-006 (Celery beat task sends email and logs at WARNING/ERROR; deduplication guard prevents repeat sends)

## Acceptance Notes

AC-001 requires that the monthly total documented in the cost monitor after 30 days of real MVP
production traffic is below $100. The automated test suite (no TDD required for this complexity-S
plan) cannot verify this — it is verified by reading the `GET /api/v1/admin/cost-monitor` response
after the first full billing month of production operation. The admin should screenshot or export
the summary for the audit record. Infrastructure costs must be entered manually into the
`infrastructure_cost` table by the admin at the end of each billing period; the monitor cannot
auto-fetch cloud billing data.

## Risks and Notes

- **infrastructure_cost is manually entered**: There is no integration with a cloud billing API
  (Azure Cost Management, etc.). The admin must enter hosting costs for each billing month. A
  missing or delayed entry will cause `infra_total_usd` to understate the real total, which could
  mask a budget breach. Add a note in the admin UI reminding operators to update infrastructure
  costs by the 5th of each month.

- **cost_record model column name uncertainty**: TASK-003 references `model_id` as the grouping
  key. PLAN-F-030 defines the `cost_record` table schema. If PLAN-F-030 uses `workflow_type`
  rather than `model_id` as the primary cost dimension, TASK-003 must adapt its grouping key
  accordingly. The executor must read PLAN-F-030 TASK definitions before implementing TASK-003.

- **Email deduplication for TASK-006**: The Redis key `budget_alert_sent:{YYYY-MM}` uses a 25-hour
  TTL. If the daily task runs at 09:00 and the TTL expires before the next day's run (unlikely
  with 25h), a second alert email could be sent in the same month. This is acceptable for MVP —
  the email is informational, not a shutdown signal.

- **Dependency on PLAN-F-030 cost monitor skeleton**: TASK-005 relies on the `require_admin`
  dependency and the `send_admin_email` helper introduced in PLAN-F-030. If PLAN-F-030 has not
  yet been executed, TASK-005 and TASK-006 will fail at import time. PLAN-N-005 must be
  scheduled after PLAN-F-030 in the execution wave (Wave 4 per the plans-index, which correctly
  places this plan after PLAN-F-030 in Wave 2).

- **Single-tenant scope**: All repository queries pass `tenant_id=None` for the global view. When
  multi-tenancy is activated (post-MVP), `MonthlyBudgetMonitor` will need to aggregate per-tenant
  and the endpoint will need a `tenant_id` query parameter or path segment. The interface is
  designed to accept `tenant_id` already, so the change will be additive.

- **Frontend path uncertainty**: TASK-007 references `src/frontend/admin/CostMonitor.tsx` as an
  illustrative path. The actual frontend directory structure is established by PLAN-F-028 (Admin
  Data Source Management) and PLAN-F-030. The executor must align the file path with the
  convention already in place rather than creating a new directory.
