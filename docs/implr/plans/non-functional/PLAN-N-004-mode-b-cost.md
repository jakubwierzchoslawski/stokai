---
plan_id: PLAN-N-004
slug: mode-b-cost
title: Mode B Per-Report Cost Ceiling and User Budget
linked_requirement: REQ-N-004
type: non-functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-006, reason: "Morning Brief Workflow defines WorkflowState.cost_usd, CostGuard, and cost_ceiling_usd workflow config; this plan extends that pattern to all five workflows and adds per-user daily budget enforcement" }
  - { id: PLAN-F-011, reason: "ExecutionLimiter enforces per-agent cost_ceiling_usd; this plan builds the workflow-level and per-user-daily tiers above it, and tests the full three-tier stack end-to-end" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-004 — Mode B Per-Report Cost Ceiling and User Budget

## Linked Requirement
**REQ-N-004** — Mode B Per-Report Cost Ceiling and User Budget
Status: approved | Jira: —

## Objective

Implement the per-workflow cost ceiling and per-user daily budget enforcement mechanism for all
five Mode B deliberative workflows. Each workflow type carries a hard cost ceiling enforced at
runtime by `WorkflowCostGuard`: Watchlist Scan ($1.00), On-Demand Analysis ($1.50), Morning
Brief ($2.00), Earnings Risk Brief ($1.50), and Event Deep-Dive ($2.00). When a workflow's
running cost reaches its ceiling mid-execution, the run is immediately terminated with
`WorkflowBudgetExceededError`, partial results are stored with `cost_limited=true` on the
`workflow_run` row, and the admin cost monitor is notified. Separately, each user's daily AI
spend is tracked in a `user_daily_cost` accumulator backed by the existing `cost_record` table
(PLAN-F-030). A `UserBudgetEnforcer` checks this accumulator before every workflow dispatch: it
sends an alert when the user's spend reaches `daily_alert_threshold_pct` (default 80%) of
`daily_budget_usd`, and blocks further workflow dispatch once `daily_hard_stop_pct` (default
100%) is reached. Budget config is stored in `user.settings JSONB` and loaded at dispatch time
by the Celery task layer. After each workflow run completes (or is terminated), the run's
`cost_usd` is written to `cost_record` so the admin cost monitor can surface it. The plan
extends `src/ai/workflows/base_workflow.py` (introduced in PLAN-F-030) and aligns with the
three-tier cost governance hierarchy described in ARCHITECTURE.md §12.6.

## Architecture Context

This plan operates at the intersection of Layer 4 (Processing — `src/ai/`) and Layer 3
(Storage — `src/storage/`) with a narrow touch on the Celery dispatch layer.

- **ARCHITECTURE.md §12.6 — Cost Governance**: Three enforcement tiers. Tier 1 (per-agent
  `cost_ceiling_usd`) is implemented in PLAN-F-011 (`ExecutionLimiter`). Tier 2 (per-workflow
  ceiling) is partially sketched in PLAN-F-006 (`CostGuard` for Morning Brief) and PLAN-F-008
  (`WorkflowCostGuard` for Watchlist Scan). This plan elevates those per-workflow implementations
  into a shared `WorkflowCostGuard` in `src/ai/cost/` and ensures the pattern covers all five
  workflows. Tier 3 (per-user daily hard stop) is new work introduced entirely by this plan.

- **ARCHITECTURE.md §7.1 — LangGraph Runtime**: `WorkflowState.cost_usd` accumulates the
  spend of every agent invocation. Each node calls `WorkflowCostGuard.check_and_accumulate`
  after the agent completes. On ceiling breach, the guard raises `WorkflowBudgetExceededError`,
  which is caught by the graph's error handler and routes to the terminal `cost_exceeded` node.

- **ARCHITECTURE.md §10 — Data Model**: `workflow_run.cost_usd` is the per-run accumulator
  (already defined). This plan adds `workflow_run.cost_limited BOOLEAN DEFAULT FALSE` via
  migration. `cost_record` (introduced by PLAN-F-030) receives one insert per completed (or
  terminated) workflow run. `user.settings JSONB` already stores anti-fatigue fields; this plan
  adds `daily_budget_usd`, `daily_alert_threshold_pct`, and `daily_hard_stop_pct` keys to the
  same JSONB column — no schema migration required.

- **ARCHITECTURE.md §12.6 — Per-user daily enforcement**: The hard stop is enforced at Celery
  task dispatch time, not inside the LangGraph graph. `UserBudgetEnforcer.check_and_alert` is
  called by every Mode B Celery task before invoking the workflow. This is consistent with
  §12.6 which states "Budget hard-stop enforced at Celery task dispatch time, not just within
  the workflow graph."

- **ARCHITECTURE.md §5 — Backend Module Map**: `src/ai/` owns workflow runtime; `src/storage/`
  owns repositories. `UserBudgetEnforcer` lives in `src/ai/cost/` and depends on
  `ICostRecordRepository` (from PLAN-F-030) and `IUserRepository` (from existing storage module)
  — no layer skipping.

## Component Design

### New Components

```
src/ai/cost/
  __init__.py
  workflow_cost_guard.py     — WorkflowCostGuard: per-workflow ceiling enforcement (shared
                               across all five workflows; replaces per-workflow ad-hoc guards
                               in PLAN-F-006 and PLAN-F-008)
  user_budget_enforcer.py    — UserBudgetEnforcer: per-user daily budget check and alert
  errors.py                  — WorkflowBudgetExceededError, UserDailyBudgetExceededError,
                               BudgetAlertEvent (dataclass for structured logging)
  cost_config.py             — WorkflowCeilings (typed constants), BudgetDefaults

src/ai/workflows/
  base_workflow.py           — Modified (see Modified Components): adds UserBudgetEnforcer
                               call before graph.ainvoke(); adds cost_record insert after
                               graph completes or raises

tests/unit/ai/cost/
  test_workflow_cost_guard.py
  test_user_budget_enforcer.py
  test_cost_config.py

tests/integration/
  test_mode_b_cost_enforcement.py  — Integration tests: ceiling breach, daily hard stop,
                                     daily alert, 50-run cost distribution
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/workflows/base_workflow.py` | Add `UserBudgetEnforcer.check_and_alert(user_id, tenant_id)` call at the start of every Mode B Celery task dispatch; add `cost_record` insert in the `finally` block after each workflow run | Per-user daily hard stop (§12.6) and cost-record telemetry |
| `src/storage/repositories/cost_record_repo.py` | Add `daily_total_for_user(user_id, tenant_id, date) -> float` method to `ICostRecordRepository` | `UserBudgetEnforcer` needs per-user daily aggregate, not just per-tenant monthly aggregate |
| `alembic/versions/` | New migration: add `cost_limited BOOLEAN NOT NULL DEFAULT FALSE` column to `workflow_run` table | Flags runs that were terminated mid-execution due to ceiling breach |
| `agents/morning_brief_workflow.yaml` | Verify `cost_ceiling_usd: 2.00` is present (PLAN-F-006 introduces it; this plan asserts the contract) | Canonical source of ceiling value; `WorkflowCostGuard` reads it |
| `agents/watchlist_scan_workflow.yaml` | Add `cost_ceiling_usd: 1.00` | Ceiling for Watchlist Scan |
| `agents/on_demand_workflow.yaml` | Add `cost_ceiling_usd: 1.50` | Ceiling for On-Demand Analysis |
| `agents/earnings_brief_workflow.yaml` | Add `cost_ceiling_usd: 1.50` | Ceiling for Earnings Risk Brief |
| `agents/event_deep_dive_workflow.yaml` | Add `cost_ceiling_usd: 2.00` | Ceiling for Event Deep-Dive |

### Interfaces and Contracts

```python
# src/ai/cost/errors.py

from dataclasses import dataclass
from uuid import UUID

class WorkflowBudgetExceededError(Exception):
    """Raised by WorkflowCostGuard when accumulated cost reaches the workflow ceiling."""
    def __init__(
        self,
        workflow_type: str,
        ceiling_usd: float,
        accumulated_usd: float,
        workflow_id: UUID,
    ) -> None:
        self.workflow_type = workflow_type
        self.ceiling_usd = ceiling_usd
        self.accumulated_usd = accumulated_usd
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow {workflow_type!r} (id={workflow_id}) exceeded cost ceiling "
            f"${ceiling_usd:.4f}: accumulated=${accumulated_usd:.4f}"
        )

class UserDailyBudgetExceededError(Exception):
    """Raised by UserBudgetEnforcer when user has hit daily_hard_stop_pct."""
    def __init__(self, user_id: UUID, daily_budget_usd: float, spent_today_usd: float) -> None:
        self.user_id = user_id
        self.daily_budget_usd = daily_budget_usd
        self.spent_today_usd = spent_today_usd
        super().__init__(
            f"User {user_id} daily budget hard stop: "
            f"spent=${spent_today_usd:.4f} >= budget=${daily_budget_usd:.4f}"
        )

@dataclass
class BudgetAlertEvent:
    """Structured log payload for budget alert at daily_alert_threshold_pct."""
    user_id: UUID
    tenant_id: UUID
    spent_today_usd: float
    daily_budget_usd: float
    pct_used: float
    alert_threshold_pct: float
    workflow_type: str
```

```python
# src/ai/cost/cost_config.py

from dataclasses import dataclass

@dataclass(frozen=True)
class WorkflowCeilings:
    """Hard cost ceilings per workflow type, in USD.
    Source of truth: workflow YAML files. These constants are defaults used
    when a YAML ceiling is not provided (startup validation should prevent this)."""
    WATCHLIST_SCAN: float = 1.00
    ON_DEMAND_ANALYSIS: float = 1.50
    MORNING_BRIEF: float = 2.00
    EARNINGS_RISK_BRIEF: float = 1.50
    EVENT_DEEP_DIVE: float = 2.00

@dataclass(frozen=True)
class BudgetDefaults:
    """Default per-user daily budget configuration values."""
    DAILY_BUDGET_USD: float = 10.00       # sensible MVP default; overridden by user.settings
    DAILY_ALERT_THRESHOLD_PCT: float = 80.0
    DAILY_HARD_STOP_PCT: float = 100.0
```

```python
# src/ai/cost/workflow_cost_guard.py

from decimal import Decimal
from uuid import UUID
from src.ai.cost.errors import WorkflowBudgetExceededError

class WorkflowCostGuard:
    """
    Enforces the per-workflow cost ceiling.
    Uses Decimal internally to avoid float drift across 6-7 agent invocations.

    Usage inside any AgentNode wrapper:
        guard.check_and_accumulate(state, agent_cost_usd)
    """

    def __init__(self, workflow_type: str, ceiling_usd: float, workflow_id: UUID) -> None:
        self._workflow_type = workflow_type
        self._ceiling = Decimal(str(ceiling_usd))
        self._workflow_id = workflow_id

    def check_and_accumulate(self, state: "WorkflowState", agent_cost_usd: float) -> None:
        """
        Adds agent_cost_usd to state.cost_usd (as Decimal), then checks against ceiling.
        Raises WorkflowBudgetExceededError immediately if ceiling is reached or exceeded.
        At 80% of ceiling: logs WARNING with structured fields.
        Must be called after every AgentNode completes.
        """
        ...

    @property
    def ceiling_usd(self) -> float:
        return float(self._ceiling)
```

```python
# src/ai/cost/user_budget_enforcer.py

from datetime import date
from uuid import UUID
import logging
from src.ai.cost.errors import (
    UserDailyBudgetExceededError,
    BudgetAlertEvent,
)
from src.storage.repositories.cost_record_repo import ICostRecordRepository
from src.storage.repositories.user_repo import IUserRepository

logger = logging.getLogger(__name__)

class UserBudgetEnforcer:
    """
    Checks per-user daily AI cost budget before dispatching a Mode B workflow.
    Configuration is read from user.settings JSONB:
      - daily_budget_usd          (float, default BudgetDefaults.DAILY_BUDGET_USD)
      - daily_alert_threshold_pct (float, default 80.0)
      - daily_hard_stop_pct       (float, default 100.0)

    Called at Celery task dispatch time (ARCHITECTURE §12.6).
    """

    def __init__(
        self,
        cost_record_repo: ICostRecordRepository,
        user_repo: IUserRepository,
    ) -> None:
        self._cost_repo = cost_record_repo
        self._user_repo = user_repo

    async def check_and_alert(
        self,
        user_id: UUID,
        tenant_id: UUID,
        workflow_type: str,
    ) -> None:
        """
        1. Loads user.settings to read daily_budget_usd, thresholds.
        2. Reads daily_total_for_user(user_id, tenant_id, today) from cost_record.
        3. If pct_used >= daily_hard_stop_pct: raises UserDailyBudgetExceededError.
        4. If pct_used >= daily_alert_threshold_pct: logs BudgetAlertEvent at WARNING level.
        5. Otherwise: returns None (dispatch is allowed).
        """
        ...
```

## Implementation Tasks

### TASK-001: DB migration — add cost_limited to workflow_run · S/no-TDD · alembic/versions/XXXX_add_workflow_run_cost_limited.py, src/storage/models/workflow_run.py

Write an Alembic migration that adds `cost_limited BOOLEAN NOT NULL DEFAULT FALSE` to the
`workflow_run` table. Update the `WorkflowRun` SQLAlchemy ORM model with the new column.
This flag is set to `True` by the terminal `cost_exceeded` node handler whenever a
`WorkflowBudgetExceededError` is raised mid-run and partial results are stored. The migration
must include a clean `downgrade()` that drops the column. Verify the column does not already
exist (migration must be idempotent for CI re-runs with empty DB).

**AC covered:** AC-001 (partial results stored with `cost_limited=true`)

---

### TASK-002: WorkflowCostGuard — shared per-workflow ceiling enforcer · M/TDD · src/ai/cost/workflow_cost_guard.py, src/ai/cost/errors.py, src/ai/cost/cost_config.py, src/ai/cost/__init__.py, tests/unit/ai/cost/test_workflow_cost_guard.py

Implement `WorkflowCostGuard` as described in Interfaces and Contracts. Key behavior:

- Uses `decimal.Decimal` internally to prevent float accumulation drift.
- After each `check_and_accumulate` call, computes `pct = accumulated / ceiling * 100`.
- At `pct >= 80` (below ceiling): emits a structured `WARNING` log with `workflow_type`,
  `workflow_id`, `accumulated_usd`, `ceiling_usd`, `pct_used`. Only logs on first crossing of
  80% threshold within a single run (uses internal `_warned` flag).
- At `pct >= 100` (ceiling reached): raises `WorkflowBudgetExceededError` before returning.
- Converts `state.cost_usd` (float) to `Decimal` for accumulation; converts back to float
  when writing to state.

Implement `WorkflowCeilings` and `BudgetDefaults` frozen dataclasses in `cost_config.py`.
Implement `WorkflowBudgetExceededError` and `BudgetAlertEvent` in `errors.py`.

**Tests to write first (TDD):**
- `test_guard_allows_cost_below_ceiling()` — accumulated $0.50 against $2.00 ceiling; assert no exception and no warning log
- `test_guard_warns_at_80_pct_threshold()` — accumulated $1.61 against $2.00; assert WARNING logged with correct pct; no exception
- `test_guard_warns_only_once_per_run()` — call twice with cost that crosses 80% on first call; assert WARNING emitted exactly once
- `test_guard_raises_at_ceiling()` — accumulated $2.00 against $2.00; assert `WorkflowBudgetExceededError` raised with correct `ceiling_usd` and `accumulated_usd`
- `test_guard_raises_when_single_agent_exceeds_ceiling()` — single agent call costs $2.50 on a $2.00 ceiling; assert raises immediately
- `test_guard_uses_decimal_for_accumulation()` — 7 calls each adding $0.285714 against $2.00 ceiling; assert no floating-point false positive
- `test_guard_updates_state_cost_usd()` — after `check_and_accumulate(state, 0.10)`, assert `state.cost_usd == prior + 0.10`

**AC covered:** AC-001 (ceiling enforcement), AC-004 (ceiling enforcement for Morning Brief is the prerequisite for mean/max stat tests)

---

### TASK-003: Per-user daily cost query extension on ICostRecordRepository · M/TDD · src/storage/repositories/cost_record_repo.py, tests/unit/storage/test_cost_record_repo.py

Add `daily_total_for_user(user_id: UUID, tenant_id: UUID, target_date: date) -> float` to the
`ICostRecordRepository` abstract interface and implement it on
`PostgresCostRecordRepository`. The query sums `cost_record.cost_usd` for all rows where
`user_id = :user_id AND tenant_id = :tenant_id AND date = :target_date`. If no rows exist,
return `0.0`. This is a read-only method — no side effects.

Also add `insert_for_workflow_run(workflow_run_id: UUID, user_id: UUID, tenant_id: UUID, workflow_type: str, cost_usd: float, target_date: date) -> CostRecord` to insert one `cost_record` row after a workflow run completes (successful or terminated). This consolidates the cost-telemetry write point so every Mode B workflow uses the same code path.

**Tests to write first (TDD):**
- `test_daily_total_for_user_returns_sum_of_rows()` — seed two rows for user A on target date; assert correct sum returned
- `test_daily_total_for_user_excludes_other_users()` — seed rows for user A and user B on same date; assert user A query returns only user A total
- `test_daily_total_for_user_excludes_other_dates()` — seed rows on yesterday and today; query for today; assert only today's sum
- `test_daily_total_for_user_returns_zero_when_no_rows()` — no rows seeded; assert returns 0.0
- `test_insert_for_workflow_run_creates_cost_record()` — call method; assert row present in DB with correct fields
- `test_insert_for_workflow_run_tenant_scoped()` — assert `tenant_id` written on the inserted row

**AC covered:** AC-002 (daily accumulation queried before alert check), AC-003 (daily accumulation queried before hard-stop check)

---

### TASK-004: UserBudgetEnforcer — per-user daily alert and hard stop · M/TDD · src/ai/cost/user_budget_enforcer.py, tests/unit/ai/cost/test_user_budget_enforcer.py

Implement `UserBudgetEnforcer.check_and_alert` as described in Interfaces and Contracts.

Budget config is read from `user.settings` JSONB using the keys `daily_budget_usd`,
`daily_alert_threshold_pct`, `daily_hard_stop_pct`. Missing keys fall back to
`BudgetDefaults` values. `daily_budget_usd` of `0.0` or absent is treated as unconfigured —
the enforcer allows dispatch but logs a `WARNING` that no budget is set.

Alert path (pct >= alert threshold but < hard stop): logs a structured `BudgetAlertEvent` at
`WARNING` level. Does NOT raise. Does NOT send an email directly — the structured log event is
consumed by the admin cost monitor (PLAN-F-030) via log aggregation. The workflow dispatch
continues normally after the warning.

Hard stop path (pct >= hard_stop_pct): raises `UserDailyBudgetExceededError`. The calling
Celery task catches this, writes a `workflow_run` row with `status="budget_hard_stop"`, and
does not invoke the LangGraph graph.

Both thresholds use strict comparison against `spent / budget * 100`: at exactly 100%, the
hard stop fires. At exactly 80% (with default thresholds), the alert fires.

**Tests to write first (TDD):**
- `test_check_allows_dispatch_when_under_alert_threshold()` — spent $7.00, budget $10.00, alert at 80%; assert returns None
- `test_check_logs_alert_at_alert_threshold()` — spent $8.00, budget $10.00, alert at 80%; assert WARNING logged with correct BudgetAlertEvent fields; no exception raised
- `test_check_allows_dispatch_after_alert_threshold()` — same scenario; assert no exception; method returns None
- `test_check_raises_hard_stop_at_100_pct()` — spent $10.00, budget $10.00; assert `UserDailyBudgetExceededError` raised with correct user_id
- `test_check_raises_hard_stop_above_100_pct()` — spent $10.05, budget $10.00; assert raises
- `test_check_allows_when_daily_budget_not_configured()` — user.settings has no `daily_budget_usd`; assert returns None and logs WARNING about unconfigured budget
- `test_check_reads_alert_threshold_from_user_settings()` — user settings sets `daily_alert_threshold_pct: 60`; spent $6.00 of $10.00; assert alert fires at 60% threshold
- `test_check_uses_correct_date_for_daily_total()` — mock `daily_total_for_user` with today's date; verify date passed matches `date.today()`

**AC covered:** AC-002 (alert at threshold, workflow continues), AC-003 (hard stop at 100%, no further dispatch)

---

### TASK-005: base_workflow.py integration — dispatch guard and cost-record write · M/TDD · src/ai/workflows/base_workflow.py, tests/unit/ai/cost/test_base_workflow_cost_integration.py

Extend `src/ai/workflows/base_workflow.py` (introduced in PLAN-F-030) with two new
responsibilities that apply to every Mode B workflow:

**Pre-dispatch guard:** At the entry point of every Mode B Celery task, before
`graph.ainvoke(state)` is called:
```python
await user_budget_enforcer.check_and_alert(user_id, tenant_id, workflow_type)
```
If `UserDailyBudgetExceededError` is raised, the task writes a `workflow_run` row with
`status="budget_hard_stop"`, `cost_usd=0.0`, `cost_limited=False`, and re-raises so the
Celery task exits cleanly without retrying.

**Post-run cost-record write:** In a `finally` block wrapping the `graph.ainvoke` call:
```python
await cost_record_repo.insert_for_workflow_run(
    workflow_run_id=state.workflow_id,
    user_id=state.user_id,
    tenant_id=state.tenant_id,
    workflow_type=state.workflow_type,
    cost_usd=state.cost_usd,
    target_date=date.today(),
)
```
This fires whether the workflow completed normally, was terminated by `WorkflowBudgetExceededError`,
or failed with any other exception. The `cost_usd` at the time of the exception is whatever was
accumulated in state before the raise.

**cost_limited flag write:** When `WorkflowBudgetExceededError` propagates out of
`graph.ainvoke`, the except handler sets `workflow_run.cost_limited = True` and
`workflow_run.status = "cost_exceeded"` before persisting the partial `workflow_run` row.

**Tests to write first (TDD):**
- `test_budget_enforcer_called_before_graph_invoke()` — mock enforcer and graph; assert enforcer.check_and_alert called before graph.ainvoke
- `test_hard_stop_prevents_graph_invoke()` — mock enforcer raises `UserDailyBudgetExceededError`; assert graph.ainvoke never called
- `test_hard_stop_writes_workflow_run_with_budget_hard_stop_status()` — after hard stop, assert workflow_run row has status "budget_hard_stop"
- `test_cost_record_written_on_successful_run()` — mock graph completes with state.cost_usd=1.20; assert cost_record_repo.insert_for_workflow_run called with cost_usd=1.20
- `test_cost_record_written_on_cost_exceeded_error()` — mock graph raises `WorkflowBudgetExceededError` at state.cost_usd=2.01; assert cost_record inserted with cost_usd=2.01
- `test_cost_record_written_on_unexpected_exception()` — mock graph raises generic RuntimeError; assert cost_record still inserted (finally block fires)
- `test_cost_limited_flag_set_on_budget_exceeded()` — `WorkflowBudgetExceededError` raised; assert workflow_run.cost_limited == True; status == "cost_exceeded"
- `test_cost_limited_false_on_normal_completion()` — graph completes normally; assert workflow_run.cost_limited == False

**AC covered:** AC-001 (cost_limited=True written on ceiling breach), AC-002 (cost_record written, enabling daily accumulation for alert check), AC-003 (UserDailyBudgetExceededError prevents dispatch)

---

### TASK-006: Workflow YAML ceiling declarations — all five workflows · S/no-TDD · agents/watchlist_scan_workflow.yaml, agents/on_demand_workflow.yaml, agents/earnings_brief_workflow.yaml, agents/event_deep_dive_workflow.yaml

Ensure `cost_ceiling_usd` is present and correct in the workflow YAML files for all five Mode B
workflows. PLAN-F-006 already writes `agents/morning_brief_workflow.yaml` with
`cost_ceiling_usd: 2.00`. This task writes or extends the remaining four:

```yaml
# agents/watchlist_scan_workflow.yaml  (extends PLAN-F-008)
cost_ceiling_usd: 1.00

# agents/on_demand_workflow.yaml  (extends PLAN-F-007)
cost_ceiling_usd: 1.50

# agents/earnings_brief_workflow.yaml  (extends PLAN-F-009)
cost_ceiling_usd: 1.50

# agents/event_deep_dive_workflow.yaml  (extends PLAN-F-010)
cost_ceiling_usd: 2.00
```

Each YAML must also include a comment block documenting the per-agent budget allocation that
sums to the workflow ceiling. For example, in `event_deep_dive_workflow.yaml`:
```yaml
# Agent ceiling allocation (must sum ≤ cost_ceiling_usd):
#   exposure_analyst:          0.30  (Sonnet 4.6, parallel per company)
#   event_deep_dive_agent:     0.50  (Opus 4.7)
#   historical_context_agent:  0.60  (Opus 4.7)
#   recommendation_synthesizer: 0.35 (Opus 4.7)
#   narrative_writer:          0.20  (Opus 4.7)
#   evaluate_quality:          0.05  (Opus 4.7 LLM-as-judge)
#   Total allocation:          2.00
```

**AC covered:** enables AC-001 (ceiling values available to WorkflowCostGuard at runtime), AC-004 (Morning Brief ceiling is the prerequisite for the 50-run assertion)

---

### TASK-007: cost_exceeded terminal node and partial-results storage · M/TDD · src/ai/workflows/cost_exceeded_node.py, tests/unit/ai/cost/test_cost_exceeded_node.py

Implement `cost_exceeded_node(state: WorkflowState) -> WorkflowState` as a shared
`DeterministicNode` that all five workflow graphs wire as the handler for
`WorkflowBudgetExceededError`. Each workflow graph registers a conditional edge from every
AgentNode: if `WorkflowBudgetExceededError` is caught by the graph's exception hook, route to
`cost_exceeded_node`. The node:

1. Sets `state.cost_limited = True` (new field added to `WorkflowState`).
2. Sets `state.workflow_status = "cost_exceeded"`.
3. Persists whatever partial `state.recommendations` and `state.report` exist (may be empty
   lists / None) to the `workflow_run.final_state` JSONB column.
4. Logs a structured `ERROR` event with `workflow_id`, `workflow_type`, `cost_usd`,
   `ceiling_usd`, `partial_results_count`.
5. Does NOT dispatch any email or alert to the end user.

Update `WorkflowState` base model in `src/ai/schemas/workflow_state.py` to add
`cost_limited: bool = False` field. This change propagates to all five workflow state subclasses.

**Tests to write first (TDD):**
- `test_cost_exceeded_node_sets_cost_limited_true()` — mock state with recommendations; assert state.cost_limited == True after node
- `test_cost_exceeded_node_sets_status_cost_exceeded()` — assert state.workflow_status == "cost_exceeded"
- `test_cost_exceeded_node_preserves_partial_recommendations()` — state has 2 recommendations before node; assert they are retained in state after node (not cleared)
- `test_cost_exceeded_node_does_not_dispatch_email()` — mock sendgrid; assert never called
- `test_cost_exceeded_node_logs_structured_error()` — mock logger; assert ERROR logged with workflow_id, cost_usd, ceiling_usd

**AC covered:** AC-001 (cost_limited=True, partial results stored, admin notified via structured log)

---

### TASK-008: Integration tests — ceiling breach, daily alert, daily hard stop, 50-run cost stat · L/TDD · tests/integration/test_mode_b_cost_enforcement.py

Write integration tests against a real PostgreSQL test database with mocked LLM (Anthropic)
and mocked SendGrid. Each test uses the full workflow stack (LangGraph + Celery task simulation
via direct async call).

**Scenario 1 — Workflow ceiling breach mid-execution:**
Seed an Event Deep-Dive workflow run. Mock agent invocations so the third agent call pushes
`state.cost_usd` over $2.00. Assert:
- `WorkflowBudgetExceededError` is caught.
- `workflow_run.cost_limited == True`.
- `workflow_run.status == "cost_exceeded"`.
- `cost_record` row inserted with the partial `cost_usd`.
- No email dispatched.

**Scenario 2 — Daily alert threshold without hard stop:**
Seed `cost_record` rows totalling 80% of `daily_budget_usd` for a user today. Dispatch a new
Morning Brief workflow for that user. Assert:
- `BudgetAlertEvent` WARNING is logged.
- Workflow dispatch proceeds (graph.ainvoke is called).
- Run completes normally.

**Scenario 3 — Daily hard stop:**
Seed `cost_record` rows totalling 100% of `daily_budget_usd` for a user today. Attempt to
dispatch a Morning Brief workflow for that user. Assert:
- `UserDailyBudgetExceededError` is raised.
- `graph.ainvoke` is never called.
- `workflow_run.status == "budget_hard_stop"`.
- `cost_record` is NOT written (no cost incurred).

**Scenario 4 — 50 Morning Brief runs cost distribution:**
Run the Morning Brief workflow 50 times with varying mocked agent costs drawn from a realistic
distribution. Assert:
- No single run exceeds $2.00 (`max(costs) <= 2.00`).
- Mean cost across all 50 runs is at or below $1.50 (`mean(costs) <= 1.50`).
- All 50 runs produce a `cost_record` row.

**Tests to write first (TDD):**
- `test_workflow_ceiling_breach_sets_cost_limited_flag()`
- `test_workflow_ceiling_breach_no_email_dispatched()`
- `test_workflow_ceiling_breach_cost_record_written()`
- `test_daily_alert_threshold_allows_dispatch()`
- `test_daily_alert_threshold_logs_budget_alert_event()`
- `test_daily_hard_stop_prevents_dispatch()`
- `test_daily_hard_stop_writes_budget_hard_stop_run_status()`
- `test_50_morning_brief_runs_max_cost_under_2_00()`
- `test_50_morning_brief_runs_mean_cost_at_or_below_1_50()`

**AC covered:** AC-001, AC-002, AC-003, AC-004

---

## Acceptance Criteria Coverage

- AC-001: Event Deep-Dive reaches $2.00 → workflow terminated, cost_limited=True, partial results stored, admin notified → TASK-002 (WorkflowCostGuard ceiling raise), TASK-005 (cost_limited flag on workflow_run), TASK-007 (cost_exceeded_node, partial results, structured log), TASK-008 (Scenario 1 integration test)
- AC-002: User daily spend reaches daily_alert_threshold_pct → BudgetAlertEvent WARNING logged; workflow continues → TASK-004 (UserBudgetEnforcer alert path), TASK-005 (pre-dispatch check in base_workflow), TASK-008 (Scenario 2 integration test)
- AC-003: User daily spend reaches daily_hard_stop_pct → no further workflow dispatched → TASK-004 (UserDailyBudgetExceededError raised), TASK-005 (hard-stop handled in base_workflow), TASK-008 (Scenario 3 integration test)
- AC-004: 50 consecutive Morning Brief runs max ≤ $2.00, mean ≤ $1.50 → TASK-002 (ceiling enforced), TASK-006 (YAML ceiling values), TASK-008 (Scenario 4 — 50-run distribution test)

## Acceptance Notes

AC-004 is a statistical assertion over 50 runs. The integration test (TASK-008 Scenario 4)
uses mocked LLM calls with costs drawn from a fixed random seed to ensure reproducibility in
CI. The seed and distribution parameters must be documented in the test module docstring. A
real-traffic cost report from Langfuse is required for production verification of the mean ≤
$1.50 target; the integration test is a necessary but not sufficient gate.

## Risks and Notes

- **Float accumulation drift:** Seven agent invocations per Morning Brief run, each adding a
  float, can accumulate IEEE-754 rounding error. `WorkflowCostGuard` uses `decimal.Decimal`
  internally (TASK-002). `state.cost_usd` remains a `float` for JSON/Pydantic compatibility;
  conversion happens only at the comparison boundary inside the guard.

- **WorkflowCostGuard vs. ExecutionLimiter overlap:** `ExecutionLimiter` (PLAN-F-011) enforces
  `cost_ceiling_usd` at the per-agent level. `WorkflowCostGuard` enforces the aggregate ceiling
  at the per-workflow level. Both can fire independently. If a per-agent ceiling is hit first,
  `LimitExceededError` routes the workflow to HIL (per PLAN-F-011 design). If the workflow
  aggregate ceiling is hit, `WorkflowBudgetExceededError` routes to the `cost_exceeded` terminal
  node. These are complementary, not redundant. The agent YAML ceilings must be set such that
  their sum does not exceed the workflow ceiling — the budget allocation comments in TASK-006
  make this constraint explicit.

- **cost_record timing:** The `finally` block in `base_workflow.py` (TASK-005) inserts the
  cost_record after every run regardless of outcome. If the process is killed (SIGKILL) between
  the graph completing and the finally block executing, the cost_record will be missing. This is
  acceptable for MVP — the `workflow_run.cost_usd` field still carries the value for post-hoc
  reconciliation.

- **daily_budget_usd not in user schema migration:** `daily_budget_usd`,
  `daily_alert_threshold_pct`, and `daily_hard_stop_pct` are stored as JSONB keys in the
  existing `user.settings` column — no schema migration is required. The `UserBudgetEnforcer`
  must gracefully handle absent keys (fallback to `BudgetDefaults`). A follow-up task in
  PLAN-F-033 (User Auth) should seed these keys when a new user is created.

- **Admin notification for ceiling breach:** AC-001 requires the admin to be notified when a
  workflow is terminated due to cost ceiling breach. This plan delivers notification via
  structured `ERROR` log in `cost_exceeded_node` (TASK-007). The admin cost monitor (PLAN-F-030)
  reads from `cost_record` and `workflow_run` tables — it will surface `cost_limited=True` runs
  in its dashboard. A real-time push notification to the admin is out of scope for this plan;
  if required, it should be added to PLAN-F-030.

- **UserBudgetEnforcer and alert fan-out:** The alert at `daily_alert_threshold_pct` is a
  structured log event (not an email) in this plan. If email alerting to admins is required, it
  must be added to the `BudgetAlertEvent` handler in PLAN-F-030 or a dedicated alerting task.
  This avoids coupling the dispatch path to SendGrid.
