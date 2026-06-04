---
plan_id: PLAN-F-007
slug: on-demand-analysis-workflow
title: On-Demand Company Analysis Workflow (Mode B)
linked_requirement: REQ-F-007
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-002, reason: "On-demand workflow must complete end-to-end in ≤4 min (p95); Celery task hard-terminated at 6 min absolute" }
  - { id: REQ-N-004, reason: "Per-report cost ceiling $1.50; CostCeilingGuard halts workflow if ceiling is approached" }
  - { id: REQ-N-008, reason: "One Langfuse trace per workflow run; parallel agent calls produce sibling spans" }
dependencies:
  - { id: PLAN-F-011, reason: "Named-role agents (Exposure Analyst, Historical Context Agent, Anomaly Detector, Recommendation Synthesizer, Narrative Writer) must be defined in AgentRegistry before this workflow graph can resolve them" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-007 — On-Demand Company Analysis Workflow (Mode B)

## Linked Requirement
**REQ-F-007** — On-Demand Company Analysis Workflow (Mode B)
Status: approved | Jira:

## Objective
Build the complete Workflow 2 — On-Demand Company Analysis — as a LangGraph StateGraph
running inside a Celery task. When a user clicks "Deep Analyze" on a Company Detail screen,
a FastAPI endpoint creates a `workflow_run` record and enqueues a Celery task. The task
executes a seven-node graph: two DeterministicNodes (`fetch_company_state`,
`fetch_active_events`), five AgentNodes (`Exposure Analyst` → `Historical Context Agent` →
`Anomaly Detector` → `Recommendation Synthesizer` → `Narrative Writer`), and a terminal
quality-gate DeterministicNode (`evaluate_quality`) followed by a confidence-routing branch.
The workflow must finish within 4 minutes (p95) and cost no more than $1.50 per run; both
constraints are enforced programmatically. Confidence routing follows D9: ≥0.7 auto-delivers
the report; 0.4–0.69 routes to the HIL queue (delivers with a low-confidence banner after
10 minutes unreviewed); <0.4 blocks with an error message recorded in the AI audit log.
The completed report is persisted to `ai_recommendation` and surfaced on the Company Detail
screen; a full Langfuse trace with sibling spans for any parallel agent work is emitted per
run.

## Architecture Context
This plan operates in Layer 4 (Processing — Mode B) and Layer 5 (Serving — API). It
introduces new files across three backend modules:

- `src/ai/workflows/` — new sub-package within the `ai` module (Architecture §5, §7).
  Contains the LangGraph StateGraph definition, node implementations, graph builder, and the
  `CostCeilingGuard`.
- `src/api/` — new FastAPI router (`workflow_router.py`) and a new WebSocket notification
  path for delivering the completed report to the frontend without polling.
- `src/config/celery_app.py` — registers the new Celery task.

The graph uses the `WorkflowState` Pydantic model defined in Architecture §7.1. PostgreSQL
checkpointing (via LangGraph's built-in `PostgresSaver`) is mandatory for failure recovery,
HIL pause/resume, and replay. The `AgentRegistry` (PLAN-F-011) is injected into graph nodes
at construction time — nodes never construct agents themselves. The `WorkflowStructureValidator`
from PLAN-F-011 is invoked at graph-build time to assert the `evaluate_quality` →
`narrative_writer` tail invariant (Architecture §7.1 cross-workflow invariants). The
`LangfuseInvocationLogger` from PLAN-F-011 decorates every AgentNode call.

Confidence routing and HIL fallback follow Architecture §7.6–7.7 and D9. The 10-minute HIL
window for on-demand runs is checked by a lightweight Celery beat task introduced in this plan.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-002 | On-demand workflow ≤4 min end-to-end (p95); absolute hard limit 6 min | `OnDemandAnalysisTask` is wrapped with `celery.task(time_limit=360, soft_time_limit=300)`. The Celery soft limit fires at 300 s, writes a `TIMEOUT` terminal state, and notifies the frontend. Per-agent `timeout_seconds` values in agent YAMLs (from PLAN-F-011) budget agent time; `ExecutionLimiter` enforces them. |
| REQ-N-004 | Per-report cost ceiling $1.50; halt if ceiling approached | `CostCeilingGuard.check(state)` is called after every AgentNode. It reads `state.cost_usd` and raises `WorkflowCostLimitError` if it reaches or exceeds $1.50. The error is caught by the graph's error edge, sets `WorkflowState.status = "COST_LIMIT"`, and delivers a partial-results message to the frontend. |
| REQ-N-008 | One Langfuse trace per workflow run; sibling spans for parallel agent calls | `LangfuseWorkflowTracer` opens a root trace at task start with `workflow_id`, `workflow_type="on_demand"`, `tenant_id`, `user_id`. Each AgentNode call uses `LangfuseInvocationLogger` (PLAN-F-011) as a child span. Any `asyncio.gather` over parallel tool calls inside a node produces sibling sub-spans via the Langfuse SDK context propagation. |

## Component Design

### New Components
```
Package: src/ai/workflows/
  ├── __init__.py
  ├── state.py                          — WorkflowState Pydantic model (canonical for all workflows)
  ├── on_demand/
  │   ├── __init__.py
  │   ├── graph.py                      — build_on_demand_graph() → CompiledGraph
  │   ├── nodes/
  │   │   ├── __init__.py
  │   │   ├── fetch_company_state.py    — DeterministicNode: load company, portfolio, scores
  │   │   ├── fetch_active_events.py    — DeterministicNode: load active geo_events for company
  │   │   ├── exposure_analyst_node.py  — AgentNode wrapper: Exposure Analyst
  │   │   ├── historical_context_node.py— AgentNode wrapper: Historical Context Agent
  │   │   ├── anomaly_detector_node.py  — AgentNode wrapper: Anomaly Detector
  │   │   ├── recommendation_node.py    — AgentNode wrapper: Recommendation Synthesizer
  │   │   ├── narrative_writer_node.py  — AgentNode wrapper: Narrative Writer
  │   │   └── evaluate_quality.py       — DeterministicNode: confidence aggregation + HIL flag
  │   └── tasks.py                      — Celery task: on_demand_analysis_task
  ├── cost_guard.py                     — CostCeilingGuard (reusable across all Mode B workflows)
  ├── tracer.py                         — LangfuseWorkflowTracer (root trace context manager)
  └── errors.py                         — WorkflowCostLimitError, WorkflowTimeoutError

Package: src/ai/workflows/on_demand/hil/
  ├── __init__.py
  └── fallback_task.py                  — Celery beat task: check 10-min HIL window, deliver
                                           with low-confidence banner if unreviewed

src/api/routers/workflow_router.py      — POST /api/v1/companies/{id}/analysis
                                           GET  /api/v1/workflow-runs/{run_id}
src/api/websocket/workflow_notifier.py  — push completed report over WebSocket channel

Tests:
tests/unit/ai/workflows/
  test_state.py
  test_cost_guard.py
  test_evaluate_quality.py
  test_fetch_company_state.py
  test_fetch_active_events.py
  test_exposure_analyst_node.py
  test_historical_context_node.py
  test_anomaly_detector_node.py
  test_recommendation_node.py
  test_narrative_writer_node.py
  test_on_demand_graph.py
  test_hil_fallback_task.py

tests/integration/ai/
  test_on_demand_workflow_happy_path.py
  test_on_demand_workflow_cost_limit.py
  test_on_demand_workflow_confidence_routing.py

tests/integration/api/
  test_workflow_router.py
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Register `on_demand_analysis_task` and `hil_fallback_task` | Celery must discover the new tasks |
| `src/config/settings.py` | Add `ON_DEMAND_COST_CEILING_USD: float = 1.50` and `ON_DEMAND_HIL_WINDOW_SECONDS: int = 600` | Values must come from environment, not be hardcoded |
| `src/api/routers/__init__.py` | Register `workflow_router` | Expose the trigger endpoint |

### Interfaces and Contracts

The executor must implement these exactly.

```python
# src/ai/workflows/state.py

from pydantic import BaseModel, Field
from typing import Any
from uuid import UUID
from datetime import datetime
from enum import Enum

class WorkflowType(str, Enum):
    ON_DEMAND       = "on_demand"
    MORNING_BRIEF   = "morning_brief"
    WATCHLIST_SCAN  = "watchlist_scan"
    EARNINGS_BRIEF  = "earnings_brief"
    EVENT_DEEP_DIVE = "event_deep_dive"

class WorkflowStatus(str, Enum):
    RUNNING       = "RUNNING"
    COMPLETED     = "COMPLETED"
    COST_LIMIT    = "COST_LIMIT"
    TIMEOUT       = "TIMEOUT"
    BLOCKED       = "BLOCKED"       # confidence < 0.4
    HIL_PENDING   = "HIL_PENDING"   # confidence 0.4–0.69; awaiting human review
    FAILED        = "FAILED"

class WorkflowState(BaseModel):
    workflow_id:       UUID
    workflow_type:     WorkflowType
    tenant_id:         UUID
    user_id:           UUID
    company_id:        UUID                       # on_demand scope
    started_at:        datetime
    inputs:            dict[str, Any] = Field(default_factory=dict)
    company_state:     dict[str, Any] | None = None
    active_events:     list[dict[str, Any]] = Field(default_factory=list)
    exposure_output:   dict[str, Any] | None = None
    historical_output: dict[str, Any] | None = None
    anomaly_output:    dict[str, Any] | None = None
    recommendation:    dict[str, Any] | None = None
    report:            dict[str, Any] | None = None
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float | None = None
    requires_hil:      bool = False
    hil_reason:        str | None = None
    cost_usd:          float = 0.0
    tokens_consumed:   dict[str, int] = Field(default_factory=dict)
    status:            WorkflowStatus = WorkflowStatus.RUNNING
    error_detail:      str | None = None
    langfuse_trace_id: str | None = None
```

```python
# src/ai/workflows/cost_guard.py

from src.ai.workflows.state import WorkflowState
from src.ai.workflows.errors import WorkflowCostLimitError

class CostCeilingGuard:
    """Raises WorkflowCostLimitError when accumulated cost reaches the ceiling."""

    def __init__(self, ceiling_usd: float) -> None:
        if ceiling_usd <= 0:
            raise ValueError("ceiling_usd must be positive")
        self._ceiling = ceiling_usd

    def check(self, state: WorkflowState) -> None:
        """Call after every AgentNode. Raises if cost_usd >= ceiling_usd."""
        if state.cost_usd >= self._ceiling:
            raise WorkflowCostLimitError(
                accumulated=state.cost_usd,
                ceiling=self._ceiling,
                workflow_id=state.workflow_id,
            )
```

```python
# src/ai/workflows/errors.py

from uuid import UUID

class WorkflowCostLimitError(Exception):
    def __init__(self, accumulated: float, ceiling: float, workflow_id: UUID) -> None:
        self.accumulated = accumulated
        self.ceiling = ceiling
        self.workflow_id = workflow_id
        super().__init__(
            f"Workflow {workflow_id} cost ${accumulated:.4f} reached ceiling ${ceiling:.2f}"
        )

class WorkflowTimeoutError(Exception):
    def __init__(self, workflow_id: UUID, elapsed_seconds: float) -> None:
        self.workflow_id = workflow_id
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"Workflow {workflow_id} timed out after {elapsed_seconds:.1f}s"
        )
```

```python
# src/ai/workflows/on_demand/graph.py  (key signature)

from langgraph.graph import StateGraph
from src.ai.registry.interfaces import IAgentRegistry
from src.ai.workflows.state import WorkflowState
from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

def build_on_demand_graph(
    registry: IAgentRegistry,
    cost_ceiling_usd: float,
    pg_checkpointer,          # LangGraph PostgresSaver instance
) -> "CompiledGraph":
    """
    Builds and compiles the On-Demand Analysis StateGraph.
    Validates the evaluate_quality → narrative_writer tail invariant before returning.
    Raises WorkflowStructureError if the invariant is violated.
    """
    ...

def node_sequence() -> list[str]:
    """Returns the ordered list of node names for WorkflowStructureValidator."""
    return [
        "fetch_company_state",
        "fetch_active_events",
        "exposure_analyst",
        "historical_context",
        "anomaly_detector",
        "recommendation_synthesizer",
        "narrative_writer",
        "evaluate_quality",
    ]
```

```python
# src/ai/workflows/on_demand/tasks.py  (key signature)

from celery import shared_task
from uuid import UUID

@shared_task(
    name="ai.on_demand_analysis",
    bind=True,
    time_limit=360,        # absolute hard limit: 6 min (REQ-N-002)
    soft_time_limit=300,   # soft limit: 5 min — triggers graceful shutdown
    max_retries=0,         # on-demand runs must not auto-retry
)
def on_demand_analysis_task(self, workflow_id: str, company_id: str,
                             tenant_id: str, user_id: str) -> dict:
    """
    Entry point for the on-demand analysis Celery task.
    Creates WorkflowState, runs the compiled graph, persists result,
    and notifies the frontend via WebSocket.
    """
    ...
```

```python
# src/api/routers/workflow_router.py  (key signatures)

from fastapi import APIRouter, Depends, status
from uuid import UUID

router = APIRouter(prefix="/api/v1", tags=["workflows"])

# POST /api/v1/companies/{company_id}/analysis
# Auth: authenticated end_user or above
# Returns: { "data": { "run_id": "<uuid>", "status": "RUNNING" }, "error": null }
# Side-effect: creates workflow_run row; enqueues on_demand_analysis_task

# GET /api/v1/workflow-runs/{run_id}
# Auth: resource-owner check (tenant_id + user_id)
# Returns: workflow_run status + report payload if COMPLETED
```

## Implementation Tasks

### TASK-001: WorkflowState Pydantic model and workflow_run DB table · M/TDD · src/ai/workflows/state.py,src/ai/workflows/__init__.py,src/storage/repositories/workflow_run_repository.py,src/storage/repositories/interfaces.py,tests/unit/ai/workflows/test_state.py

Define the `WorkflowState` Pydantic v2 model per the contract in Component Design above. Implement the `WorkflowRun` SQLAlchemy 2.0 ORM model mapping to the `workflow_run` table (Architecture §10 Agentic Layer Tables). Implement `IWorkflowRunRepository` protocol and `WorkflowRunRepository` with four methods: `create(state: WorkflowState) -> WorkflowRun`, `get(workflow_id: UUID, tenant_id: UUID) -> WorkflowRun | None`, `update_status(workflow_id: UUID, status: WorkflowStatus, **kwargs) -> None`, `save_final_state(workflow_id: UUID, final_state: WorkflowState) -> None`. The repository enforces `tenant_id` scoping on every query (Architecture §12.3). `WorkflowState.status` must be validated against the `WorkflowStatus` enum; an invalid literal must raise a Pydantic `ValidationError`, not a silent coercion.

**Tests to write first (TDD):**
- `test_workflow_state_requires_company_id` — constructing `WorkflowState` without `company_id` raises `ValidationError`
- `test_workflow_status_invalid_literal_raises` — `WorkflowStatus("NONSENSE")` raises `ValueError`
- `test_workflow_state_cost_usd_defaults_to_zero`
- `test_workflow_state_serialises_to_json` — `state.model_dump_json()` must not raise; UUID fields serialize as strings
- `test_workflow_run_repository_create_and_get` — integration: creates a row, retrieves by `workflow_id` + `tenant_id`
- `test_workflow_run_repository_get_wrong_tenant_returns_none` — IDOR guard: another tenant's `workflow_id` returns `None`

**AC covered**: AC-001, AC-005

---

### TASK-002: CostCeilingGuard and workflow error types · M/TDD · src/ai/workflows/cost_guard.py,src/ai/workflows/errors.py,tests/unit/ai/workflows/test_cost_guard.py

Implement `CostCeilingGuard` and both error classes per the contracts in Component Design. The guard must accept `ceiling_usd` as a constructor parameter — never read it from a global or module-level constant — so it is trivially injected with different values in tests. `WorkflowCostLimitError` and `WorkflowTimeoutError` must expose all constructor arguments as attributes and implement a `to_dict() -> dict` method for JSON-safe serialization into `WorkflowState.error_detail`.

**Tests to write first (TDD):**
- `test_cost_guard_passes_when_under_ceiling` — `cost_usd=1.49`, ceiling `1.50` → no raise
- `test_cost_guard_raises_at_ceiling` — `cost_usd=1.50`, ceiling `1.50` → `WorkflowCostLimitError`
- `test_cost_guard_raises_over_ceiling` — `cost_usd=1.51` → `WorkflowCostLimitError`
- `test_cost_guard_rejects_non_positive_ceiling` — `ceiling_usd=0.0` → `ValueError` in `__init__`
- `test_cost_limit_error_to_dict_is_json_serializable`
- `test_timeout_error_to_dict_is_json_serializable`
- `test_cost_limit_error_attributes` — `accumulated`, `ceiling`, `workflow_id` present and correct

**AC covered**: AC-004

---

### TASK-003: DeterministicNodes — fetch_company_state and fetch_active_events · M/TDD · src/ai/workflows/on_demand/nodes/fetch_company_state.py,src/ai/workflows/on_demand/nodes/fetch_active_events.py,src/ai/workflows/on_demand/__init__.py,src/ai/workflows/on_demand/nodes/__init__.py,tests/unit/ai/workflows/test_fetch_company_state.py,tests/unit/ai/workflows/test_fetch_active_events.py

Implement the two opening DeterministicNodes as pure `(state: WorkflowState) -> WorkflowState` functions. `fetch_company_state` calls the storage repositories to populate `state.company_state` with: company fundamentals, current portfolio position (if any), latest `company_score` entries. `fetch_active_events` queries `geo_event` joined through `event_exposure` to populate `state.active_events` with events in the last 30 days where `event_exposure.company_id = state.company_id`, capped at 50 rows (Architecture §7.3 Tool Library bounded output). Both nodes must be agnostic of the Celery task — they accept only `WorkflowState` and injected repository dependencies, never a Celery task reference. Repository dependencies are injected via constructor arguments to a `NodeContext` dataclass that is built once per task invocation and passed through the graph via LangGraph's configurable state.

**Tests to write first (TDD):**
- `test_fetch_company_state_populates_company_state` — mock repository returns company fixture; node sets `state.company_state`
- `test_fetch_company_state_company_not_found_raises` — repository returns `None`; node raises `CompanyNotFoundError`
- `test_fetch_company_state_scoped_to_tenant` — asserts repository called with `tenant_id`
- `test_fetch_active_events_populates_active_events` — mock repository returns event list; node sets `state.active_events`
- `test_fetch_active_events_empty_result_sets_empty_list` — no events is valid (not an error)
- `test_fetch_active_events_caps_at_fifty_rows` — repository returns 60 items; node trims to 50

**AC covered**: AC-001, AC-002

---

### TASK-004: AgentNode wrapper — generic AgentNode executor · M/TDD · src/ai/workflows/on_demand/nodes/exposure_analyst_node.py,src/ai/workflows/on_demand/nodes/historical_context_node.py,src/ai/workflows/on_demand/nodes/anomaly_detector_node.py,src/ai/workflows/on_demand/nodes/recommendation_node.py,src/ai/workflows/on_demand/nodes/narrative_writer_node.py,tests/unit/ai/workflows/test_exposure_analyst_node.py,tests/unit/ai/workflows/test_historical_context_node.py,tests/unit/ai/workflows/test_anomaly_detector_node.py,tests/unit/ai/workflows/test_recommendation_node.py,tests/unit/ai/workflows/test_narrative_writer_node.py

Implement the five AgentNode wrapper modules. Each module follows the same structural pattern: a module-level `async def <role>_node(state: WorkflowState, config: RunnableConfig) -> WorkflowState` function that: (1) retrieves the `AgentDefinition` from the injected `IAgentRegistry`; (2) calls `ToolGuard.assert_allowed` before any tool dispatch; (3) wraps the LLM call in `LangfuseInvocationLogger` (from PLAN-F-011); (4) calls `ExecutionLimiter` checks before and during the call; (5) accumulates `cost_usd` and `tokens_consumed` into `state`; (6) validates the output against `AgentDefinition.output_schema` using `jsonschema.validate`; (7) writes the output to the correct `state` field (`exposure_output`, `historical_output`, `anomaly_output`, `recommendation`, `report` respectively); (8) records a per-agent entry in `state.confidence_scores`. Each node function calls `CostCeilingGuard.check(state)` as its final step before returning. The implementation must use `asyncio.gather` for any parallel sub-tasks within a node (e.g., Historical Context Agent querying multiple events simultaneously — each as a sibling Langfuse span).

**Tests to write first (TDD):**
- For each of the five nodes:
  - `test_<role>_node_populates_correct_state_field` — mock agent call returns fixture; asserts correct `state.*` field is set
  - `test_<role>_node_accumulates_cost` — mock returns `cost_usd=0.10`; asserts `state.cost_usd` increases
  - `test_<role>_node_records_confidence_score` — asserts `state.confidence_scores["<role>"]` is set
  - `test_<role>_node_raises_on_invalid_output_schema` — mock returns dict missing required key; `jsonschema.ValidationError` propagates
- `test_historical_context_node_parallel_calls_use_asyncio_gather` — mock `asyncio.gather`; assert it is awaited when multiple events present

**AC covered**: AC-001, AC-002

---

### TASK-005: evaluate_quality DeterministicNode and confidence routing · M/TDD · src/ai/workflows/on_demand/nodes/evaluate_quality.py,tests/unit/ai/workflows/test_evaluate_quality.py

Implement `evaluate_quality` as a DeterministicNode. It computes `state.overall_confidence = min(state.confidence_scores.values())` (Architecture §7.2 — workflow confidence equals minimum across critical AgentNodes). It then sets `state.requires_hil` and `state.status` according to D9: if `overall_confidence ≥ 0.7` → `status = COMPLETED`, `requires_hil = False`; if `0.4 ≤ overall_confidence < 0.7` → `status = HIL_PENDING`, `requires_hil = True`, `hil_reason = "Confidence below auto-send threshold"`; if `overall_confidence < 0.4` → `status = BLOCKED`, `requires_hil = False`, `hil_reason = "Confidence too low to deliver"`. This node must handle the edge case of an empty `confidence_scores` dict by raising `EvaluateQualityError("No agent confidence scores recorded")`. This node is always second-to-last in the graph; `WorkflowStructureValidator` (PLAN-F-011) enforces this at build time.

**Tests to write first (TDD):**
- `test_evaluate_quality_high_confidence_sets_completed` — `confidence_scores = {"exposure": 0.8, "recommendation": 0.9}` → `status = COMPLETED`, `requires_hil = False`
- `test_evaluate_quality_mid_confidence_sets_hil_pending` — min confidence 0.55 → `status = HIL_PENDING`, `requires_hil = True`
- `test_evaluate_quality_low_confidence_sets_blocked` — min confidence 0.3 → `status = BLOCKED`
- `test_evaluate_quality_uses_minimum_not_average` — scores `[0.9, 0.9, 0.35]` → `overall_confidence = 0.35`
- `test_evaluate_quality_empty_scores_raises` — `confidence_scores = {}` → `EvaluateQualityError`
- `test_evaluate_quality_boundary_0_7_inclusive_is_completed` — score exactly 0.7 → `COMPLETED`
- `test_evaluate_quality_boundary_0_4_inclusive_is_hil_pending` — score exactly 0.4 → `HIL_PENDING`

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-006: Graph builder — build_on_demand_graph with LangGraph StateGraph and PostgreSQL checkpointing · L/TDD · src/ai/workflows/on_demand/graph.py,tests/unit/ai/workflows/test_on_demand_graph.py,tests/integration/ai/test_on_demand_workflow_happy_path.py,tests/integration/ai/test_on_demand_workflow_cost_limit.py,tests/integration/ai/test_on_demand_workflow_confidence_routing.py

Implement `build_on_demand_graph` per the contract in Component Design. The function constructs a `StateGraph(WorkflowState)`, adds all eight nodes in order, adds conditional edges from `evaluate_quality` to route on `state.status` (`COMPLETED` → end, `HIL_PENDING` → end, `BLOCKED` → end, `COST_LIMIT` → end), and compiles with the `pg_checkpointer`. Before returning the compiled graph, the function calls `WorkflowStructureValidator().validate(node_sequence())`. An error edge from any node to a `_handle_error` DeterministicNode catches `WorkflowCostLimitError` and `WorkflowTimeoutError`, sets the appropriate `state.status`, and routes to the end node so the graph always terminates cleanly. The compiled graph is cached at module level (constructed once at Celery worker startup) to avoid repeated database connections.

**Tests to write first (TDD):**
- `test_graph_has_correct_node_count` — compiled graph has exactly eight nodes plus the error handler
- `test_graph_structure_validator_called_at_build` — mock `WorkflowStructureValidator`; assert `validate` is called with `node_sequence()`
- `test_graph_build_fails_on_invalid_node_sequence` — pass a tampered `node_sequence` that puts `narrative_writer` before `evaluate_quality`; `WorkflowStructureError` raised
- Integration: `test_on_demand_workflow_happy_path` — run the full compiled graph with mocked agent calls returning confidence 0.8; assert `state.status == COMPLETED` and `state.report` is populated
- Integration: `test_on_demand_workflow_cost_limit` — third agent call accumulates cost to $1.51; assert `state.status == COST_LIMIT` and `state.error_detail` non-null
- Integration: `test_on_demand_workflow_confidence_routing_hil` — all agents return confidence 0.55; assert `state.status == HIL_PENDING` and `state.requires_hil == True`

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-007: Celery task — on_demand_analysis_task with timeout enforcement · M/TDD · src/ai/workflows/on_demand/tasks.py,src/config/celery_app.py,tests/unit/ai/workflows/test_on_demand_task.py

Implement `on_demand_analysis_task` per the contract in Component Design. The task: (1) opens a `LangfuseWorkflowTracer` root trace; (2) constructs `WorkflowState` from the task arguments; (3) creates the `workflow_run` DB row via `WorkflowRunRepository`; (4) invokes the compiled graph via `graph.invoke(state, config={"configurable": {"thread_id": str(workflow_id)}})`; (5) persists the final state to `workflow_run.final_state` and updates `workflow_run.status`; (6) emits a WebSocket notification to the connected client via `WorkflowNotifier.notify(workflow_id, final_state)`; (7) catches `SoftTimeLimitExceeded` from Celery, sets `state.status = TIMEOUT`, persists, and notifies. The Celery task is registered with `time_limit=360` (6 min hard) and `soft_time_limit=300` (5 min soft). `max_retries=0` — on-demand tasks must not auto-retry because the user is actively waiting. Register the task in `src/config/celery_app.py`.

**Tests to write first (TDD):**
- `test_task_creates_workflow_run_row` — mock graph and repository; assert `repository.create` called with correct `workflow_id`
- `test_task_updates_status_on_completion` — mock graph returns `COMPLETED` state; assert `repository.update_status(status=COMPLETED)` called
- `test_task_handles_soft_time_limit_exceeded` — patch `graph.invoke` to raise `SoftTimeLimitExceeded`; assert `status = TIMEOUT` persisted
- `test_task_opens_langfuse_trace` — mock tracer; assert root trace opened with `workflow_type="on_demand"`
- `test_task_notifies_websocket_on_completion` — mock notifier; assert `notify(workflow_id, state)` called

**AC covered**: AC-001, AC-002

---

### TASK-008: FastAPI trigger endpoint and workflow-run status endpoint · M/TDD · src/api/routers/workflow_router.py,src/api/websocket/workflow_notifier.py,tests/integration/api/test_workflow_router.py

Implement two endpoints per the contracts in Component Design.

`POST /api/v1/companies/{company_id}/analysis`: validates that the authenticated user's tenant owns the company (IDOR guard), validates that the company exists, creates a `workflow_run` record with `status=RUNNING`, enqueues `on_demand_analysis_task.delay(...)`, and returns `202 Accepted` with `{ "data": { "run_id": "<uuid>", "status": "RUNNING" }, "error": null }`. The endpoint must enforce rate limiting: one active analysis per company per user at a time (checked against `workflow_run` rows with `status=RUNNING`).

`GET /api/v1/workflow-runs/{run_id}`: returns the current status and, if `status=COMPLETED`, the full report payload. Enforces tenant + user ownership. Returns `404` if the run does not exist for the requesting tenant.

`WorkflowNotifier` opens a WebSocket message to the client channel identified by `workflow_id` when the Celery task completes. It uses the existing WebSocket manager (Architecture §5 `api` module). If no client is connected when the notification fires (e.g., the user navigated away), the WebSocket send is a no-op (not an error).

**Tests to write first (TDD):**
- `test_trigger_endpoint_returns_202_with_run_id` — authenticated user; valid company_id; asserts 202 and `run_id` UUID in response
- `test_trigger_endpoint_requires_authentication` — unauthenticated request returns 401
- `test_trigger_endpoint_404_for_unknown_company` — non-existent company_id returns 404
- `test_trigger_endpoint_idor_guard` — company_id owned by different tenant returns 404
- `test_trigger_endpoint_rate_limit_one_active_analysis` — second trigger while first is RUNNING returns 409
- `test_status_endpoint_returns_running_state` — workflow in RUNNING state; response includes status
- `test_status_endpoint_returns_completed_report` — workflow COMPLETED; report payload included in response
- `test_status_endpoint_404_wrong_tenant` — another tenant's run_id returns 404

**AC covered**: AC-001, AC-002, AC-005

---

### TASK-009: HIL fallback task — deliver with low-confidence banner after 10 minutes · S/no-TDD · src/ai/workflows/on_demand/hil/fallback_task.py,src/ai/workflows/on_demand/hil/__init__.py,src/config/celery_app.py

Implement `hil_fallback_check_task` as a Celery beat task that runs every 60 seconds. It queries `workflow_run` for rows where `status = HIL_PENDING` and `started_at < NOW() - 10 minutes`. For each such row it: (1) logs an audit entry in the AI audit log; (2) updates `workflow_run.status` to `COMPLETED` with a `low_confidence_banner=True` flag in `final_state`; (3) notifies the frontend via `WorkflowNotifier` with the report plus a banner payload. This task implements the Architecture §7.6 on-demand HIL fallback: "if unreviewed in 10 min, deliver with low-confidence banner." Register the beat schedule in `src/config/celery_app.py` with a 60-second interval. This is an S-complexity task (simple query + state update) and does not require TDD.

**AC covered**: AC-003

---

### TASK-010: ai_recommendation persistence and analysis history storage · M/TDD · src/storage/repositories/ai_recommendation_repository.py,src/storage/repositories/interfaces.py,tests/unit/ai/workflows/test_on_demand_graph.py,tests/integration/api/test_workflow_router.py

Implement `IAiRecommendationRepository` protocol and `AiRecommendationRepository`. The repository exposes: `save(state: WorkflowState) -> UUID` — maps `WorkflowState.recommendation` fields to the `ai_recommendation` row per the data model in REQ-F-007 and Architecture §10 (populates `event_id=None` for on-demand runs, `company_id`, `action_signal`, `direction`, `confidence`, `sample_size`, `rationale`, `forecast`, `analogies`, `model_version`, `workflow_run_id`). `list_for_company(company_id: UUID, tenant_id: UUID, limit: int = 10) -> list[AiRecommendation]` — returns the N most-recent analyses for a company, scoped to the tenant, used by the Company Detail screen to populate the analysis history panel. The `save` method is called from within `on_demand_analysis_task` after the graph completes with `status=COMPLETED` or `HIL_PENDING`.

**Tests to write first (TDD):**
- `test_save_creates_ai_recommendation_row` — integration: saves state fixture; asserts row exists with correct `company_id` and `confidence`
- `test_save_sets_workflow_run_id` — asserts `workflow_run_id` FK is set correctly
- `test_list_for_company_returns_ordered_by_generated_at_desc` — insert three rows with different timestamps; assert correct order
- `test_list_for_company_scoped_to_tenant` — another tenant's recommendations are not returned
- `test_list_for_company_respects_limit` — 15 rows exist; `limit=10` returns exactly 10

**AC covered**: AC-005

---

### TASK-011: Langfuse root trace — LangfuseWorkflowTracer · M/TDD · src/ai/workflows/tracer.py,tests/unit/ai/workflows/test_tracer.py

Implement `LangfuseWorkflowTracer` as a context manager. On `__enter__` it opens a Langfuse root trace with metadata: `workflow_id`, `workflow_type`, `tenant_id`, `user_id`, `started_at`. It stores the trace ID in `state.langfuse_trace_id` and attaches the trace to the Langfuse SDK thread-local context so that `LangfuseInvocationLogger` spans from PLAN-F-011 are automatically child spans. On `__exit__` it records `cost_usd`, `status`, `tokens_consumed`, and closes the trace. When `LANGFUSE_HOST` is not set or the Langfuse client is `None`, the tracer must no-op silently (same pattern as `LangfuseInvocationLogger` in PLAN-F-011). The Langfuse client is injected as a constructor argument.

**Tests to write first (TDD):**
- `test_tracer_opens_root_trace_with_metadata` — mock Langfuse client; assert `trace()` called with `workflow_id`, `workflow_type`, `tenant_id`, `user_id`
- `test_tracer_sets_langfuse_trace_id_on_state` — assert `state.langfuse_trace_id` is populated after `__enter__`
- `test_tracer_closes_trace_on_exit` — assert mock trace `.update()` called with `cost_usd` and `status` on `__exit__`
- `test_tracer_noop_when_client_is_none` — no exception when client is `None`
- `test_tracer_records_status_on_exit`

**AC covered**: AC-001 (REQ-N-008 compliance)

---

## Acceptance Criteria Coverage

- AC-001: Given a user clicks "On-Demand Analysis", a LangGraph workflow is initiated, a loading state displayed, report delivered within 4 min (p95); if not within 6 min the Celery task is hard-terminated and the user sees an error state → TASK-007, TASK-008, TASK-006
- AC-002: Given the workflow completes, the report includes action signal, confidence score, sample_size, historical analogies, exposure analysis, and anomaly assessment → TASK-003, TASK-004, TASK-005, TASK-006, TASK-010
- AC-003: Given confidence < 0.4, the UI displays "unable to generate confident analysis" and the run is recorded in the admin AI audit console → TASK-005, TASK-006, TASK-009
- AC-004: Given the total workflow cost exceeds $1.50, the workflow is terminated by the cost ceiling guard and the user sees a partial-results message → TASK-002, TASK-006
- AC-005: Given the analysis completes, it is stored in the company's AI analysis history and visible on subsequent Company Detail views → TASK-001, TASK-008, TASK-010

## Acceptance Notes

The confidence < 0.4 case (AC-003) writes to the admin AI audit console. The audit console UI is delivered by PLAN-F-029. For this plan's scope, "recorded in the admin AI audit console" means a structured `workflow_run` row with `status=BLOCKED` and `final_state.hil_reason` populated — the UI reads from this row. No additional audit table is needed.

The frontend loading state and real-time result delivery (AC-001) depend on the WebSocket manager from the `api` module. This plan introduces `WorkflowNotifier` which calls into the existing WebSocket infrastructure — it does not re-implement WebSocket plumbing.

## Open Questions Inherited
| # | Question | Resolution |
|---|----------|-----------|
| 1 | What output schema does the Recommendation Synthesizer produce for on-demand vs morning-brief runs? | The `ai_recommendation` schema in the requirement data model is authoritative. The `output_schema` key in `recommendation-synthesizer.yaml` (PLAN-F-011, TASK-002) must match this schema. No divergence between workflows. |

## Risks and Notes
- The graph node sequence in `node_sequence()` lists `narrative_writer` before `evaluate_quality` as AgentNodes — but `evaluate_quality` is a DeterministicNode that runs after `narrative_writer` in the LangGraph edge ordering. The `WorkflowStructureValidator` from PLAN-F-011 validates the LangGraph node sequence (edges), not the Python function call order within a node. TASK-006 must ensure LangGraph edges are wired so `narrative_writer` executes before `evaluate_quality` in the compiled graph, matching Architecture §7.1 invariant: "evaluate_quality is always the second-to-last node; Narrative Writer is always the last AgentNode."
- PostgreSQL checkpointing (LangGraph `PostgresSaver`) shares the application database. The `langgraph_checkpoints` table must be created by migration before any workflow is invoked. This migration should be added to `src/storage/migrations/` as part of TASK-006.
- `CostCeilingGuard.check` is called after every AgentNode. If the Celery soft time limit fires mid-node (inside an `await`), the guard may not have had a chance to run. The Celery `SoftTimeLimitExceeded` handler in `on_demand_analysis_task` (TASK-007) is the safety net for the timeout case; the cost guard is the safety net for the cost case. Both must be present.
- `max_retries=0` on the Celery task is intentional: an on-demand task that fails silently and retries would deliver a stale result to an actively-waiting user. If PLAN-F-013 (HIL Review Queue) introduces a replay mechanism later, it should be implemented as a separate Celery task submission, not as Celery auto-retry.
- PLAN-F-012 (Agent Tool Library) must exist before the AgentNode wrappers in TASK-004 can make real tool calls. For the integration tests introduced in TASK-006, agent calls are mocked at the LangGraph node level. Full end-to-end testing with real tool calls is scoped to PLAN-F-012.
