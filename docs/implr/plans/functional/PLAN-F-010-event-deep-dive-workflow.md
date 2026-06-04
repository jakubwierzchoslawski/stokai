---
plan_id: PLAN-F-010
slug: event-deep-dive-workflow
title: Event Deep-Dive Workflow (Mode B — Workflow 5)
linked_requirement: REQ-F-010
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-002, reason: "Event Deep-Dive workflow must complete within 7 minutes (target) / 15 minutes (hard limit)" }
  - { id: REQ-N-004, reason: "Per-memo cost ceiling of $2.00 enforced at workflow and per-agent level" }
  - { id: REQ-N-008, reason: "One Langfuse trace per workflow run; parallel Exposure Analyst calls are sibling spans within that trace" }
dependencies:
  - { id: PLAN-F-001, reason: "Mode A step 11 (enqueue_deep_dive) is the sole trigger; the WorkflowQueue interface and enqueue contract are defined there" }
  - { id: PLAN-F-011, reason: "AgentRegistry, ExecutionLimiter, LangfuseInvocationLogger, and the event_deep_dive_agent YAML definition must exist before this workflow graph can be built" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-010 — Event Deep-Dive Workflow (Mode B — Workflow 5)

## Linked Requirement
**REQ-F-010** — Event Deep-Dive Workflow (Mode B)
Status: approved | Jira: —

## Objective

Build Workflow 5 — Event Deep-Dive as a LangGraph `StateGraph` hosted inside a Celery task inside the `ai` backend module. When Mode A step 11 detects intensity ≥ 4 or a portfolio match it enqueues a Celery task with a 2-minute ETA. On execution the graph runs eight nodes in order: `fetch_event_full` (DeterministicNode) → `fetch_market_reaction_so_far` (DeterministicNode) → `run_exposure_analysts` (DeterministicNode, fans out to the `exposure_analyst` AgentNode via `asyncio.gather` — one call per affected company) → `event_deep_dive_agent` (AgentNode, Opus 4.7) → `historical_context_agent` (AgentNode, Opus 4.7) → `recommendation_synthesizer` (AgentNode, Opus 4.7) → `narrative_writer` (AgentNode, Opus 4.7) → `evaluate_quality` (DeterministicNode). After `evaluate_quality` a conditional edge branches to: auto-store (confidence ≥ 0.7), HIL queue (0.4–0.69), or blocked/episodic-log-only (< 0.4). A separate timer branch enforces the 30-minute HIL fallback (send with low-confidence banner if unreviewed). Every `workflow_run` row carries a `cost_usd` accumulator; when the $2.00 ceiling is hit mid-run the graph raises `CostCeilingExceededError`, stores a partial memo flagged `cost_limited`, and exits. All state transitions are checkpointed to PostgreSQL so any failure can resume from the last completed node. One Langfuse trace covers the full run; the `asyncio.gather` fan-out produces sibling Langfuse spans.

## Architecture Context

This plan operates in **Layer 4 — Processing** and touches the following modules (Architecture §5):

- **`src/ai/`** — primary owner: LangGraph `StateGraph` definition, Celery task entry point, `DeepDiveWorkflowState` Pydantic model, `CostAccumulator`, node implementations, PostgreSQL checkpointer setup, HIL router, and Langfuse trace wiring. All agent invocations go through `AgentRegistry.resolve()` (defined in PLAN-F-011).
- **`src/storage/`** — new repository interfaces and SQLAlchemy implementations: `WorkflowRunRepository` (upsert run row, update status/cost), `BriefRepository` (insert memo, query by event_id), `EventExposureRepository` (read affected companies for fan-out), `GeoEventRepository` (read full event row). The `storage` module is also where LangGraph's PostgreSQL checkpoint saver is wired.
- **`src/events/`** — the `enqueue_deep_dive` step 11 function (defined in PLAN-F-001) calls `WorkflowQueue.enqueue()`; this plan defines the Celery task that `WorkflowQueue` dispatches to.
- **`src/api/`** — one new read endpoint: `GET /api/v1/events/{event_id}/memo` returns the memo artifact if available.

Architectural invariants (Architecture §7.1) enforced by this plan:
- `evaluate_quality` is the second-to-last node (before the branch, after `narrative_writer`).
- `narrative_writer` is the last `AgentNode`.
- Bounded execution limits are read from the agent YAML files via `AgentRegistry` — never hardcoded.
- Every agent node is wrapped by `ExecutionLimiter` and `LangfuseInvocationLogger` from PLAN-F-011.
- Confidence thresholds: ≥ 0.7 auto-store, 0.4–0.69 HIL, < 0.4 blocked (D9).
- The 30-minute unreviewed fallback sends with a low-confidence banner (Architecture §7.6).

The `WorkflowState` base class (Architecture §7.1) is extended with memo-specific fields to form `DeepDiveWorkflowState`. PostgreSQL checkpointing (Architecture §7.1) uses the same `langgraph-checkpoint-postgres` adapter used across all Mode B workflows.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-002 | Event Deep-Dive ≤ 7 min target, ≤ 15 min hard limit | `WorkflowTimeoutGuard` wraps the Celery task; if the 15-minute hard limit is breached the task is terminated and a partial memo stored with `status=failed`; per-agent `timeout_seconds` values in YAML are set so the sum fits within 7 minutes on the happy path |
| REQ-N-004 | Per-memo cost ceiling $2.00 | `CostAccumulator` is updated after every agent node; if `cost_usd >= 2.00` the graph raises `CostCeilingExceededError` before the next node; a partial memo is stored with `cost_limited=True` and `status=cost_limited`; the admin view exposes the flag |
| REQ-N-008 | One Langfuse trace per workflow; parallel agent calls as sibling spans | `LangfuseTracer.start_workflow_trace()` is called in the Celery task before the graph runs; the `run_exposure_analysts` node passes the parent trace context to each `asyncio.gather` coroutine so each `exposure_analyst` call creates a sibling span under the same trace; the trace is flushed after `evaluate_quality` and the branch |

## Component Design

### New Components

```
Package: src/ai/workflows/event_deep_dive/
  ├── __init__.py
  ├── graph.py                  — LangGraph StateGraph definition; node wiring; edge conditions
  ├── state.py                  — DeepDiveWorkflowState(WorkflowState): adds memo, exposure_analyses,
  │                               event_full, market_reaction, cost_limited fields
  ├── nodes/
  │   ├── __init__.py
  │   ├── fetch_event_full.py         — DeterministicNode: load full geo_event + event_exposure rows
  │   ├── fetch_market_reaction.py    — DeterministicNode: call get_price_reaction_to_event tool;
  │   │                                 returns market_reaction dict keyed by company_id
  │   ├── run_exposure_analysts.py    — DeterministicNode: asyncio.gather fan-out; one
  │   │                                 exposure_analyst AgentNode call per affected company;
  │   │                                 each call is a sibling Langfuse span
  │   ├── event_deep_dive_agent.py    — AgentNode wrapper: resolves agent via AgentRegistry;
  │   │                                 enforces ExecutionLimiter; receives state, returns analysis
  │   ├── historical_context_agent.py — AgentNode wrapper: finds analogies for this event via
  │   │                                 find_similar_events + compute_event_outcome_statistics tools
  │   ├── recommendation_synthesizer.py — AgentNode wrapper: produces per-company recommendations
  │   │                                   with action_signal + confidence
  │   ├── narrative_writer.py         — AgentNode wrapper: last AgentNode; converts structured
  │   │                                 output to FT-columnist-voice memo prose
  │   └── evaluate_quality.py         — DeterministicNode: computes workflow_confidence =
  │                                     min(agent confidences); sets requires_hil; sets cost_limited
  ├── routing.py                — conditional_edge function: auto_store | hil_queue | blocked
  ├── cost_accumulator.py       — CostAccumulator: running total; raises CostCeilingExceededError
  ├── timeout_guard.py          — WorkflowTimeoutGuard: asyncio timeout wrapper for Celery task
  ├── exceptions.py             — CostCeilingExceededError, WorkflowTimeoutError
  └── celery_task.py            — run_event_deep_dive(event_id: UUID): Celery task; 2-min ETA
                                  set by Mode A step 11 at enqueue time; task entry point

Package: src/ai/workflows/shared/
  ├── hil_router.py             — HILRouter: enqueue to hil_queue table; schedule 30-min fallback
  └── memo_store.py             — MemoStore: write Brief row + workflow_run update in one transaction

src/storage/repositories/
  ├── workflow_run_repository.py — IWorkflowRunRepository interface + SQLAlchemy implementation
  ├── brief_repository.py        — IBriefRepository interface + SQLAlchemy implementation
  │                                (includes cost_limited flag, confidence, content JSONB)
  └── (geo_event and event_exposure repositories assumed from PLAN-F-001)

src/api/routes/memos.py         — GET /api/v1/events/{event_id}/memo → MemoResponse DTO

agents/event_deep_dive_agent.yaml  — agent YAML (owned by PLAN-F-011 scope; this plan adds
                                     budget allocation comments and verifies limits sum ≤ $2.00)
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/workflows/__init__.py` | Register `event_deep_dive` workflow type in the workflow registry | Allow WorkflowQueue to dispatch to the correct Celery task |
| `src/config/celery_app.py` | Include `src.ai.workflows.event_deep_dive.celery_task` in task autodiscovery | Celery worker must find the task at startup |
| `src/storage/repositories/__init__.py` | Export new repository interfaces | Other modules import via the storage abstraction |

### Interfaces and Contracts

```python
# state.py
class DeepDiveWorkflowState(WorkflowState):
    event_full: GeoEvent | None = None
    market_reaction: dict[UUID, PriceReaction] = {}
    exposure_analyses: list[ExposureAnalysis] = []
    memo_draft: MemoDraft | None = None        # set by narrative_writer
    cost_limited: bool = False

# graph.py — node names match Architecture §7.5 Workflow 5 exactly
GRAPH_NODES = [
    "fetch_event_full",           # DeterministicNode
    "fetch_market_reaction_so_far",  # DeterministicNode
    "run_exposure_analysts",      # DeterministicNode (asyncio.gather fan-out)
    "event_deep_dive_agent",      # AgentNode (Opus 4.7)
    "historical_context_agent",   # AgentNode (Opus 4.7)
    "recommendation_synthesizer", # AgentNode (Opus 4.7)
    "narrative_writer",           # AgentNode (Opus 4.7) — last AgentNode (invariant)
    "evaluate_quality",           # DeterministicNode — second-to-last node (invariant)
]

# routing.py
def route_after_evaluate(state: DeepDiveWorkflowState) -> Literal["auto_store", "hil_queue", "blocked"]:
    if state.confidence_scores["workflow"] >= 0.70:
        return "auto_store"
    if state.confidence_scores["workflow"] >= 0.40:
        return "hil_queue"
    return "blocked"

# celery_task.py
@celery_app.task(name="ai.event_deep_dive", queue="mode_b")
def run_event_deep_dive(event_id: str) -> dict:
    ...

# brief_repository.py
class IBriefRepository(Protocol):
    async def insert_memo(self, brief: BriefCreate) -> Brief: ...
    async def get_by_event_id(self, event_id: UUID) -> Brief | None: ...
    async def mark_hil_reviewed(self, brief_id: UUID, approved: bool) -> None: ...

# workflow_run_repository.py
class IWorkflowRunRepository(Protocol):
    async def create(self, run: WorkflowRunCreate) -> WorkflowRun: ...
    async def update_status(self, workflow_id: UUID, status: WorkflowStatus,
                             cost_usd: float, confidence: float | None) -> None: ...

# memo_store.py
class MemoStore:
    async def persist(
        self,
        state: DeepDiveWorkflowState,
        workflow_run_repo: IWorkflowRunRepository,
        brief_repo: IBriefRepository,
        confidence: float,
        cost_limited: bool,
    ) -> Brief: ...
```

## Implementation Tasks

### TASK-001: DeepDiveWorkflowState and data transfer models · S/no-TDD · src/ai/workflows/event_deep_dive/state.py, src/ai/workflows/event_deep_dive/__init__.py

Define `DeepDiveWorkflowState` extending the base `WorkflowState` from Architecture §7.1 with the memo-specific fields: `event_full`, `market_reaction`, `exposure_analyses`, `memo_draft`, and `cost_limited`. Define Pydantic models `MemoDraft`, `PriceReaction`, `ExposureAnalysis`, and `BriefCreate` with all required fields and validators. All fields use strict typing; no `Any` except where Architecture forces it (`WorkflowState.inputs`).

**AC covered**: AC-002 (state carries all memo content fields), AC-003 (cost_limited and confidence fields present for enforcement)

---

### TASK-002: Repository interfaces and SQLAlchemy implementations for workflow_run and brief · M/TDD · src/storage/repositories/workflow_run_repository.py, src/storage/repositories/brief_repository.py, src/storage/repositories/__init__.py, tests/unit/storage/test_brief_repository.py, tests/unit/storage/test_workflow_run_repository.py

Implement `IWorkflowRunRepository` and `IBriefRepository` Protocol interfaces. Provide `SQLAlchemyWorkflowRunRepository` and `SQLAlchemyBriefRepository` concrete implementations against the `workflow_run` and `report/brief` tables defined in the Data Model section of the requirement. `BriefCreate` carries `type="event_deep_dive"`, `event_id`, `content` (JSONB), `confidence`, `cost_usd`, and `cost_limited` bool. `workflow_run.status` is the enum `pending | running | completed | failed | cost_limited`. All queries include `tenant_id` in the WHERE clause (Architecture §12.3 multi-tenancy).

**Tests to write first (TDD)**:
- `test_insert_memo_returns_brief_with_id` — happy path
- `test_get_by_event_id_returns_none_when_absent`
- `test_get_by_event_id_returns_brief_when_present`
- `test_create_workflow_run_sets_status_pending`
- `test_update_status_to_cost_limited_sets_flag`
- `test_tenant_isolation_prevents_cross_tenant_read` — asserts a second tenant cannot retrieve the first tenant's brief

**AC covered**: AC-004 (memo stored, linked to geo_event), AC-005 (cost_limited flag visible)

---

### TASK-003: CostAccumulator and WorkflowTimeoutGuard · M/TDD · src/ai/workflows/event_deep_dive/cost_accumulator.py, src/ai/workflows/event_deep_dive/timeout_guard.py, src/ai/workflows/event_deep_dive/exceptions.py, tests/unit/ai/workflows/test_cost_accumulator.py, tests/unit/ai/workflows/test_timeout_guard.py

`CostAccumulator` is a mutable dataclass holding `total_usd: float` and `ceiling_usd: float`. Its `add(amount: float) -> None` method raises `CostCeilingExceededError` immediately if `total_usd + amount >= ceiling_usd` before adding. This prevents any agent from starting once the budget is exhausted. `WorkflowTimeoutGuard` is an `asyncio.timeout` context-manager wrapper that raises `WorkflowTimeoutError` after a configurable `hard_limit_seconds`. Both exceptions carry structured metadata (cost accumulated, elapsed seconds) for the partial-memo handler.

**Tests to write first (TDD)**:
- `test_add_below_ceiling_succeeds`
- `test_add_at_ceiling_raises_cost_ceiling_exceeded`
- `test_add_above_ceiling_raises_cost_ceiling_exceeded`
- `test_accumulated_total_increments_correctly`
- `test_timeout_guard_raises_after_deadline` — uses `asyncio.sleep` mock

**AC covered**: AC-003 (cost ceiling $2.00 enforced), AC-005 (cost_limited flag on partial memo)

---

### TASK-004: DeterministicNode — fetch_event_full · S/no-TDD · src/ai/workflows/event_deep_dive/nodes/fetch_event_full.py

Implement the `fetch_event_full` node. It reads the `event_id` from `state.inputs["event_id"]`, fetches the full `GeoEvent` row via `GeoEventRepository`, fetches all associated `event_exposure` rows via `EventExposureRepository`, and writes `state.event_full` and populates `state.events` list. Raises `WorkflowInputError` if the event_id resolves to no row (defensive guard for orphaned Celery messages). No LLM call.

**AC covered**: AC-001 (workflow initialised from geo_event context), AC-002 (event context available to agents)

---

### TASK-005: DeterministicNode — fetch_market_reaction_so_far · S/no-TDD · src/ai/workflows/event_deep_dive/nodes/fetch_market_reaction.py

Implement the `fetch_market_reaction_so_far` node. Calls the `get_price_reaction_to_event` tool (from the Tool Library, PLAN-F-012 scope) for each exposed company. Writes `state.market_reaction` as a `dict[UUID, PriceReaction]`. If the market is not yet open (event occurred outside trading hours), stores empty reactions rather than failing — the 2-minute delay means real market data may not yet exist. No LLM call.

**AC covered**: AC-002 (exposure analysis available to agents)

---

### TASK-006: DeterministicNode — run_exposure_analysts (asyncio.gather fan-out) · M/TDD · src/ai/workflows/event_deep_dive/nodes/run_exposure_analysts.py, tests/unit/ai/workflows/test_run_exposure_analysts.py

Implement the `run_exposure_analysts` fan-out node. For each company in `state.event_full.exposures`, create a coroutine that invokes the `exposure_analyst` AgentNode (Sonnet 4.6) via `AgentRegistry.resolve("exposure_analyst")`. Gather all coroutines with `asyncio.gather`. Each coroutine receives its own Langfuse span as a sibling of the workflow trace (pass `parent_span_id` explicitly). Each result is appended to `state.exposure_analyses`. The `CostAccumulator` is called with the cost of each completed agent call; if any call triggers `CostCeilingExceededError` the gather is cancelled and the exception propagated upward. Empty exposure list (no affected companies) is not an error — the graph continues with empty `exposure_analyses`.

**Tests to write first (TDD)**:
- `test_fan_out_produces_one_analysis_per_company` — mock AgentRegistry to return stub results
- `test_fan_out_with_empty_exposures_returns_empty_list`
- `test_fan_out_propagates_cost_ceiling_exceeded`
- `test_each_coroutine_receives_sibling_span_context` — asserts `parent_span_id` is passed to each mock call

**AC covered**: AC-002 (exposure analysis per affected company), REQ-N-008 (sibling spans)

---

### TASK-007: AgentNode wrappers — event_deep_dive_agent, historical_context_agent, recommendation_synthesizer, narrative_writer · M/TDD · src/ai/workflows/event_deep_dive/nodes/event_deep_dive_agent.py, src/ai/workflows/event_deep_dive/nodes/historical_context_agent.py, src/ai/workflows/event_deep_dive/nodes/recommendation_synthesizer.py, src/ai/workflows/event_deep_dive/nodes/narrative_writer.py, tests/unit/ai/workflows/test_agent_nodes.py

Implement the four sequential AgentNode wrappers. Each follows the same pattern: (1) call `AgentRegistry.resolve(role_id)` to get `AgentDefinition`; (2) build a typed input from the current `WorkflowState` fields; (3) invoke via `ExecutionLimiter` (from PLAN-F-011); (4) update `state` fields with the structured output; (5) call `cost_accumulator.add(result.cost_usd)`; (6) update `state.confidence_scores[role_id]`. `narrative_writer` sets `state.memo_draft` and is the last AgentNode (Architecture §7.1 invariant). The `event_deep_dive_agent` receives the `event_full`, `market_reaction`, and `exposure_analyses` serialised to JSON within the token limit.

**Tests to write first (TDD)**:
- `test_event_deep_dive_agent_updates_state_with_analysis`
- `test_historical_context_agent_updates_analogies`
- `test_recommendation_synthesizer_produces_per_company_recommendations`
- `test_narrative_writer_sets_memo_draft`
- `test_any_agent_node_propagates_cost_ceiling_exceeded`
- `test_any_agent_node_updates_confidence_scores`

**AC covered**: AC-002 (all memo content sections produced by agents), AC-003 (cost ceiling enforced per agent)

---

### TASK-008: DeterministicNode — evaluate_quality and routing · M/TDD · src/ai/workflows/event_deep_dive/nodes/evaluate_quality.py, src/ai/workflows/event_deep_dive/routing.py, tests/unit/ai/workflows/test_evaluate_quality.py, tests/unit/ai/workflows/test_routing.py

Implement the `evaluate_quality` DeterministicNode. It computes `workflow_confidence = min(state.confidence_scores.values())` (Architecture §7.2 workflow confidence = minimum across critical AgentNodes). It writes `state.confidence_scores["workflow"]` and sets `state.requires_hil = True` when confidence is in the 0.4–0.69 range. It also sets `state.cost_limited` from the accumulator if the graph reached this node after a `CostCeilingExceededError` was caught by the graph's error handler. Implement the `route_after_evaluate` conditional edge function that returns `"auto_store"`, `"hil_queue"`, or `"blocked"` per D9.

**Tests to write first (TDD)**:
- `test_confidence_is_minimum_of_all_agent_scores`
- `test_confidence_above_threshold_sets_no_hil`
- `test_confidence_in_hil_range_sets_requires_hil`
- `test_confidence_below_block_threshold_returns_blocked`
- `test_route_auto_store_at_0_70`
- `test_route_hil_queue_at_0_69`
- `test_route_hil_queue_at_0_40`
- `test_route_blocked_at_0_39`

**AC covered**: AC-004 (confidence ≥ 0.7 → auto-store without user action), AC-003 (workflow terminates correctly on cost limit)

---

### TASK-009: MemoStore — persist memo and update workflow_run atomically · M/TDD · src/ai/workflows/shared/memo_store.py, tests/unit/ai/workflows/test_memo_store.py

Implement `MemoStore.persist()`. It writes the `Brief` row and updates the `workflow_run` row to `completed` (or `cost_limited`) in a single SQLAlchemy transaction. If the transaction fails, neither row is committed. It also links the brief to `geo_event` by setting `brief.event_id`. The `cost_limited` bool on the `Brief` row comes from `state.cost_limited`. After successful commit it returns the `Brief` ORM object.

**Tests to write first (TDD)**:
- `test_persist_writes_brief_and_updates_workflow_run`
- `test_persist_sets_cost_limited_flag_when_true`
- `test_persist_links_brief_to_event_id`
- `test_persist_rolls_back_on_db_error` — simulate constraint violation; verify no partial commit

**AC covered**: AC-004 (memo stored and linked to geo_event), AC-005 (cost_limited flag stored)

---

### TASK-010: LangGraph StateGraph — graph assembly and PostgreSQL checkpointing · L/TDD · src/ai/workflows/event_deep_dive/graph.py, tests/integration/ai/workflows/test_deep_dive_graph.py

Assemble the full `StateGraph(DeepDiveWorkflowState)`. Add all eight nodes in order. Add directed edges between them. Add the conditional edge from `evaluate_quality` using `route_after_evaluate`. Wire the `auto_store`, `hil_queue`, and `blocked` terminal branches. Configure the PostgreSQL checkpointer using `langgraph-checkpoint-postgres` pointed at `DATABASE_URL`. Compile the graph. Validate the `evaluate_quality → narrative_writer` tail invariant using `WorkflowStructureValidator` from PLAN-F-011 at module import time — a misconfigured graph raises `WorkflowStructureError` at startup, not at runtime.

**Tests to write first (TDD)**:
- `test_graph_compiles_without_error`
- `test_graph_node_order_matches_architecture_spec` — asserts node sequence via compiled graph introspection
- `test_graph_evaluate_quality_is_second_to_last_node`
- `test_graph_narrative_writer_is_last_agent_node`
- `test_conditional_edge_routes_to_auto_store_on_high_confidence` — integration test with mocked agents
- `test_conditional_edge_routes_to_hil_queue_on_mid_confidence`
- `test_conditional_edge_routes_to_blocked_on_low_confidence`
- `test_checkpoint_is_written_after_each_node` — assert checkpoint table row count increments

**AC covered**: AC-001 (workflow executes after 2-minute delay and not before — tested via Celery ETA contract), AC-003 (workflow completes within budget), AC-004 (auto-store branch exists and is reachable)

---

### TASK-011: Celery task — run_event_deep_dive with timeout enforcement · M/TDD · src/ai/workflows/event_deep_dive/celery_task.py, src/config/celery_app.py, tests/unit/ai/workflows/test_celery_task.py

Implement the `run_event_deep_dive(event_id: str)` Celery task. It is decorated with `@celery_app.task(name="ai.event_deep_dive", queue="mode_b")`. The task body: (1) creates a `WorkflowRun` row with `status=running`; (2) starts the Langfuse workflow trace; (3) wraps the graph invocation in `WorkflowTimeoutGuard(hard_limit_seconds=900)`; (4) invokes the compiled graph via `graph.invoke(initial_state, config={"configurable": {"thread_id": str(workflow_id)}})`; (5) on `WorkflowTimeoutError` stores a partial memo with `status=failed`; (6) on `CostCeilingExceededError` stores a partial memo with `status=cost_limited` and `cost_limited=True`; (7) flushes the Langfuse trace. The 2-minute ETA is set by Mode A step 11 at enqueue time (`countdown=120`); this task does not re-schedule itself.

**Tests to write first (TDD)**:
- `test_task_creates_workflow_run_before_graph` — mock graph; assert repo.create called first
- `test_task_handles_workflow_timeout_and_stores_failed_status`
- `test_task_handles_cost_ceiling_and_stores_cost_limited_status`
- `test_task_flushes_langfuse_trace_on_success`
- `test_task_flushes_langfuse_trace_on_error` — assert flush called even when graph raises

**AC covered**: AC-001 (task executes after 2-minute delay), AC-003 (hard timeout 15 min = 900 s enforced), AC-005 (cost_limited flag stored on ceiling breach)

---

### TASK-012: HIL fallback — 30-minute unreviewed send with low-confidence banner · M/TDD · src/ai/workflows/shared/hil_router.py, tests/unit/ai/workflows/test_hil_router.py

Implement `HILRouter`. When `route_after_evaluate` returns `"hil_queue"`: (1) insert a row in the `hil_queue` table with `scheduled_send = now() + timedelta(minutes=30)`; (2) schedule a Celery beat task `send_hil_fallback` that fires at `scheduled_send`; when the fallback task fires it checks if the queue item is still `unreviewed` — if so it calls `MemoStore.persist()` with the checkpoint-restored state and appends `{"low_confidence_banner": True}` to the memo content (Architecture §7.6). A HIL reviewer's Approve/Edit action marks the item `reviewed` before the fallback fires and triggers `MemoStore.persist()` directly without the banner.

**Tests to write first (TDD)**:
- `test_hil_router_inserts_queue_row_with_30_min_deadline`
- `test_hil_router_schedules_fallback_celery_task`
- `test_fallback_sends_with_banner_when_unreviewed`
- `test_fallback_is_suppressed_when_already_reviewed`

**AC covered**: AC-004 (memo made available without user action — both via auto-store and HIL fallback paths)

---

### TASK-013: REST endpoint — GET /api/v1/events/{event_id}/memo · S/no-TDD · src/api/routes/memos.py, src/api/routes/__init__.py

Implement `GET /api/v1/events/{event_id}/memo`. Calls `IBriefRepository.get_by_event_id()`. Returns `MemoResponse` DTO (brief_id, event_id, type, content, confidence, cost_usd, cost_limited, created_at). Returns HTTP 404 if no memo exists yet. Returns HTTP 200 with the memo if available. Authentication required (JWT middleware). Resource ownership verified: `tenant_id` from JWT must match `brief.tenant_id`. The `cost_limited` field in the response body is the admin-visible flag for AC-005.

**AC covered**: AC-004 (memo available in full analysis view), AC-005 (cost_limited visible via API)

---

### TASK-014: Langfuse trace wiring and sibling-span fan-out · M/TDD · src/ai/workflows/event_deep_dive/nodes/run_exposure_analysts.py (updated), src/ai/workflows/event_deep_dive/celery_task.py (updated), tests/unit/ai/workflows/test_langfuse_tracing.py

Wire the Langfuse trace as required by REQ-N-008. In `celery_task.py`: call `LangfuseTracer.start_workflow_trace(workflow_type="event_deep_dive", workflow_id=...)` and store the resulting `trace_id` on the `workflow_run` row (`langfuse_trace_id` column). In `run_exposure_analysts.py`: each `asyncio.gather` coroutine receives the `trace_id` and creates a child span via `langfuse_client.span(parent_id=trace_id, name=f"exposure_analyst:{company_id}")` — these are sibling spans sharing the same parent, not nested. Flush the trace after the terminal branch completes. Assert trace metadata fields: `workflow_id`, `workflow_type`, `tenant_id`, `cost_usd`, `confidence`.

**Tests to write first (TDD)**:
- `test_trace_started_at_task_entry`
- `test_trace_id_stored_on_workflow_run`
- `test_exposure_analyst_calls_are_sibling_spans` — assert each call's `parent_id` equals the workflow trace id, not a nested span id
- `test_trace_flushed_on_success`
- `test_trace_flushed_on_exception`

**AC covered**: REQ-N-008 (one Langfuse trace per workflow; parallel agent calls as sibling spans)

## Acceptance Criteria Coverage

- AC-001: Given Mode A step 11 enqueues a deep-dive job with a 2-minute delay, the Celery task executes after 2 minutes and not before → TASK-011 (Celery `countdown=120` set at enqueue, task does not start before ETA), TASK-010 (graph only invoked from within task body)
- AC-002: Given the workflow executes, a memo artifact is produced containing geopolitical context, exposure analysis for affected companies, extended historical analogies, scenario analysis, and per-company action recommendations → TASK-001 (state model carries all fields), TASK-004, TASK-005, TASK-006, TASK-007 (agent nodes produce each content section), TASK-009 (memo persisted)
- AC-003: Given the workflow runs, it completes within 7 minutes (target) and 15 minutes (hard limit), and total cost does not exceed $2.00 → TASK-003 (CostAccumulator + WorkflowTimeoutGuard), TASK-011 (900-second hard timeout in Celery task)
- AC-004: Given the memo is produced with confidence ≥ 0.7, it is stored, linked to the geo_event, and made available in the full analysis view without requiring explicit user action → TASK-008 (evaluate_quality + routing), TASK-009 (MemoStore), TASK-012 (HIL fallback for mid-confidence), TASK-013 (REST endpoint)
- AC-005: Given the cost ceiling ($2.00) is reached before completion, the workflow terminates and a partial memo is stored with a "cost-limited" flag visible to the admin → TASK-003 (CostCeilingExceededError), TASK-011 (exception handler stores partial memo with flag), TASK-002 (cost_limited column in Brief row), TASK-013 (flag returned in API response)

## Risks and Notes

- **Parallel fan-out cost spike.** The `run_exposure_analysts` fan-out calls one Exposure Analyst per affected company concurrently. A high-intensity event affecting 20+ companies could exhaust the $2.00 budget in the fan-out alone. Mitigate: cap concurrent Exposure Analyst calls to `min(len(companies), MAX_PARALLEL_EXPOSURE_CALLS)` where `MAX_PARALLEL_EXPOSURE_CALLS` defaults to 10 (configurable via env var). Log a warning when companies are capped; the capped companies are still listed in the memo but without individual deep exposure analysis.
- **Checkpoint table migration.** `langgraph-checkpoint-postgres` requires its own schema tables. These must be created via the library's `setup()` call on first run or via an Alembic migration. Confirm with PLAN-F-001 (which also uses PostgreSQL checkpointing) whether a shared migration step already exists; if so, reuse it.
- **Celery task ETA vs. clock drift.** The 2-minute delay is enforced by Celery's `countdown=120` at enqueue time. If the Celery worker is under load and the task queues for longer than 2 minutes before starting, the actual delay will exceed 2 minutes. This is acceptable per Architecture §6 — the SLA is "not before 2 minutes", not "exactly 2 minutes".
- **Partial memo on timeout.** When `WorkflowTimeoutError` is raised, the state at the last checkpoint is used to build the partial memo. If the timeout occurs before `narrative_writer` completes, the memo content will be incomplete. Store whatever partial content exists in the `content` JSONB with a `"status": "timeout"` key so the admin can distinguish timeout-partial from cost-limited-partial.
- **`evaluate_quality` + `narrative_writer` invariant ordering.** Architecture §7.1 requires `evaluate_quality` second-to-last and `narrative_writer` last AgentNode — but in this workflow `evaluate_quality` is the last *node overall* (after `narrative_writer`). The `narrative_writer` is the last `AgentNode`; `evaluate_quality` is a `DeterministicNode` and the last node in the graph before the routing branch. This satisfies both invariants simultaneously. The `WorkflowStructureValidator` from PLAN-F-011 checks both conditions at graph compile time.
- **No HIL queue table schema in this plan.** The `hil_queue` table is owned by REQ-F-013 (HIL Review Queue). TASK-012 depends on that table existing. If PLAN-F-013 is not yet executed when this plan runs, TASK-012 will encounter a missing table. Treat as a soft dependency — add a startup check and a clear error message.
