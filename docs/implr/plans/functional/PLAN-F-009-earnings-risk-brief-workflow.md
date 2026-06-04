---
plan_id: PLAN-F-009
slug: earnings-risk-brief-workflow
title: Earnings Risk Brief Workflow (Mode B)
linked_requirement: REQ-F-009
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-002, reason: "Earnings Risk Brief must complete end-to-end in ≤4 min; Celery task hard-terminated at 10 min absolute per architectural spec" }
  - { id: REQ-N-004, reason: "Per-brief cost ceiling $1.50; CostCeilingGuard halts workflow if ceiling is reached" }
dependencies:
  - { id: PLAN-F-011, reason: "Earnings Context Agent (Opus 4.7), Historical Context Agent, Recommendation Synthesizer, Narrative Writer must be defined in AgentRegistry before this workflow graph can resolve them" }
  - { id: PLAN-F-024, reason: "Portfolio companies with T+1 earnings are identified via portfolio and position data; IPortfolioRepository and IPositionRepository must exist" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-04T00:00:00Z
---

# PLAN-F-009 — Earnings Risk Brief Workflow (Mode B)

## Linked Requirement
**REQ-F-009** — Earnings Risk Brief Workflow (Mode B)
Status: approved | Jira:

## Objective
Build the complete Workflow 4 — Earnings Risk Brief — as a LangGraph StateGraph running
inside Celery tasks. A daily Celery beat cron at 17:30 identifies all portfolio companies
with earnings events scheduled for the next trading day (T+1) and dispatches one
`earnings_brief_task` per qualifying company. Each task executes a nine-node graph: four
DeterministicNodes (`fetch_company_state`, `fetch_earnings_history`, `fetch_macro_context`,
`fetch_sector_recent_earnings`), four AgentNodes (`Earnings Context Agent` →
`Historical Context Agent` → `Recommendation Synthesizer` → `Narrative Writer`), and a
terminal quality-gate DeterministicNode (`evaluate_quality`) followed by a
confidence-routing branch. The Earnings Context Agent (Opus 4.7) is the primary agent; it
produces a structured scenario tree covering bull, base, and bear scenarios with probability
weights, macro rationale, sector rationale, and historical earnings-surprise analogies. The
Recommendation Synthesizer outputs this scenario tree rather than a single action signal.
Each brief must complete within 4 minutes and cost no more than $1.50; both constraints are
enforced programmatically. Confidence routing follows D9: ≥0.7 auto-delivers the brief;
0.4–0.69 routes to the HIL queue with a hold deadline of 17:45; <0.4 is blocked with an
audit log entry. No workflow is triggered when no portfolio companies have T+1 earnings. A
hard timeout of 10 minutes terminates the workflow and records the event in the admin AI
audit console.

## Architecture Context
This plan operates in Layer 4 (Processing — Mode B) and Layer 5 (Serving — API).
It introduces new files across three backend modules:

- `src/ai/workflows/earnings_brief/` — new sub-package within the `ai` module (Architecture
  §5, §7). Contains the LangGraph StateGraph definition, node implementations, graph builder,
  Celery tasks, and HIL fallback logic.
- `src/api/` — a new FastAPI router (`earnings_brief_router.py`) exposing a status endpoint
  for the frontend briefs reader; no user-triggered creation endpoint (cron-only trigger).
- `src/config/celery_app.py` — registers the new Celery cron task and per-company
  brief task.

The graph uses an `EarningsBriefState` Pydantic model that extends the canonical
`WorkflowState` shape from Architecture §7.1 with earnings-specific fields
(`scenario_tree`, `earnings_history`, `macro_context`, `sector_context`). PostgreSQL
checkpointing (LangGraph `PostgresSaver`) is mandatory for failure recovery, HIL
pause/resume, and replay (Architecture §7.1). The `AgentRegistry` from PLAN-F-011 is
injected at graph construction time; nodes never construct agents themselves.
The `WorkflowStructureValidator` from PLAN-F-011 asserts the `evaluate_quality` →
`narrative_writer` tail invariant at build time (Architecture §7.1). The
`LangfuseInvocationLogger` from PLAN-F-011 decorates every AgentNode call.
The `CostCeilingGuard` (first introduced in PLAN-F-007) is reused from
`src/ai/workflows/cost_guard.py` with a $1.50 ceiling. HIL timing windows follow
Architecture §7.6: review window 14:00–17:45; unreviewed items are held and the user is
notified.

The earnings detection query reads from the `position` table (PLAN-F-024) and an
`earnings_event` table introduced by this plan's migration. The detection cron must be
idempotent: running it twice for the same trading day must not dispatch duplicate briefs
(guarded by a unique constraint on `(company_id, earnings_date)` in a new
`earnings_brief_run` tracking table).

Architecture §7.5 Workflow 4 defines the authoritative node order:
`fetch_company_state` → `fetch_earnings_history` → `fetch_macro_context` →
`fetch_sector_recent_earnings` → `Earnings Context Agent` → `Historical Context Agent` →
`Recommendation Synthesizer` (scenario tree output) → `Narrative Writer` →
`evaluate_quality` → branch.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-002 | Earnings brief ≤4 min end-to-end (p95); 10 min absolute hard limit | `earnings_brief_task` is decorated with `time_limit=600` (10 min hard) and `soft_time_limit=240` (4 min soft). The soft limit fires gracefully, writes `TIMEOUT` status, and records the event in the audit log. Per-agent `timeout_seconds` in agent YAMLs (PLAN-F-011) budget agent time; `ExecutionLimiter` enforces them. |
| REQ-N-004 | Per-brief cost ceiling $1.50; halt if ceiling reached | `CostCeilingGuard.check(state)` is called after every AgentNode. It reads `state.cost_usd` and raises `WorkflowCostLimitError` at $1.50. The error is caught by the graph's error edge, sets `status = COST_LIMIT`, and routes to the end node. |

## Component Design

### New Components
```
Package: src/ai/workflows/earnings_brief/
  ├── __init__.py
  ├── state.py                               — EarningsBriefState Pydantic model
  ├── graph.py                               — build_earnings_brief_graph() → CompiledGraph
  ├── nodes/
  │   ├── __init__.py
  │   ├── fetch_company_state.py             — DeterministicNode: company, portfolio position, scores
  │   ├── fetch_earnings_history.py          — DeterministicNode: past earnings results, surprises
  │   ├── fetch_macro_context.py             — DeterministicNode: FRED macro indicators snapshot
  │   ├── fetch_sector_recent_earnings.py    — DeterministicNode: sector peers' recent earnings
  │   ├── earnings_context_node.py           — AgentNode: Earnings Context Agent (scenario tree)
  │   ├── historical_context_node.py         — AgentNode: Historical Context Agent (analogies)
  │   ├── recommendation_node.py             — AgentNode: Recommendation Synthesizer (scenario tree output)
  │   ├── narrative_writer_node.py           — AgentNode: Narrative Writer (prose brief)
  │   └── evaluate_quality.py               — DeterministicNode: min-confidence + HIL routing
  ├── tasks.py                               — Celery tasks: detect_t1_earnings_task, earnings_brief_task
  └── hil/
      ├── __init__.py
      └── fallback_task.py                   — Celery beat task: 17:45 HIL hold + user notification

DB migration:
  alembic/versions/xxxx_earnings_brief_tables.py
    — earnings_event table
    — earnings_brief_run tracking table (idempotency guard)

src/api/routers/earnings_brief_router.py    — GET /api/v1/earnings-briefs
                                               GET /api/v1/earnings-briefs/{run_id}

Tests:
tests/unit/ai/workflows/earnings_brief/
  test_earnings_brief_state.py
  test_fetch_company_state.py
  test_fetch_earnings_history.py
  test_fetch_macro_context.py
  test_fetch_sector_recent_earnings.py
  test_earnings_context_node.py
  test_historical_context_node.py
  test_recommendation_node.py
  test_narrative_writer_node.py
  test_evaluate_quality.py
  test_earnings_brief_graph.py
  test_earnings_brief_tasks.py
  test_hil_fallback_task.py

tests/integration/ai/
  test_earnings_brief_happy_path.py
  test_earnings_brief_no_earnings_today.py
  test_earnings_brief_cost_limit.py
  test_earnings_brief_confidence_routing.py
  test_earnings_brief_timeout.py

tests/integration/api/
  test_earnings_brief_router.py
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Register `detect_t1_earnings_task` (cron 17:30), `earnings_brief_task`, `earnings_hil_fallback_task` (beat 60s) | Celery must discover new tasks and beat schedules |
| `src/config/settings.py` | Add `EARNINGS_BRIEF_COST_CEILING_USD: float`, `EARNINGS_BRIEF_HIL_DEADLINE_TIME: str`, `EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS: int` | All constraint values come from environment, never hardcoded |
| `src/api/routers/__init__.py` | Register `earnings_brief_router` | Expose brief status endpoints |

### Interfaces and Contracts

The executor must implement these exactly.

```python
# src/ai/workflows/earnings_brief/state.py

from pydantic import BaseModel, Field
from typing import Any
from uuid import UUID
from datetime import date, datetime
from src.ai.workflows.state import WorkflowStatus  # reuse from PLAN-F-007

class EarningsScenario(BaseModel):
    probability: float = Field(ge=0.0, le=1.0)
    rationale: str
    macro_drivers: list[str]
    sector_drivers: list[str]
    implied_price_impact_pct: float | None = None

class ScenarioTree(BaseModel):
    bull: EarningsScenario
    base: EarningsScenario
    bear: EarningsScenario
    analogies: list[dict[str, Any]] = Field(default_factory=list)
    macro_summary: str
    sector_summary: str

class EarningsBriefState(BaseModel):
    workflow_id:          UUID
    workflow_type:        str = "earnings_brief"
    tenant_id:            UUID
    user_id:              UUID
    company_id:           UUID
    earnings_date:        date                            # T+1 earnings date
    started_at:           datetime
    inputs:               dict[str, Any] = Field(default_factory=dict)
    # Populated by DeterministicNodes
    company_state:        dict[str, Any] | None = None
    earnings_history:     list[dict[str, Any]] = Field(default_factory=list)
    macro_context:        dict[str, Any] | None = None
    sector_recent_earnings: list[dict[str, Any]] = Field(default_factory=list)
    # Populated by AgentNodes
    scenario_tree:        ScenarioTree | None = None      # from Earnings Context Agent
    analogies_output:     dict[str, Any] | None = None    # from Historical Context Agent
    recommendation:       dict[str, Any] | None = None    # Recommendation Synthesizer (scenario-tree form)
    report:               dict[str, Any] | None = None    # Narrative Writer prose output
    # Quality and routing
    confidence_scores:    dict[str, float] = Field(default_factory=dict)
    overall_confidence:   float | None = None
    requires_hil:         bool = False
    hil_reason:           str | None = None
    cost_usd:             float = 0.0
    tokens_consumed:      dict[str, int] = Field(default_factory=dict)
    status:               WorkflowStatus = WorkflowStatus.RUNNING
    error_detail:         str | None = None
    langfuse_trace_id:    str | None = None
```

```python
# src/ai/workflows/earnings_brief/graph.py  (key signature)

from langgraph.graph import StateGraph
from src.ai.registry.interfaces import IAgentRegistry
from src.ai.workflows.earnings_brief.state import EarningsBriefState
from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

def build_earnings_brief_graph(
    registry: IAgentRegistry,
    cost_ceiling_usd: float,
    pg_checkpointer,          # LangGraph PostgresSaver instance
) -> "CompiledGraph":
    """
    Builds and compiles the Earnings Risk Brief StateGraph.
    Validates evaluate_quality → narrative_writer tail invariant before returning.
    Raises WorkflowStructureError if invariant is violated.
    """
    ...

def node_sequence() -> list[str]:
    """Returns ordered node names for WorkflowStructureValidator."""
    return [
        "fetch_company_state",
        "fetch_earnings_history",
        "fetch_macro_context",
        "fetch_sector_recent_earnings",
        "earnings_context",
        "historical_context",
        "recommendation_synthesizer",
        "narrative_writer",
        "evaluate_quality",
    ]
```

```python
# src/ai/workflows/earnings_brief/tasks.py  (key signatures)

from celery import shared_task
from uuid import UUID

@shared_task(
    name="ai.detect_t1_earnings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def detect_t1_earnings_task(self) -> dict:
    """
    Cron entry point (17:30 daily).
    Queries portfolio positions joined with earnings_event where
    earnings_date = next_trading_day().
    For each qualifying company not already in earnings_brief_run for that date,
    enqueues earnings_brief_task.
    Returns: { "companies_queued": N, "already_processed": M }
    """
    ...

@shared_task(
    name="ai.earnings_brief",
    bind=True,
    time_limit=600,         # 10 min absolute hard limit
    soft_time_limit=240,    # 4 min soft limit → TIMEOUT status
    max_retries=0,          # no auto-retry; each company is independent
)
def earnings_brief_task(self, workflow_id: str, company_id: str,
                        earnings_date: str, tenant_id: str, user_id: str) -> dict:
    """
    Executes the full earnings brief LangGraph workflow for one company.
    """
    ...
```

```python
# src/api/routers/earnings_brief_router.py  (key signatures)

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["earnings-briefs"])

# GET /api/v1/earnings-briefs
# Auth: authenticated end_user or above
# Query params: date (optional, defaults to today's T+1 detection run)
# Returns: list of EarningsBriefRun records for the tenant's portfolio companies

# GET /api/v1/earnings-briefs/{run_id}
# Auth: resource-owner check (tenant_id + user_id)
# Returns: full EarningsBriefRun with report payload if COMPLETED
```

```python
# Alembic migration: earnings_event and earnings_brief_run tables

# earnings_event: stores T+1 earnings calendar data per company
# Columns: event_id UUID PK, company_id UUID FK→company, earnings_date DATE NOT NULL,
#          source VARCHAR(50), fiscal_quarter VARCHAR(10), fiscal_year INT,
#          estimated_eps FLOAT, reported_eps FLOAT, surprise_pct FLOAT,
#          fetched_at TIMESTAMPTZ DEFAULT now()
# Unique: (company_id, earnings_date)
# Index: (earnings_date) for T+1 detection query

# earnings_brief_run: idempotency guard + status tracking
# Columns: run_id UUID PK, workflow_id UUID FK→workflow_run,
#          company_id UUID FK→company, tenant_id UUID NOT NULL,
#          earnings_date DATE NOT NULL, status VARCHAR(20) NOT NULL,
#          created_at TIMESTAMPTZ DEFAULT now()
# Unique: (company_id, tenant_id, earnings_date)  — prevents duplicate dispatch
# Index: (tenant_id, earnings_date) for HIL fallback query
```

## Implementation Tasks

### TASK-001: DB migrations — earnings_event and earnings_brief_run tables · M/TDD · alembic/versions/xxxx_earnings_brief_tables.py

Create one Alembic migration with two tables.

`earnings_event`: stores per-company earnings calendar entries. Required columns:
`event_id UUID PK`, `company_id UUID NOT NULL FK→company ON DELETE CASCADE`,
`earnings_date DATE NOT NULL`, `source VARCHAR(50) NOT NULL`,
`fiscal_quarter VARCHAR(10)`, `fiscal_year INT`,
`estimated_eps FLOAT`, `reported_eps FLOAT`, `surprise_pct FLOAT`,
`fetched_at TIMESTAMPTZ DEFAULT now()`.
Unique constraint on `(company_id, earnings_date)`.
Index on `earnings_date` (used by daily T+1 detection query).

`earnings_brief_run`: idempotency guard and status tracking.
`run_id UUID PK`, `workflow_id UUID FK→workflow_run`,
`company_id UUID NOT NULL FK→company`, `tenant_id UUID NOT NULL`,
`earnings_date DATE NOT NULL`, `status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'`,
`created_at TIMESTAMPTZ DEFAULT now()`.
Unique constraint on `(company_id, tenant_id, earnings_date)` — prevents duplicate
brief dispatch for the same company on the same date.
Index on `(tenant_id, earnings_date)` for HIL fallback polling.

Down migration must cleanly drop both tables.

**Tests to write first (TDD):**
- `test_migration_applies_and_rolls_back` — Alembic `upgrade` then `downgrade` against test DB succeeds without error.
- `test_earnings_event_unique_constraint` — inserting two rows for the same `(company_id, earnings_date)` raises `IntegrityError`.
- `test_earnings_brief_run_unique_constraint` — duplicate `(company_id, tenant_id, earnings_date)` raises `IntegrityError`.
- `test_earnings_event_company_fk_cascade` — deleting a company cascades to its earnings_event rows.

**AC covered**: AC-001, AC-004 (tables must exist before detection query and brief tasks can run)

---

### TASK-002: EarningsBriefState Pydantic model and EarningsBriefRunRepository · M/TDD · src/ai/workflows/earnings_brief/state.py,src/ai/workflows/earnings_brief/__init__.py,src/storage/repositories/earnings_brief_repository.py,tests/unit/ai/workflows/earnings_brief/test_earnings_brief_state.py

Define `EarningsBriefState`, `ScenarioTree`, and `EarningsScenario` per the contracts in
Component Design. Implement `IEarningsBriefRunRepository` protocol and
`EarningsBriefRunRepository` with: `create(workflow_id, company_id, tenant_id, earnings_date) -> EarningsBriefRun`,
`get(run_id, tenant_id) -> EarningsBriefRun | None`,
`exists_for_date(company_id, tenant_id, earnings_date) -> bool` (idempotency check),
`update_status(run_id, status, **kwargs) -> None`,
`list_for_tenant(tenant_id, earnings_date) -> list[EarningsBriefRun]`.
All queries scope by `tenant_id`. `ScenarioTree` must validate that
`bull.probability + base.probability + bear.probability` equals 1.0 ± 0.01 (field
validator); failing this raises `ValueError`.

**Tests to write first (TDD):**
- `test_scenario_tree_probabilities_sum_to_one` — valid tree with probs 0.25/0.50/0.25 passes.
- `test_scenario_tree_probabilities_invalid_sum_raises` — probs 0.4/0.4/0.4 raises `ValueError`.
- `test_earnings_brief_state_status_defaults_to_running`.
- `test_earnings_brief_state_serialises_to_json` — `state.model_dump_json()` must not raise.
- `test_run_repository_create_and_get` — integration: creates row; retrieves by `run_id` + `tenant_id`.
- `test_run_repository_get_wrong_tenant_returns_none` — IDOR guard.
- `test_run_repository_exists_for_date_returns_true_after_create`.
- `test_run_repository_exists_for_date_false_different_date`.

**AC covered**: AC-002, AC-005

---

### TASK-003: T+1 earnings detection — detect_t1_earnings_task · M/TDD · src/ai/workflows/earnings_brief/tasks.py,src/config/celery_app.py,tests/unit/ai/workflows/earnings_brief/test_earnings_brief_tasks.py,tests/integration/ai/test_earnings_brief_no_earnings_today.py

Implement `detect_t1_earnings_task` as a Celery task. The task:
1. Calls `next_trading_day()` (a pure function in a new `src/ai/workflows/earnings_brief/calendar.py`) that returns the next trading day date, skipping weekends and US market holidays.
2. Queries the `earnings_event` table for rows where `earnings_date = next_trading_day()`.
3. Joins with `position` (via `company_id`) to filter only portfolio companies for each tenant.
4. For each qualifying `(tenant_id, company_id, earnings_date)` tuple, calls `exists_for_date` on `EarningsBriefRunRepository`; if already processed, skips (idempotency).
5. For each unprocessed company, generates a `workflow_id` UUID, creates an `earnings_brief_run` row with `status=RUNNING`, and enqueues `earnings_brief_task.delay(...)`.
6. Returns a summary dict `{"companies_queued": N, "already_processed": M}`.

When no companies have T+1 earnings, the task returns `{"companies_queued": 0, "already_processed": 0}` and enqueues nothing. Register the task in Celery beat with a cron schedule of `17:30` daily.

**Tests to write first (TDD):**
- `test_detect_task_queues_one_task_per_qualifying_company` — mock: 2 portfolio companies with T+1 earnings; assert `earnings_brief_task.delay` called twice.
- `test_detect_task_skips_already_processed_companies` — `exists_for_date` returns True; assert no second dispatch.
- `test_detect_task_no_earnings_enqueues_nothing` — empty `earnings_event` result; returns `companies_queued=0`.
- `test_detect_task_only_queries_portfolio_companies` — earnings_event has 5 companies but only 2 are in any portfolio; assert only 2 queued.
- `test_next_trading_day_skips_weekends` — Friday → returns Monday.
- `test_next_trading_day_skips_us_holidays` — day before Thanksgiving → returns day after.

**AC covered**: AC-001, AC-004

---

### TASK-004: DeterministicNodes — four fetch nodes · M/TDD · src/ai/workflows/earnings_brief/nodes/fetch_company_state.py,src/ai/workflows/earnings_brief/nodes/fetch_earnings_history.py,src/ai/workflows/earnings_brief/nodes/fetch_macro_context.py,src/ai/workflows/earnings_brief/nodes/fetch_sector_recent_earnings.py,src/ai/workflows/earnings_brief/nodes/__init__.py,tests/unit/ai/workflows/earnings_brief/test_fetch_company_state.py,tests/unit/ai/workflows/earnings_brief/test_fetch_earnings_history.py,tests/unit/ai/workflows/earnings_brief/test_fetch_macro_context.py,tests/unit/ai/workflows/earnings_brief/test_fetch_sector_recent_earnings.py

Implement four DeterministicNodes as pure `(state: EarningsBriefState) -> EarningsBriefState`
functions with constructor-injected repository dependencies via a `NodeContext` dataclass.

`fetch_company_state`: loads company fundamentals, current portfolio position, latest
`company_score` entries for `state.company_id`. Populates `state.company_state`.
Raises `CompanyNotFoundError` if the company does not exist for the tenant.

`fetch_earnings_history`: queries `earnings_event` for the company's past 8 earnings events
(chronological descending), including `reported_eps`, `estimated_eps`, and `surprise_pct`.
Returns empty list when no history exists (not an error). Populates `state.earnings_history`.

`fetch_macro_context`: queries FRED macro indicators (CPI, Fed Funds Rate, 10Y Treasury
Yield, GDP growth) via the cache-or-fetch layer (Architecture §7.3 Macro & Market tools).
Caps at 10 indicators (bounded output). Populates `state.macro_context`.

`fetch_sector_recent_earnings`: queries `earnings_event` joined with `company` to retrieve
earnings results from sector peers in the last 90 days. Returns at most 20 rows (bounded
output). Used by the Earnings Context Agent to frame sector-level expectations. Populates
`state.sector_recent_earnings`.

All four nodes assert `tenant_id` scoping on every repository call.

**Tests to write first (TDD):**
- `test_fetch_company_state_populates_state` — mock repository returns company fixture; asserts `state.company_state` set.
- `test_fetch_company_state_not_found_raises` — repository returns `None`; `CompanyNotFoundError` raised.
- `test_fetch_company_state_scoped_to_tenant` — asserts repository called with `tenant_id`.
- `test_fetch_earnings_history_populates_state` — mock returns 5 records; `state.earnings_history` has 5 items.
- `test_fetch_earnings_history_empty_is_not_error` — repository returns `[]`; node succeeds.
- `test_fetch_macro_context_populates_state` — mock returns 10 indicators; `state.macro_context` set.
- `test_fetch_macro_context_caps_at_ten` — repository returns 15 items; node trims to 10.
- `test_fetch_sector_recent_earnings_populates_state` — mock returns peers; state updated.
- `test_fetch_sector_recent_earnings_caps_at_twenty` — 25 rows returned; node trims to 20.

**AC covered**: AC-001, AC-002

---

### TASK-005: AgentNode — Earnings Context Agent (scenario tree) · L/TDD · src/ai/workflows/earnings_brief/nodes/earnings_context_node.py,tests/unit/ai/workflows/earnings_brief/test_earnings_context_node.py

Implement `earnings_context_node` as an `async def` AgentNode wrapper following the same
structural pattern as the AgentNode wrappers in PLAN-F-007. The node:
1. Retrieves `AgentDefinition` for `role_id="earnings-context-agent"` from the injected
   `IAgentRegistry`.
2. Constructs the agent input from `state.company_state`, `state.earnings_history`,
   `state.macro_context`, and `state.sector_recent_earnings`.
3. Calls `ToolGuard.assert_allowed` before any tool dispatch.
4. Wraps the LLM call in `LangfuseInvocationLogger`.
5. Applies `ExecutionLimiter` checks.
6. Validates the output against `AgentDefinition.output_schema` using `jsonschema.validate`.
7. Deserializes the output into a `ScenarioTree` Pydantic model; raises `OutputSchemaError`
   if deserialization fails.
8. Populates `state.scenario_tree`.
9. Records `state.confidence_scores["earnings_context"]`.
10. Accumulates `state.cost_usd` and `state.tokens_consumed`.
11. Calls `CostCeilingGuard.check(state)` before returning.

The agent must produce at minimum three scenarios (bull, base, bear) each with a probability
weight, macro rationale, and sector rationale — the output schema enforces this.

**Tests to write first (TDD):**
- `test_earnings_context_node_populates_scenario_tree` — mock agent returns valid fixture; `state.scenario_tree` is a `ScenarioTree`.
- `test_earnings_context_node_scenarios_have_required_fields` — asserts `bull`, `base`, `bear` each have `probability` and `rationale`.
- `test_earnings_context_node_accumulates_cost` — mock returns `cost_usd=0.25`; `state.cost_usd` increases.
- `test_earnings_context_node_records_confidence_score` — `state.confidence_scores["earnings_context"]` is set.
- `test_earnings_context_node_invalid_output_raises` — mock returns dict missing `bear`; `OutputSchemaError` propagates.
- `test_earnings_context_node_calls_cost_guard` — mock `CostCeilingGuard`; assert `check` called.
- `test_earnings_context_node_tool_guard_blocks_disallowed_tool` — `ToolGuard` raises for unlisted tool name.

**AC covered**: AC-002

---

### TASK-006: AgentNodes — Historical Context Agent, Recommendation Synthesizer, Narrative Writer · M/TDD · src/ai/workflows/earnings_brief/nodes/historical_context_node.py,src/ai/workflows/earnings_brief/nodes/recommendation_node.py,src/ai/workflows/earnings_brief/nodes/narrative_writer_node.py,tests/unit/ai/workflows/earnings_brief/test_historical_context_node.py,tests/unit/ai/workflows/earnings_brief/test_recommendation_node.py,tests/unit/ai/workflows/earnings_brief/test_narrative_writer_node.py

Implement three AgentNode wrapper modules following the same structural pattern as TASK-005.

`historical_context_node`: role `"historical-context-agent"`. Input includes
`state.scenario_tree` and `state.earnings_history`. Uses pgvector semantic search
(via tool calls) to find historical earnings-surprise analogies whose outcomes match
each scenario. Populates `state.analogies_output`. Records
`state.confidence_scores["historical_context"]`.

`recommendation_node`: role `"recommendation-synthesizer"`. Input includes
`state.scenario_tree`, `state.analogies_output`, and `state.company_state`. Produces a
**scenario-tree-form recommendation** (not a single action signal) — the output schema
must match the scenario tree structure extended with action implications per scenario
(`hold_signal`, `position_sizing_guidance`, `key_risk_factors`). Populates
`state.recommendation`. Records `state.confidence_scores["recommendation_synthesizer"]`.

`narrative_writer_node`: role `"narrative-writer"`. Input includes all prior outputs. Produces
the final prose brief in FT columnist voice (Architecture §7.2 Narrative Writer). Populates
`state.report`. Records `state.confidence_scores["narrative_writer"]`.

Each node: wraps in `LangfuseInvocationLogger`, applies `ExecutionLimiter`, validates
output against `AgentDefinition.output_schema`, accumulates `cost_usd`, calls
`CostCeilingGuard.check(state)` before returning.

**Tests to write first (TDD):**
- For each of the three nodes:
  - `test_<role>_node_populates_correct_state_field` — mock agent returns fixture; correct `state.*` field is set.
  - `test_<role>_node_accumulates_cost`.
  - `test_<role>_node_records_confidence_score`.
  - `test_<role>_node_raises_on_invalid_output_schema` — missing required key; propagates `jsonschema.ValidationError`.
- `test_recommendation_node_output_includes_all_three_scenarios` — recommendation output has `bull`, `base`, `bear` keys.
- `test_narrative_writer_node_report_is_nonempty_string` — `state.report["text"]` is non-empty.

**AC covered**: AC-002

---

### TASK-007: evaluate_quality DeterministicNode — earnings brief variant · M/TDD · src/ai/workflows/earnings_brief/nodes/evaluate_quality.py,tests/unit/ai/workflows/earnings_brief/test_evaluate_quality.py

Implement `evaluate_quality` as a DeterministicNode specific to the earnings brief workflow.
Logic is identical to the pattern in PLAN-F-007 TASK-005 (min-confidence routing via D9)
but operates on `EarningsBriefState`. The node:
1. Computes `state.overall_confidence = min(state.confidence_scores.values())`.
2. Sets `state.requires_hil` and `state.status` per D9:
   - `≥0.7` → `status=COMPLETED`, `requires_hil=False`.
   - `0.4–0.69` → `status=HIL_PENDING`, `requires_hil=True`, `hil_reason="Confidence below auto-send threshold"`.
   - `<0.4` → `status=BLOCKED`, `requires_hil=False`, `hil_reason="Confidence too low to deliver"`.
3. Raises `EvaluateQualityError("No agent confidence scores recorded")` if `confidence_scores` is empty.

This node is always second-to-last. `WorkflowStructureValidator` (PLAN-F-011) enforces this
at build time. Note: per Architecture §7.5 Workflow 4, `evaluate_quality` appears after
`narrative_writer` in the execution order — the `node_sequence()` function reflects this.
The `WorkflowStructureValidator` invariant is: `["evaluate_quality", "narrative_writer"]`
must end the sequence — but per Architecture §7.1, "Narrative Writer is always the last
AgentNode" and `evaluate_quality` is "always the second-to-last node" (DeterministicNode).
The authoritative Architecture §7.5 sequence ends `→ Narrative Writer → evaluate_quality →
branch`, meaning `evaluate_quality` is the second-to-last node and `narrative_writer` is
the last AgentNode (which runs immediately before it). The `node_sequence()` list therefore
ends `[..., "narrative_writer", "evaluate_quality"]`.

**Tests to write first (TDD):**
- `test_evaluate_quality_high_confidence_sets_completed` — min confidence 0.75 → `COMPLETED`, `requires_hil=False`.
- `test_evaluate_quality_mid_confidence_sets_hil_pending` — min confidence 0.55 → `HIL_PENDING`, `requires_hil=True`.
- `test_evaluate_quality_low_confidence_sets_blocked` — min confidence 0.3 → `BLOCKED`.
- `test_evaluate_quality_uses_minimum_not_average` — scores `[0.9, 0.9, 0.35]` → `overall_confidence=0.35`.
- `test_evaluate_quality_empty_scores_raises` — `confidence_scores={}` → `EvaluateQualityError`.
- `test_evaluate_quality_boundary_0_7_inclusive_is_completed` — score exactly 0.7 → `COMPLETED`.
- `test_evaluate_quality_boundary_0_4_inclusive_is_hil_pending` — score exactly 0.4 → `HIL_PENDING`.

**AC covered**: AC-003

---

### TASK-008: Graph builder — build_earnings_brief_graph with PostgreSQL checkpointing · L/TDD · src/ai/workflows/earnings_brief/graph.py,tests/unit/ai/workflows/earnings_brief/test_earnings_brief_graph.py,tests/integration/ai/test_earnings_brief_happy_path.py,tests/integration/ai/test_earnings_brief_cost_limit.py,tests/integration/ai/test_earnings_brief_confidence_routing.py,tests/integration/ai/test_earnings_brief_timeout.py

Implement `build_earnings_brief_graph` per the contract in Component Design. The function
constructs a `StateGraph(EarningsBriefState)`, adds all nine nodes in order per
`node_sequence()`, adds conditional edges from `evaluate_quality` routing on `state.status`
(`COMPLETED` → end, `HIL_PENDING` → end, `BLOCKED` → end, `COST_LIMIT` → end,
`TIMEOUT` → end), and compiles with `pg_checkpointer`. Before returning, calls
`WorkflowStructureValidator().validate(node_sequence())`. An error edge from any node to a
`_handle_error` DeterministicNode catches `WorkflowCostLimitError` and
`WorkflowTimeoutError`, sets the appropriate `state.status` and `state.error_detail`, and
routes to the end node. The compiled graph is cached at module level.

The Alembic migration for `langgraph_checkpoints` table is added here if not already created
by PLAN-F-007; if PLAN-F-007 has already created it, this task only documents that
dependency and skips re-creation.

**Tests to write first (TDD):**
- `test_graph_has_correct_node_count` — compiled graph has exactly nine nodes plus error handler.
- `test_graph_node_sequence_ends_with_narrative_writer_then_evaluate_quality` — `node_sequence()[-2:]` equals `["narrative_writer", "evaluate_quality"]`.
- `test_graph_structure_validator_called_at_build` — mock `WorkflowStructureValidator`; assert `validate` called with `node_sequence()`.
- `test_graph_build_fails_on_invalid_node_sequence` — tampered sequence missing `evaluate_quality`; `WorkflowStructureError` raised.
- Integration: `test_earnings_brief_happy_path` — full compiled graph with mocked agents (confidence 0.8, cost $0.90); `status=COMPLETED`, `state.report` populated, `state.scenario_tree` has all three scenarios.
- Integration: `test_earnings_brief_cost_limit` — third agent accumulates cost to $1.51; `status=COST_LIMIT`, `error_detail` non-null.
- Integration: `test_earnings_brief_confidence_routing_hil` — agents return confidence 0.55; `status=HIL_PENDING`, `requires_hil=True`.
- Integration: `test_earnings_brief_timeout` — patch `soft_time_limit` to raise `SoftTimeLimitExceeded`; `status=TIMEOUT`.

**AC covered**: AC-001, AC-002, AC-003, AC-005

---

### TASK-009: Celery task — earnings_brief_task with timeout and audit logging · M/TDD · src/ai/workflows/earnings_brief/tasks.py,src/config/celery_app.py,src/config/settings.py,tests/unit/ai/workflows/earnings_brief/test_earnings_brief_tasks.py

Implement `earnings_brief_task` per the contract in Component Design. The task:
1. Opens a `LangfuseWorkflowTracer` root trace (from `src/ai/workflows/tracer.py`).
2. Constructs `EarningsBriefState` from task arguments.
3. Updates the `earnings_brief_run` row to `status=RUNNING` (row was created by `detect_t1_earnings_task`).
4. Invokes the compiled graph via `graph.invoke(state, config={"configurable": {"thread_id": str(workflow_id)}})`.
5. Persists the final state to `workflow_run.final_state`, updates `workflow_run.status` and `earnings_brief_run.status`.
6. If `status=COMPLETED`: saves the brief to `ai_recommendation` (populating `scenario_tree` JSONB field from Architecture §10) and notifies the frontend via `WorkflowNotifier`.
7. If `status=BLOCKED` or `TIMEOUT`: writes a structured entry to the admin AI audit log (a `workflow_run` row with `status=BLOCKED`/`TIMEOUT` and `final_state.hil_reason` populated).
8. Catches `SoftTimeLimitExceeded`, sets `state.status=TIMEOUT`, updates DB, writes audit entry.

Settings added: `EARNINGS_BRIEF_COST_CEILING_USD`, `EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS`.

**Tests to write first (TDD):**
- `test_earnings_brief_task_creates_workflow_run` — mock graph and repository; assert `create` called with `workflow_id`.
- `test_earnings_brief_task_updates_status_on_completion` — graph returns `COMPLETED`; assert `update_status(COMPLETED)` called on both repositories.
- `test_earnings_brief_task_saves_ai_recommendation_on_completion` — mock `AiRecommendationRepository`; assert `save` called with `scenario_tree` populated.
- `test_earnings_brief_task_handles_timeout` — patch graph to raise `SoftTimeLimitExceeded`; `status=TIMEOUT` persisted.
- `test_earnings_brief_task_writes_audit_entry_on_blocked` — graph returns `BLOCKED`; assert `workflow_run.status=BLOCKED` and `hil_reason` non-null.
- `test_earnings_brief_task_opens_langfuse_trace` — mock tracer; assert root trace opened with `workflow_type="earnings_brief"`.

**AC covered**: AC-001, AC-003, AC-005

---

### TASK-010: HIL fallback task — 17:45 deadline hold and user notification · S/no-TDD · src/ai/workflows/earnings_brief/hil/fallback_task.py,src/ai/workflows/earnings_brief/hil/__init__.py,src/config/celery_app.py

Implement `earnings_hil_fallback_task` as a Celery beat task running every 60 seconds. It
queries `earnings_brief_run` for rows where `status=HIL_PENDING` and
`created_at < NOW() - 15 minutes` (past the 17:45 deadline). For each such row it:
1. Updates `earnings_brief_run.status` to `HIL_HOLD`.
2. Writes an audit entry to `workflow_run` with `status=HIL_HOLD` and a `hil_reason` of
   `"HIL deadline passed without review"`.
3. Notifies the user (via the existing notification infrastructure) that their brief is on
   hold pending review, with a link to `/admin/hil`.

This implements the Architecture §7.6 Earnings Risk Brief HIL fallback: "hold; notify user"
when unreviewed by 17:45. Register the beat schedule with a 60-second interval.

**AC covered**: AC-003

---

### TASK-011: FastAPI status endpoints and ai_recommendation persistence · M/TDD · src/api/routers/earnings_brief_router.py,src/storage/repositories/ai_recommendation_repository.py,src/api/routers/__init__.py,tests/integration/api/test_earnings_brief_router.py

Implement two read-only FastAPI endpoints and the `ai_recommendation` persistence layer for
earnings briefs.

`GET /api/v1/earnings-briefs`: returns a list of `EarningsBriefRun` records for the
authenticated tenant's portfolio companies. Optional `?date=YYYY-MM-DD` query parameter
filters by earnings date. Returns empty list (not 404) when no briefs exist for the date.

`GET /api/v1/earnings-briefs/{run_id}`: returns the full `EarningsBriefRun` including the
report payload and `scenario_tree` JSONB when `status=COMPLETED`. Returns 404 if the run
does not exist for the requesting tenant (IDOR guard).

`AiRecommendationRepository.save_earnings_brief(state: EarningsBriefState) -> UUID`:
maps `state.recommendation` (scenario-tree form) and `state.scenario_tree` to the
`ai_recommendation` row; populates `scenario_tree JSONB` from Architecture §10 (`forecast`
field stores the full `ScenarioTree` JSON). Called from `earnings_brief_task` on completion.

Both endpoints enforce JWT authentication via `get_current_user`. Response envelope follows
DEV-STANDARDS §7 convention. Controllers never return raw ORM models.

**Tests to write first (TDD):**
- `test_list_briefs_returns_empty_list_when_none` — no briefs for date; HTTP 200 with `data=[]`.
- `test_list_briefs_returns_completed_brief` — one COMPLETED brief; response includes `status=COMPLETED`.
- `test_list_briefs_requires_auth` — unauthenticated request returns 401.
- `test_get_brief_returns_full_report_when_completed` — `status=COMPLETED`; `data.report` and `data.scenario_tree` present.
- `test_get_brief_404_for_wrong_tenant` — another tenant's `run_id` returns 404.
- `test_save_earnings_brief_populates_scenario_tree_jsonb` — integration: saved row has non-null `scenario_tree`.
- `test_save_earnings_brief_scoped_to_company` — `list_for_company` returns the saved recommendation.

**AC covered**: AC-001, AC-002, AC-005

---

## Acceptance Criteria Coverage

- AC-001: Given portfolio companies with T+1 earnings events, the system triggers an earnings brief workflow for each qualifying company daily, completing within 4 minutes and $1.50 per company → TASK-003, TASK-008, TASK-009
- AC-002: Given the Earnings Context Agent runs, the output includes a structured scenario tree with at minimum bull, base, and bear scenarios each with a probability weight and macro/sector rationale → TASK-005, TASK-006, TASK-008, TASK-011
- AC-003: Given the evaluate_quality node produces confidence ≥ 0.7, the brief is auto-delivered; confidence 0.4–0.69 routes to HIL queue; confidence < 0.4 is blocked → TASK-007, TASK-008, TASK-009, TASK-010
- AC-004: Given no portfolio companies have T+1 earnings, no earnings brief workflow is triggered and no cost is incurred → TASK-001, TASK-003
- AC-005: Given the workflow hard limit (10 minutes) is reached before completion, the workflow is terminated and the admin AI audit console records the timeout → TASK-008, TASK-009, TASK-011

## Acceptance Notes

AC-005 ("admin AI audit console records the timeout") means a `workflow_run` row with
`status=TIMEOUT` and `final_state.hil_reason` populated. The Admin AI Audit Console UI
(PLAN-F-029) reads these rows — no additional audit table is required for this plan.

The HIL Review Queue UI (PLAN-F-013) is the admin interface for approving or rejecting
`HIL_PENDING` briefs. TASK-010 routes items to the hold state and notifies users, but the
actual approve/edit/reject UI is out of scope here.

## Risks and Notes

- **Scenario tree probability validation**: `ScenarioTree` validates that probabilities sum to 1.0 ± 0.01. The Earnings Context Agent (Opus 4.7) is the LLM producing these values. If the model returns probabilities summing to e.g. 0.95 due to rounding, the Pydantic validator will raise. The prompt for `earnings_context_agent.md` must explicitly instruct the model to ensure probabilities sum to exactly 1.0. Validation tolerance of ±0.01 provides a safety buffer.
- **`node_sequence()` ordering vs. Architecture §7.1 invariant**: Architecture §7.1 states `evaluate_quality` is "always the second-to-last node" and `Narrative Writer` is "always the last AgentNode." Architecture §7.5 Workflow 4 ends `→ Narrative Writer → evaluate_quality → branch`. This means `evaluate_quality` runs after `narrative_writer` in graph execution order. The `WorkflowStructureValidator` in PLAN-F-011 TASK-007 checks that the sequence ends with `["evaluate_quality", "narrative_writer"]`. However, the authoritative §7.5 sequence ends with `Narrative Writer → evaluate_quality`. There is a notation ambiguity between "last AgentNode" and "last node overall." This plan resolves it as: `narrative_writer` is the last *AgentNode*; `evaluate_quality` is the last *overall* node (second-to-last was the Architecture's intent for the AgentNode ordering, not absolute node ordering). The `node_sequence()` list ends `[..., "narrative_writer", "evaluate_quality"]` matching §7.5. The `WorkflowStructureValidator` must be called with this sequence. Confirm the invariant check in PLAN-F-011 aligns with this interpretation before executing TASK-008.
- **CostCeilingGuard reuse**: `CostCeilingGuard` is defined in `src/ai/workflows/cost_guard.py` (PLAN-F-007). This plan reuses it without modification. If PLAN-F-007 has not yet been executed, TASK-008 must create a minimal local `CostCeilingGuard` stub to unblock integration tests.
- **Idempotency of detect_t1_earnings_task**: the unique constraint on `(company_id, tenant_id, earnings_date)` in `earnings_brief_run` is the primary idempotency guard. The application-level `exists_for_date` check is a defense-in-depth pre-flight that avoids hitting the constraint in the happy path. Both layers are required.
- **GDELT cold-start dependency**: historical analogy quality (Historical Context Agent) depends on the GDELT archive seed (Architecture §12.6 GDELT historical archive cold-start). If the archive is not seeded, the analogy engine returns empty results; the Historical Context Agent should handle `InsufficientData` tool errors gracefully and record a lower confidence score rather than failing the workflow.
- **LangGraph checkpointing migration**: if PLAN-F-007 is executed first, the `langgraph_checkpoints` migration table already exists. TASK-008 must check for existence before attempting to create it. Use `IF NOT EXISTS` in the migration or a separate conditional migration step.
- **Earnings calendar data source**: the `earnings_event` table must be populated by an ingestion job (data sourced from Financial Modeling Prep `FundamentalsProvider`). That ingestion job is out of scope for this plan; for MVP, `earnings_event` rows can be seeded manually or via the cold-start seeding plan (PLAN-F-031). TASK-003 must handle the case where `earnings_event` is empty gracefully.
