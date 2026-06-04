---
plan_id: PLAN-N-002
slug: mode-b-latency
title: Mode B Workflow Latency Enforcement
linked_requirement: REQ-N-002
type: non-functional
status: done
executed_at: 2026-06-04T00:00:00Z
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-006, reason: "Morning Brief workflow Celery task and LangGraph graph must exist before timeout config and enforcement can be layered on" }
  - { id: PLAN-F-007, reason: "On-Demand workflow Celery task and LangGraph graph must exist before timeout config and enforcement can be layered on" }
  - { id: PLAN-F-008, reason: "Watchlist Scan workflow Celery task must exist before timeout enforcement is applied" }
  - { id: PLAN-F-009, reason: "Earnings Risk Brief workflow Celery task must exist before timeout enforcement is applied" }
  - { id: PLAN-F-010, reason: "Event Deep-Dive workflow Celery task must exist before timeout enforcement is applied" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-002 — Mode B Workflow Latency Enforcement

## Linked Requirement
**REQ-N-002** — Mode B Workflow Latency
Status: approved | Jira:

## Objective

Add hard latency limits to all five Mode B deliberative workflows by introducing a shared `WorkflowTimeoutConfig` registry and a `WorkflowSoftTimeoutGuard` that enforces Celery `soft_time_limit` and `time_limit` parameters across Morning Brief (10 min), On-Demand Analysis (6 min), Watchlist Scan (8 min), Earnings Risk Brief (10 min), and Event Deep-Dive (15 min). When the soft limit is reached, Celery raises `SoftTimeLimitExceeded` inside the running task: the guard intercepts it, flushes the current `WorkflowState` as `status=TIMEOUT` and `partial_result=True` to the `workflow_run` table, and writes a structured timeout event to the admin AI audit log within 60 seconds. The hard (`time_limit`) boundary sends SIGKILL as the final safety net. Automated latency tests verify p95 targets using an injectable fake clock, and a Langfuse score monitor alerts operators when the p95 drifts above the target threshold.

## Architecture Context

This plan sits entirely in Layer 4 (Processing — Mode B). It touches the Celery task layer of each workflow (Architecture §7.1, §10 Celery Configuration) and the `workflow_run` table (Architecture §10 Data Model). No LangGraph node logic is modified; timeout enforcement operates at the Celery task envelope that wraps each graph invocation.

Key architecture references:

- **§7.1 LangGraph Runtime**: All five Mode B workflows run as LangGraph StateGraph instances inside Celery tasks. The `WorkflowState` Pydantic model carries `status` and `cost_usd`; this plan adds `timeout_at: datetime | None` and `partial_result: bool` to that model.
- **§10 Celery Configuration** (referenced in architecture context supplied with the requirement): `soft_time_limit` raises `SoftTimeLimitExceeded` giving the task a grace window to store partial results; `time_limit` sends SIGKILL as an absolute ceiling. This plan applies both parameters consistently across all five workflow tasks.
- **§10 Data Model — `workflow_run`**: Gains `timeout_at TIMESTAMPTZ NULL` and `partial_result BOOL NOT NULL DEFAULT FALSE` columns via an Alembic migration.
- **§12.4 Observability**: Every timeout is written as a structured Langfuse score on the workflow trace, allowing the admin AI audit console (PLAN-F-029) to surface timeout events via its existing `workflow_run`-backed query.
- **§12.6 Cost Governance**: The per-workflow `cost_ceiling_usd` (already enforced by `CostCeilingGuard` from PLAN-F-007) is complementary; this plan adds the time dimension of governance.

The five Celery tasks live at:
- `src/ai/tasks/morning_brief_task.py` (PLAN-F-006)
- `src/ai/workflows/on_demand/tasks.py` (PLAN-F-007)
- `src/ai/workflows/watchlist_scan/tasks.py` (PLAN-F-008)
- `src/ai/workflows/earnings_brief/tasks.py` (PLAN-F-009)
- `src/ai/workflows/event_deep_dive/tasks.py` (PLAN-F-010)

This plan introduces one new shared module (`src/ai/workflows/timeout_guard.py`) and modifies those five task files plus `src/ai/workflows/state.py` and the `workflow_run` DB schema.

## Component Design

### New Components

```
src/ai/workflows/
  timeout_guard.py
    WorkflowTimeoutConfig   — dataclass: workflow_type, soft_limit_seconds,
                              hard_limit_seconds, target_seconds_p95
    WORKFLOW_TIMEOUT_CONFIGS — dict[WorkflowType, WorkflowTimeoutConfig]
                              (all five workflows, authoritative from REQ-N-002)
    WorkflowSoftTimeoutGuard — callable context manager wrapping a Celery task body;
                               catches SoftTimeLimitExceeded, flushes partial state,
                               writes timeout event

src/db/migrations/
  XXXX_add_workflow_run_timeout_fields.py
    — Alembic migration: adds timeout_at TIMESTAMPTZ NULL and
      partial_result BOOL NOT NULL DEFAULT FALSE to workflow_run

tests/unit/ai/workflows/
  test_timeout_guard.py      — unit tests for WorkflowSoftTimeoutGuard (all scenarios)
  test_timeout_configs.py    — config completeness and value correctness tests

tests/performance/
  test_mode_b_latency.py     — pytest latency suite using FakeWorkflowClock
  conftest_mode_b.py         — FakeWorkflowClock, synthetic workflow state factories

src/config/
  langfuse_alerts.py         — extended: register_mode_b_latency_alerts() adds one
                               Langfuse score monitor per workflow type
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/workflows/state.py` | Add `timeout_at: datetime \| None = None` and `partial_result: bool = False` fields to `WorkflowState` | Required to persist partial results on timeout (AC-003) |
| `src/ai/tasks/morning_brief_task.py` | Wrap task body with `WorkflowSoftTimeoutGuard`; add `time_limit=600, soft_time_limit=570` to `@celery_app.task(...)` | Apply 10-min hard limit and 9m30s soft limit to Morning Brief |
| `src/ai/workflows/on_demand/tasks.py` | Wrap task body with `WorkflowSoftTimeoutGuard`; confirm `time_limit=360, soft_time_limit=300` (already present from PLAN-F-007, update soft limit to 330s) | Apply 6-min hard limit with 5m30s soft limit to On-Demand |
| `src/ai/workflows/watchlist_scan/tasks.py` | Wrap task body with `WorkflowSoftTimeoutGuard`; add `time_limit=480, soft_time_limit=450` to `@celery_app.task(...)` | Apply 8-min hard limit and 7m30s soft limit to Watchlist Scan |
| `src/ai/workflows/earnings_brief/tasks.py` | Wrap task body with `WorkflowSoftTimeoutGuard`; add `time_limit=600, soft_time_limit=570` to `@celery_app.task(...)` | Apply 10-min hard limit and 9m30s soft limit to Earnings Brief |
| `src/ai/workflows/event_deep_dive/tasks.py` | Wrap task body with `WorkflowSoftTimeoutGuard`; add `time_limit=900, soft_time_limit=870` to `@celery_app.task(...)` | Apply 15-min hard limit and 14m30s soft limit to Event Deep-Dive |
| `src/storage/repositories/workflow_run_repository.py` | Add `save_timeout(workflow_id, partial_state, timeout_at)` method to `IWorkflowRunRepository` and its implementation | Persist partial results and timeout timestamp on SoftTimeLimitExceeded |
| `src/config/langfuse_alerts.py` | Add `register_mode_b_latency_alerts()` to register per-workflow Langfuse score monitors | Production p95 monitoring closes the observability loop |

### Interfaces and Contracts

```python
# src/ai/workflows/timeout_guard.py

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


@dataclass(frozen=True)
class WorkflowTimeoutConfig:
    workflow_type: WorkflowType
    hard_limit_seconds: int    # maps to Celery time_limit
    soft_limit_seconds: int    # maps to Celery soft_time_limit (grace window = hard - soft)
    target_seconds_p95: int    # non-enforced target used by Langfuse alert threshold


# Authoritative timeout values from REQ-N-002.
# All five workflows declared here; no values hardcoded in task files.
WORKFLOW_TIMEOUT_CONFIGS: dict[WorkflowType, WorkflowTimeoutConfig] = {
    WorkflowType.MORNING_BRIEF: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.MORNING_BRIEF,
        hard_limit_seconds=600,    # 10 min
        soft_limit_seconds=570,    # 9 min 30 s — 30 s grace to flush state
        target_seconds_p95=300,    # 5 min p95 target
    ),
    WorkflowType.ON_DEMAND: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.ON_DEMAND,
        hard_limit_seconds=360,    # 6 min
        soft_limit_seconds=330,    # 5 min 30 s
        target_seconds_p95=240,    # 4 min p95 target
    ),
    WorkflowType.WATCHLIST_SCAN: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.WATCHLIST_SCAN,
        hard_limit_seconds=480,    # 8 min
        soft_limit_seconds=450,    # 7 min 30 s
        target_seconds_p95=180,    # 3 min p95 target
    ),
    WorkflowType.EARNINGS_BRIEF: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.EARNINGS_BRIEF,
        hard_limit_seconds=600,    # 10 min
        soft_limit_seconds=570,    # 9 min 30 s
        target_seconds_p95=240,    # 4 min p95 target
    ),
    WorkflowType.EVENT_DEEP_DIVE: WorkflowTimeoutConfig(
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        hard_limit_seconds=900,    # 15 min
        soft_limit_seconds=870,    # 14 min 30 s
        target_seconds_p95=420,    # 7 min p95 target
    ),
}


class WorkflowSoftTimeoutGuard:
    """
    Context manager that wraps a Celery Mode B task body.

    On SoftTimeLimitExceeded:
    1. Sets state.status = WorkflowStatus.TIMEOUT
    2. Sets state.partial_result = True
    3. Sets state.timeout_at = utcnow()
    4. Calls workflow_run_repository.save_timeout(workflow_id, state, timeout_at)
    5. Writes a Langfuse score "workflow_timeout" = 1 on the active trace
    6. Logs a structured ERROR entry (workflow_id, workflow_type, elapsed_seconds)
    7. Does NOT re-raise — the task exits cleanly so Celery marks it done,
       not failed. SIGKILL from hard time_limit is the absolute ceiling.

    Usage in a Celery task body:
        async with WorkflowSoftTimeoutGuard(state, repository, langfuse_client) as guard:
            result = await graph.ainvoke(state, ...)
    """

    def __init__(
        self,
        state: WorkflowState,
        repository: "IWorkflowRunRepository",
        langfuse_client: Any | None,
    ) -> None:
        self._state = state
        self._repository = repository
        self._langfuse = langfuse_client

    async def __aenter__(self) -> "WorkflowSoftTimeoutGuard":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is SoftTimeLimitExceeded:
            await self._handle_soft_timeout()
            return True   # suppress the exception; task exits cleanly
        return False

    async def _handle_soft_timeout(self) -> None:
        timeout_at = datetime.now(timezone.utc)
        self._state.status = WorkflowStatus.TIMEOUT
        self._state.partial_result = True
        self._state.timeout_at = timeout_at
        await self._repository.save_timeout(
            workflow_id=self._state.workflow_id,
            partial_state=self._state,
            timeout_at=timeout_at,
        )
        if self._langfuse and self._state.langfuse_trace_id:
            # Write numeric score "workflow_timeout" = 1 on the trace so
            # the admin AI audit console and Langfuse monitors can surface it.
            self._langfuse.score(
                trace_id=self._state.langfuse_trace_id,
                name="workflow_timeout",
                value=1,
                comment=f"SoftTimeLimitExceeded after soft_limit on {self._state.workflow_type}",
            )
```

```python
# src/storage/repositories/workflow_run_repository.py  (added method signature)

from datetime import datetime
from uuid import UUID
from src.ai.workflows.state import WorkflowState

class IWorkflowRunRepository(Protocol):
    # ... existing methods from PLAN-F-007 TASK-001 ...

    async def save_timeout(
        self,
        workflow_id: UUID,
        partial_state: WorkflowState,
        timeout_at: datetime,
    ) -> None:
        """
        Persists partial results and marks the workflow_run as timed out.
        Sets: status='TIMEOUT', partial_result=True, timeout_at=timeout_at,
              final_state=partial_state.model_dump().
        Must complete within the 30-second grace window (soft_limit to hard_limit).
        """
        ...
```

```python
# src/ai/workflows/state.py  (additions to WorkflowState)

from datetime import datetime

class WorkflowState(BaseModel):
    # ... existing fields from PLAN-F-007 TASK-001 ...
    timeout_at: datetime | None = None       # set on SoftTimeLimitExceeded
    partial_result: bool = False             # True when workflow terminated early
```

```python
# Celery task decoration pattern — applied uniformly to all five workflow tasks:
#
# Morning Brief (hard=600s, soft=570s):
@celery_app.task(
    name="morning_brief.run_for_user",
    time_limit=600,
    soft_time_limit=570,
    max_retries=1,
    acks_late=True,
)
#
# On-Demand (hard=360s, soft=330s):
@shared_task(
    name="ai.on_demand_analysis",
    time_limit=360,
    soft_time_limit=330,
    max_retries=0,
)
#
# Watchlist Scan (hard=480s, soft=450s):
@celery_app.task(
    name="watchlist_scan.run",
    time_limit=480,
    soft_time_limit=450,
    max_retries=1,
    acks_late=True,
)
#
# Earnings Brief (hard=600s, soft=570s):
@celery_app.task(
    name="earnings_brief.run",
    time_limit=600,
    soft_time_limit=570,
    max_retries=1,
    acks_late=True,
)
#
# Event Deep-Dive (hard=900s, soft=870s):
@celery_app.task(
    name="event_deep_dive.run",
    time_limit=900,
    soft_time_limit=870,
    max_retries=1,
    acks_late=True,
)
```

## Implementation Tasks

### TASK-001: WorkflowTimeoutConfig registry and WorkflowState timeout fields · M/TDD · src/ai/workflows/timeout_guard.py, src/ai/workflows/state.py, tests/unit/ai/workflows/test_timeout_configs.py

Define `WorkflowTimeoutConfig` dataclass and the `WORKFLOW_TIMEOUT_CONFIGS` dict with all five workflow types and their hard limit, soft limit, and p95 target values per REQ-N-002. Extend `WorkflowState` with `timeout_at: datetime | None = None` and `partial_result: bool = False`. Validate that the two new fields round-trip through `model_dump_json()` correctly (datetime serialized to ISO-8601 string).

**Tests to write first (TDD):**
- `test_workflow_timeout_configs_covers_all_five_workflow_types()` — assert `len(WORKFLOW_TIMEOUT_CONFIGS) == 5`; assert all `WorkflowType` enum values are present as keys
- `test_morning_brief_hard_limit_is_600s()` — assert `WORKFLOW_TIMEOUT_CONFIGS[WorkflowType.MORNING_BRIEF].hard_limit_seconds == 600`
- `test_on_demand_hard_limit_is_360s()` — assert `hard_limit_seconds == 360`
- `test_watchlist_scan_hard_limit_is_480s()` — assert `hard_limit_seconds == 480`
- `test_earnings_brief_hard_limit_is_600s()` — assert `hard_limit_seconds == 600`
- `test_event_deep_dive_hard_limit_is_900s()` — assert `hard_limit_seconds == 900`
- `test_soft_limits_leave_30s_grace_window()` — for every config: assert `hard_limit_seconds - soft_limit_seconds == 30`
- `test_p95_targets_within_hard_limits()` — for every config: assert `target_seconds_p95 < hard_limit_seconds`
- `test_workflow_state_timeout_at_defaults_none()` — `WorkflowState(...)` with no `timeout_at` has `timeout_at is None`
- `test_workflow_state_partial_result_defaults_false()` — default value is `False`
- `test_workflow_state_timeout_fields_serialize_to_json()` — `state.model_dump_json()` with `timeout_at=datetime.now()` and `partial_result=True` does not raise and produces valid JSON

**AC covered:** AC-003 (timeout config and state fields are prerequisites for all enforcement), AC-001, AC-002, AC-004

---

### TASK-002: workflow_run DB migration — timeout_at and partial_result columns · S/no-TDD · src/db/migrations/XXXX_add_workflow_run_timeout_fields.py

Write an Alembic migration that adds to the `workflow_run` table:
- `timeout_at TIMESTAMPTZ NULL` — populated by `save_timeout()` when `SoftTimeLimitExceeded` fires
- `partial_result BOOLEAN NOT NULL DEFAULT FALSE` — set to `TRUE` on timeout, remains `FALSE` for completed runs

Include a downgrade path that drops both columns. Verify that the migration can be applied cleanly against the existing schema produced by PLAN-F-007 TASK-001.

**AC covered:** enables AC-003 (partial results must be storable before the guard can flush them)

---

### TASK-003: IWorkflowRunRepository.save_timeout and implementation · M/TDD · src/storage/repositories/workflow_run_repository.py, src/storage/repositories/interfaces.py, tests/unit/ai/workflows/test_timeout_guard.py

Add `save_timeout(workflow_id, partial_state, timeout_at)` to the `IWorkflowRunRepository` protocol and implement it in `WorkflowRunRepository`. The implementation must:
1. Update `workflow_run` row: `status='TIMEOUT'`, `partial_result=TRUE`, `timeout_at=timeout_at`, `final_state=partial_state.model_dump()`, `completed_at=timeout_at`.
2. Use an upsert-style approach (UPDATE WHERE workflow_id = ?) so a missing row does not silently swallow the failure.
3. Complete within the 30-second grace window between soft and hard limits — no external API calls, no LLM calls.
4. Enforce `tenant_id` scoping on the UPDATE (Architecture §12.3 multi-tenancy).

**Tests to write first (TDD):**
- `test_save_timeout_sets_status_to_timeout()` — integration: create a workflow_run row with status RUNNING; call `save_timeout`; assert `status == 'TIMEOUT'`
- `test_save_timeout_sets_partial_result_true()` — assert `partial_result == True` after call
- `test_save_timeout_sets_timeout_at()` — assert `timeout_at` column matches the value passed in
- `test_save_timeout_persists_final_state()` — assert `final_state` JSON contains the partial state's `cost_usd` and `tokens_consumed`
- `test_save_timeout_scoped_to_tenant()` — assert UPDATE is issued with `tenant_id` in WHERE clause (via query inspection or IDOR guard test: calling with wrong tenant_id updates no rows)
- `test_save_timeout_on_missing_workflow_run_raises()` — calling with a non-existent `workflow_id` raises `WorkflowRunNotFoundError` rather than silently no-oping

**AC covered:** AC-003 (partial results stored within 60 seconds of termination)

---

### TASK-004: WorkflowSoftTimeoutGuard — SoftTimeLimitExceeded handler · M/TDD · src/ai/workflows/timeout_guard.py, tests/unit/ai/workflows/test_timeout_guard.py

Implement `WorkflowSoftTimeoutGuard` as specified in the Interfaces and Contracts section. Key behaviour:
- `__aexit__` must return `True` (suppress the exception) when `exc_type is SoftTimeLimitExceeded`, so the Celery task exits cleanly as `SUCCESS` rather than `FAILURE`. This ensures the hard SIGKILL limit is not triggered by exception propagation, preserving the partial state already flushed to the DB.
- Langfuse score write must be wrapped in a `try/except Exception` so a Langfuse outage never prevents the partial state from being saved.
- The structured error log entry must include: `workflow_id`, `workflow_type`, `elapsed_seconds` (computed from `state.started_at`), `cost_usd`, `partial_result=True`.

**Tests to write first (TDD):**
- `test_guard_suppresses_soft_time_limit_exceeded()` — raise `SoftTimeLimitExceeded` inside the `async with` block; assert the exception does not propagate
- `test_guard_sets_state_status_to_timeout()` — after soft timeout fires; assert `state.status == WorkflowStatus.TIMEOUT`
- `test_guard_sets_partial_result_true()` — assert `state.partial_result == True`
- `test_guard_sets_timeout_at()` — assert `state.timeout_at` is not None and is a UTC datetime
- `test_guard_calls_save_timeout_on_repository()` — mock repository; assert `save_timeout` called with correct `workflow_id` and `timeout_at`
- `test_guard_writes_langfuse_score_workflow_timeout_equals_1()` — mock Langfuse client; assert `langfuse.score` called with `name="workflow_timeout"`, `value=1`
- `test_guard_does_not_raise_if_langfuse_unavailable()` — langfuse_client is None; assert no exception
- `test_guard_does_not_suppress_other_exceptions()` — raise `ValueError` inside block; assert `ValueError` propagates; `save_timeout` not called
- `test_guard_noop_on_clean_exit()` — no exception inside block; assert `save_timeout` not called, state unchanged

**AC covered:** AC-003 (SoftTimeLimitExceeded handled; partial results stored; Langfuse score written)

---

### TASK-005: Apply WorkflowSoftTimeoutGuard to all five workflow Celery tasks · M/TDD · src/ai/tasks/morning_brief_task.py, src/ai/workflows/on_demand/tasks.py, src/ai/workflows/watchlist_scan/tasks.py, src/ai/workflows/earnings_brief/tasks.py, src/ai/workflows/event_deep_dive/tasks.py, tests/unit/ai/workflows/test_timeout_guard.py

Modify all five Celery task functions to:
1. Declare `time_limit` and `soft_time_limit` from `WORKFLOW_TIMEOUT_CONFIGS` rather than hardcoded integers. Read: `cfg = WORKFLOW_TIMEOUT_CONFIGS[workflow_type]; task.time_limit = cfg.hard_limit_seconds; task.soft_time_limit = cfg.soft_limit_seconds`.
2. Wrap the graph invocation call (`graph.ainvoke(...)`) in `async with WorkflowSoftTimeoutGuard(state, repository, langfuse_client)`.
3. Confirm the On-Demand task already has `time_limit=360` from PLAN-F-007 — update `soft_time_limit` from 300 to 330 to preserve the 30-second grace window.

Each task must import limits exclusively from `WORKFLOW_TIMEOUT_CONFIGS`; no magic numbers in task files.

**Tests to write first (TDD):**
- `test_morning_brief_task_declares_time_limit_600()` — inspect task's `time_limit` attribute; assert == 600
- `test_morning_brief_task_declares_soft_time_limit_570()` — assert == 570
- `test_on_demand_task_declares_time_limit_360()` — assert == 360
- `test_on_demand_task_declares_soft_time_limit_330()` — assert == 330
- `test_watchlist_scan_task_declares_time_limit_480()` — assert == 480
- `test_earnings_brief_task_declares_time_limit_600()` — assert == 600
- `test_event_deep_dive_task_declares_time_limit_900()` — assert == 900
- `test_morning_brief_task_wraps_graph_invoke_with_guard()` — mock `WorkflowSoftTimeoutGuard`; assert it is used as a context manager around `graph.ainvoke`
- `test_on_demand_task_wraps_graph_invoke_with_guard()` — same pattern
- `test_soft_limit_exceeded_in_morning_brief_stores_partial_result()` — inject `SoftTimeLimitExceeded` mid-graph; assert `save_timeout` called; task returns without raising

**AC covered:** AC-001 (Morning Brief hard limit ≤10 min enforced), AC-002 (On-Demand hard limit ≤6 min enforced), AC-003 (partial results stored on termination), AC-004 (Watchlist Scan hard limit ≤8 min enforced)

---

### TASK-006: Automated p95 latency test suite for all five Mode B workflows · M/TDD · tests/performance/test_mode_b_latency.py, tests/performance/conftest_mode_b.py

Create `tests/performance/conftest_mode_b.py` with:
- `FakeWorkflowClock(elapsed_seconds)` — injectable clock that returns a fixed elapsed time so latency tests run in milliseconds, not minutes.
- `build_fake_workflow_state(workflow_type, started_at)` — constructs a minimal `WorkflowState` for each workflow type.
- `FakeWorkflowGraph(target_duration_seconds, raises_at_seconds=None)` — fake LangGraph graph; sleeps `target_duration_seconds` using real `asyncio.sleep` (for integration) or accepts a clock injection for unit testing. If `raises_at_seconds` is set, raises `SoftTimeLimitExceeded` at that point.

Create `tests/performance/test_mode_b_latency.py`:

**Tests to write first (TDD):**
- `test_morning_brief_p95_within_target()` — run 50 fake Morning Brief graphs completing at 4 min 30 s (90% of 5-min target); assert p95 of recorded `elapsed_seconds` ≤ 300 (5 min)
- `test_morning_brief_hard_limit_enforcement()` — inject `SoftTimeLimitExceeded` at 571 s (just past soft limit); assert `state.status == TIMEOUT`; assert `state.partial_result == True`; assert `state.timeout_at` is not None
- `test_on_demand_p95_within_target()` — 50 runs at 3 min 30 s; assert p95 ≤ 240 s (4 min)
- `test_on_demand_hard_limit_enforcement()` — inject timeout at 331 s; assert `status == TIMEOUT`
- `test_watchlist_scan_hard_limit_enforcement()` — inject timeout at 451 s; assert `status == TIMEOUT`; assert `partial_result == True`
- `test_earnings_brief_hard_limit_enforcement()` — inject timeout at 571 s; assert `status == TIMEOUT`
- `test_event_deep_dive_hard_limit_enforcement()` — inject timeout at 871 s; assert `status == TIMEOUT`
- `test_no_run_exceeds_hard_limit_without_termination()` — for each workflow: inject timeout at `soft_limit + 1`; assert the guard intercepts and no run's `elapsed_seconds` surpasses `hard_limit_seconds` (i.e., the task exits before SIGKILL would fire)
- `test_timeout_audit_event_written_within_60s()` — mock repository; assert `save_timeout` is called within 60 s of `SoftTimeLimitExceeded` (verified by checking `timeout_at - started_at` stays within the `soft_limit_seconds + 60` window)

**AC covered:** AC-001 (p95 ≤5 min Morning Brief), AC-002 (p95 ≤4 min On-Demand), AC-003 (partial results stored and audit event written within 60 s), AC-004 (Watchlist Scan hard limit enforced)

---

### TASK-007: Langfuse latency monitors for all five Mode B workflows · S/no-TDD · src/config/langfuse_alerts.py

Extend `src/config/langfuse_alerts.py` with `register_mode_b_latency_alerts(langfuse_client)`. For each of the five workflow types this function upserts a Langfuse numeric score monitor:

| Workflow | Score name | Alert threshold (p95) | Alert headroom |
|----------|------------|----------------------|---------------|
| morning_brief | `morning_brief_duration_ms` | 240 000 ms (4 min) | 1 min before 5-min target |
| on_demand | `on_demand_duration_ms` | 180 000 ms (3 min) | 1 min before 4-min target |
| watchlist_scan | `watchlist_scan_duration_ms` | 120 000 ms (2 min) | 1 min before 3-min target |
| earnings_brief | `earnings_brief_duration_ms` | 180 000 ms (3 min) | 1 min before 4-min target |
| event_deep_dive | `event_deep_dive_duration_ms` | 360 000 ms (6 min) | 1 min before 7-min target |

Each monitor reads the rolling p95 over a 24-hour window and notifies via `LANGFUSE_ALERT_EMAIL` env var (optional). The function is idempotent (safe on every startup). Called from the application startup hook alongside `register_latency_alerts()` from PLAN-N-001.

Each Celery task must write `duration_ms` to the Langfuse trace on completion (both successful and timed-out). In the timeout path, `WorkflowSoftTimeoutGuard._handle_soft_timeout` computes `duration_ms = (timeout_at - state.started_at).total_seconds() * 1000` and writes it to the trace before writing the `workflow_timeout` score.

**AC covered:** AC-001 (production p95 monitoring for Morning Brief), AC-002 (production p95 monitoring for On-Demand), AC-004 (production p95 monitoring for Watchlist Scan)

---

## Acceptance Criteria Coverage

- AC-001: Given 50 consecutive Morning Brief runs, p95 completion time ≤5 minutes; no run exceeds the 10-minute hard limit without being terminated → TASK-001 (600 s config), TASK-002 (schema), TASK-004 (guard), TASK-005 (morning_brief_task), TASK-006 (p95 test), TASK-007 (Langfuse monitor)
- AC-002: Given an On-Demand analysis is triggered, result available within 4 minutes at p95; never longer than 6 minutes before returning a partial or terminated result → TASK-001 (360 s config), TASK-004 (guard), TASK-005 (on_demand task), TASK-006 (p95 test), TASK-007 (Langfuse monitor)
- AC-003: Given any Mode B workflow reaches its hard time limit, Celery task is terminated, partial results stored with a timeout flag, and admin AI audit console records the event within 60 seconds → TASK-001 (WorkflowState fields), TASK-002 (DB migration), TASK-003 (save_timeout), TASK-004 (WorkflowSoftTimeoutGuard), TASK-005 (all five tasks), TASK-006 (audit event timing test)
- AC-004: Given Watchlist Scan runs at 17:30, it completes and dispatches within 8 minutes at p95, ensuring delivery by 18:00 → TASK-001 (480 s config), TASK-004 (guard), TASK-005 (watchlist_scan task), TASK-006 (hard limit test), TASK-007 (Langfuse monitor)

## Acceptance Notes

AC-003 requires the admin AI audit console to "record the event within 60 seconds." This plan satisfies that requirement via the combination of: (1) `WorkflowSoftTimeoutGuard` writing `status=TIMEOUT`, `partial_result=True`, and `timeout_at` to the `workflow_run` table within the 30-second grace window; and (2) the Langfuse `workflow_timeout` score written to the trace. The admin AI audit console (PLAN-F-029) reads from `workflow_run` with `status='TIMEOUT'`; no additional audit table is introduced. The 60-second window is satisfied by the 30-second grace window (soft-to-hard gap) plus the time for the DB write to complete — the DB write is a single UPDATE with no external API calls and must complete within seconds.

The Watchlist Scan delivery-by-18:00 guarantee (AC-004) depends on the workflow starting at 17:30 (cron schedule from PLAN-F-008) and completing within 8 minutes. This plan enforces the 8-minute ceiling; the cron schedule is owned by PLAN-F-008.

## Risks and Notes

- **SoftTimeLimitExceeded and asyncio interaction**: Celery delivers `SoftTimeLimitExceeded` as a Python signal (SIGALRM on Linux). Inside an `asyncio` event loop, signals are dispatched between coroutine steps, not mid-`await`. If a single agent LLM call blocks for longer than the grace window (30 s), the soft limit exception may not fire until the `await` returns, leaving no time to flush state before SIGKILL. Mitigation: each agent YAML already specifies `timeout_seconds: 60` (Architecture §7.1 bounded execution); the maximum single-agent block is therefore 60 s. The 30-second grace window is insufficient if an agent timeout is close to the workflow soft limit. Recommendation: set per-agent `timeout_seconds` ≤ 120 s for all agents used in workflows with soft limits below 300 s (On-Demand), so the guard always has adequate time to run.
- **save_timeout must not call external APIs**: The `WorkflowSoftTimeoutGuard._handle_soft_timeout` path runs inside the 30-second grace window. It must write only to PostgreSQL. The Langfuse score write is a lightweight HTTP call; wrap it in a 5-second `asyncio.wait_for` to prevent it from consuming the entire grace window if the Langfuse server is slow.
- **On-Demand soft_time_limit updated from 300 to 330 s**: PLAN-F-007 TASK-007 specified `soft_time_limit=300` and `time_limit=360`. This plan changes `soft_time_limit` to 330 s to maintain the 30-second grace window. The executor must update PLAN-F-007's task file in TASK-005; no separate migration is needed since `soft_time_limit` is a Celery task attribute, not a DB column.
- **Config centralization**: All five workflow task files must read limits from `WORKFLOW_TIMEOUT_CONFIGS`, not hardcode them. Any future limit change requires editing only `timeout_guard.py`. Enforce via the unit tests in TASK-005 that inspect task attributes against `WORKFLOW_TIMEOUT_CONFIGS`.
- **FakeWorkflowClock in performance tests**: The p95 test suite (TASK-006) uses 50 runs as specified in AC-001. Python's `statistics.quantiles` requires ≥ 2 samples; 50 is sufficient. Use `statistics.quantiles(latencies, n=20)[18]` (the 19th of 20 quantiles = p95) consistently with the approach used in PLAN-N-001 TASK-004.
- **PLAN-F-008, F-009, F-010 dependency**: This plan lists PLAN-F-008, F-009, and F-010 as dependencies in the frontmatter even though those plans do not appear in the dependency list given in the requirement itself (which only lists F-006 and F-007). All five workflow task files must exist before TASK-005 can modify them. If those plans are not yet executed when PLAN-N-002 is dispatched, TASK-005 must be marked blocked until they are.
