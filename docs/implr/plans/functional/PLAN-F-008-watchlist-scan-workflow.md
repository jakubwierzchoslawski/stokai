---
plan_id: PLAN-F-008
slug: watchlist-scan-workflow
title: Watchlist Scan Workflow (Mode B)
linked_requirement: REQ-F-008
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-002, reason: "Watchlist Scan must complete within 3 minutes target / 8 minutes hard limit" }
  - { id: REQ-N-004, reason: "Per-scan LLM cost ceiling is $1.00; enforced at per-agent and per-workflow levels" }
dependencies:
  - { id: PLAN-F-011, reason: "Named-role agents (Relevance Analyst, Anomaly Detector, Historical Context Agent, Recommendation Synthesizer, Narrative Writer) must be registered and operational" }
  - { id: PLAN-F-024, reason: "Portfolio and watchlist DB tables and repository layer must exist; fetch_watchlist tool depends on them" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-008 — Watchlist Scan Workflow (Mode B)

## Linked Requirement
**REQ-F-008** — Watchlist Scan Workflow (Mode B)
Status: approved | Jira:

## Objective

Implement the Watchlist Scan — Mode B Workflow 3 — as a LangGraph StateGraph hosted on Celery workers and triggered daily by Celery beat at 17:30. The workflow fetches each subscribed user's watchlist and portfolio, filters the day's geopolitical events for relevance to those specific companies, recomputes exposure scores for affected names, detects anomalies, retrieves historical analogies for high-anomaly names only, synthesizes action recommendations, writes a narrative report, and evaluates overall quality before branching on confidence. Reports with confidence ≥ 0.70 are auto-dispatched by email targeting 18:00; confidence 0.40–0.69 enters the HIL queue with a 17:45 review deadline; confidence < 0.40 is blocked and the user is notified. The per-run LLM cost ceiling is $1.00, and the target execution time is ≤ 3 minutes (hard limit 8 minutes). PostgreSQL LangGraph checkpointing ensures failure recovery and HIL pause/resume without re-running prior nodes.

## Architecture Context

This plan lives entirely within the `ai` backend module (`src/ai/`) and extends the Celery beat scheduler configuration in `src/config/celery_app.py` (Architecture §5 Backend Module Map, §7 Mode B). It introduces one new LangGraph `StateGraph` sub-package: `src/ai/workflows/watchlist_scan/`. The workflow shares the `WorkflowState` Pydantic model (Architecture §7.1), the nine named-role agents loaded from `agents/` YAML via `AgentRegistry` (Architecture §7.2, PLAN-F-011), and the Tool Library for all data access (Architecture §7.3). No direct DB calls are made from workflow nodes.

Node classification follows the binary architecture rule (Architecture §7.1):
- `DeterministicNode` — `fetch_watchlist`, `fetch_today_events`, `recompute_scores`, `evaluate_quality`, `format_email`, `dispatch`, `hil_enqueue`, `block_and_notify`.
- `AgentNode` — `Relevance Analyst`, `Anomaly Detector`, `Historical Context Agent` (conditional), `Recommendation Synthesizer`, `Narrative Writer`.

The cross-workflow structural invariant is enforced: `evaluate_quality` is the second-to-last node; `Narrative Writer` is the last `AgentNode` in the graph (Architecture §7.1). HIL timing for this workflow is 14:00–17:45 window; unreviewed items at 17:45 are held and the user is notified (Architecture §7.6). Confidence routing uses Decision D9 thresholds (Architecture §7.7). Cost governance operates at three levels: per-agent `cost_ceiling_usd` in YAML, per-workflow ceiling of $1.00, and per-user/day budget in tenant config (Architecture §12.6).

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-002 | Watchlist Scan target ≤ 3 min, hard limit 8 min | Workflow-level `timeout_seconds=480` enforced in workflow YAML; Historical Context Agent is conditional (high-anomaly only) to save time; `asyncio.gather` used for parallel Historical Context calls per company; Celery task timeout set to 540 s (buffer) |
| REQ-N-004 | Per-scan cost ≤ $1.00 | Per-workflow `cost_ceiling_usd: 1.00` in workflow YAML; per-agent ceilings sum to ≤ $1.00; budget tracking in `WorkflowState.cost_usd`; cost-exceeded condition routes to HIL with "budget exceeded" reason |

## Component Design

### New Components

```
src/ai/workflows/watchlist_scan/
  __init__.py
  graph.py              — LangGraph StateGraph definition: nodes, edges, conditional branches
  nodes.py              — DeterministicNode implementations (fetch_watchlist, fetch_today_events,
                          recompute_scores, evaluate_quality, format_email, dispatch,
                          hil_enqueue, block_and_notify)
  state.py              — WatchlistScanState (extends WorkflowState with scan-specific fields)
  router.py             — Confidence routing logic: route_after_quality() pure function
  cost_guard.py         — Per-workflow cost accumulator checked before each AgentNode

src/config/celery_app.py          — modified: add watchlist_scan beat schedule entry at 17:30
src/ai/workflows/watchlist_scan/watchlist_scan.yaml
                                  — workflow YAML: cost_ceiling_usd: 1.00, timeout_seconds: 480,
                                    hil_deadline: "17:45", dispatch_target: "18:00"
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Add `watchlist-scan` beat entry: `crontab(hour=17, minute=30)` dispatching `run_watchlist_scan_for_all_users` | Cron trigger at 17:30 per AC-001 |
| `src/ai/workflows/__init__.py` | Register `watchlist_scan` graph with workflow router | Workflow discovery |
| `src/ai/tasks.py` | Add `run_watchlist_scan_for_all_users` Celery task and per-user `run_watchlist_scan` subtask | Task dispatch layer |

### Interfaces and Contracts

```python
# state.py
class WatchlistScanState(WorkflowState):
    watchlist_companies: list[UUID] = []
    portfolio_companies: list[UUID] = []
    scoped_company_ids: list[UUID] = []   # union of watchlist + portfolio
    today_events: list[GeoEvent] = []
    relevant_events: list[RelevantEvent] = []
    score_changes: list[ScoreChange] = []
    anomalies: list[Anomaly] = []
    high_anomaly_company_ids: list[UUID] = []
    analogies: dict[UUID, list[Analogy]] = {}
    recommendations: list[Recommendation] = []
    report: Report | None = None
    confidence_scores: dict[str, float] = {}
    overall_confidence: float = 0.0
    requires_hil: bool = False
    hil_reason: str | None = None
    cost_usd: float = 0.0
    workflow_type: WorkflowType = WorkflowType.WATCHLIST_SCAN

# router.py
def route_after_quality(state: WatchlistScanState) -> Literal["dispatch", "hil_enqueue", "block_and_notify"]:
    """Pure routing function. D9 thresholds: ≥0.70 auto, 0.40–0.69 HIL, <0.40 block."""
    ...

# graph.py — graph construction signature
def build_watchlist_scan_graph(registry: AgentRegistry, tool_library: ToolLibrary) -> CompiledStateGraph:
    """Builds and compiles the Watchlist Scan LangGraph StateGraph."""
    ...

# cost_guard.py
class WorkflowCostGuard:
    def __init__(self, ceiling_usd: float) -> None: ...
    def check_and_accumulate(self, state: WatchlistScanState, agent_cost: float) -> None:
        """Raises WorkflowBudgetExceededError if ceiling is breached."""
        ...
```

## Implementation Tasks

### TASK-001: Cron trigger and Celery task dispatch · S/no-TDD · src/config/celery_app.py, src/ai/tasks.py

Add a Celery beat schedule entry that fires `run_watchlist_scan_for_all_users` at 17:30 daily. The task queries all users with active watchlist subscriptions (non-empty `watchlist` rows) and fans out one `run_watchlist_scan` subtask per user. Each subtask receives `user_id` and `tenant_id`. The subtask sets Celery `time_limit=540` (9-minute hard ceiling including startup overhead). Use `apply_async` with `countdown=0` so fan-out is immediate.

```python
# celery_app.py beat_schedule addition
"watchlist-scan-daily": {
    "task": "src.ai.tasks.run_watchlist_scan_for_all_users",
    "schedule": crontab(hour=17, minute=30),
},
```

**AC covered**: AC-001 (cron fires at 17:30)

---

### TASK-002: WatchlistScanState Pydantic model · S/no-TDD · src/ai/workflows/watchlist_scan/state.py

Define `WatchlistScanState` extending `WorkflowState`. Fields: `watchlist_companies`, `portfolio_companies`, `scoped_company_ids`, `today_events`, `relevant_events`, `score_changes`, `anomalies`, `high_anomaly_company_ids`, `analogies`, `recommendations`, `report`, `confidence_scores`, `overall_confidence`, `requires_hil`, `hil_reason`. Set `workflow_type = WorkflowType.WATCHLIST_SCAN`. All collections default to empty; all optionals default to `None` or `0.0`. Pydantic v2 `model_config = ConfigDict(frozen=False)`.

**AC covered**: enables AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-003: DeterministicNodes — fetch_watchlist and fetch_today_events · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement two deterministic fetch nodes:

`fetch_watchlist(state)`: calls `tool_library.get_watchlist(user_id, tenant_id)` and `tool_library.get_portfolio_state(user_id, tenant_id)`. Populates `state.watchlist_companies`, `state.portfolio_companies`, and `state.scoped_company_ids` (union, deduplicated). Returns updated state.

`fetch_today_events(state)`: calls `tool_library.query_recent_events(since=today_start, until=now)`. Stores result in `state.today_events`. No filtering at this stage — relevance scoping happens in the Relevance Analyst AgentNode.

Both nodes follow the `(state: WatchlistScanState) -> WatchlistScanState` signature contract.

**Tests to write first (TDD)**:
- `test_fetch_watchlist_populates_scoped_company_ids` — given mock tool returns watchlist + portfolio items, assert deduplication and union are correct.
- `test_fetch_watchlist_empty_watchlist` — given user has no watchlist entries, assert `scoped_company_ids` equals portfolio-only companies; no error raised.
- `test_fetch_today_events_stores_all_events` — given mock tool returns N events, assert `state.today_events` has length N.
- `test_fetch_today_events_tool_error_propagates` — given tool raises `InsufficientData`, assert node re-raises with context.

**AC covered**: AC-002 (watchlist/portfolio scope established at fetch stage)

---

### TASK-004: DeterministicNode — recompute_scores · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `recompute_scores(state)`: iterates over companies in `state.scoped_company_ids` that appear in `state.relevant_events`, calls `tool_library.get_company_score_history(company_id)` for each, computes delta vs. prior snapshot, populates `state.score_changes`. Uses `asyncio.gather` for concurrent tool calls when more than one company is affected. Bounded to `state.scoped_company_ids` only — never scores unscoped companies (enforces AC-002). Empty `relevant_events` returns state unchanged.

**Tests to write first (TDD)**:
- `test_recompute_scores_only_scoped_companies` — given relevant_events touch companies both inside and outside `scoped_company_ids`, assert only scoped company scores are computed.
- `test_recompute_scores_empty_relevant_events` — assert `state.score_changes` remains empty and no tool calls are made.
- `test_recompute_scores_concurrent_execution` — given 5 scoped companies, assert `asyncio.gather` is used (mock to verify concurrent calls).
- `test_recompute_scores_populates_score_changes` — assert `ScoreChange` objects include company_id, prior_score, new_score, delta.

**AC covered**: AC-002 (only scoped companies re-scored)

---

### TASK-005: AgentNode — Relevance Analyst integration · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement the `relevance_analyst_node(state)` wrapper. Resolves the `relevance_analyst` agent via `AgentRegistry`, invokes it with `state.today_events` and `state.scoped_company_ids` as context, and writes the output to `state.relevant_events`. Updates `state.cost_usd` and `state.confidence_scores["relevance_analyst"]`. Calls `WorkflowCostGuard.check_and_accumulate` before returning. If the agent returns an empty `relevant_events` list (no relevant events today), the node writes a zero-confidence sentinel that will ultimately route to "block" at the quality gate.

**Tests to write first (TDD)**:
- `test_relevance_analyst_node_filters_to_scoped_companies` — mock agent returns events including out-of-scope company; assert out-of-scope event is excluded from `state.relevant_events`.
- `test_relevance_analyst_node_updates_cost` — mock agent reports cost 0.10; assert `state.cost_usd` incremented correctly.
- `test_relevance_analyst_node_empty_result_sets_sentinel` — mock agent returns empty list; assert confidence sentinel triggers downstream block.
- `test_relevance_analyst_node_cost_ceiling_exceeded` — mock cumulative cost reaches $1.00; assert `WorkflowBudgetExceededError` raised.

**AC covered**: AC-002 (relevance filtering is the gating step for scoped events)

---

### TASK-006: AgentNode — Anomaly Detector integration · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `anomaly_detector_node(state)` wrapper. Resolves `anomaly_detector` agent, invokes with `state.score_changes` and `state.relevant_events`. Writes detected anomalies to `state.anomalies`. Populates `state.high_anomaly_company_ids` as the subset of `state.scoped_company_ids` where anomaly magnitude exceeds a configurable threshold (default: `anomaly.magnitude >= 0.6`). Updates `state.cost_usd` and `state.confidence_scores["anomaly_detector"]`. Calls `WorkflowCostGuard.check_and_accumulate`.

`high_anomaly_company_ids` is the gate for the conditional Historical Context Agent invocation in TASK-007.

**Tests to write first (TDD)**:
- `test_anomaly_detector_populates_high_anomaly_ids` — given anomalies with mixed magnitudes, assert only IDs with magnitude ≥ 0.6 are in `high_anomaly_company_ids`.
- `test_anomaly_detector_no_anomalies_empty_high_anomaly_list` — given no anomalies detected, assert `high_anomaly_company_ids` is empty.
- `test_anomaly_detector_updates_cost_and_confidence` — assert cost accumulation and confidence key written.

**AC covered**: AC-001 (anomaly detection is on the critical path for latency budget), enables conditional HC Agent routing

---

### TASK-007: AgentNode — Historical Context Agent (conditional, high-anomaly only) · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `historical_context_node(state)`. Guard: if `state.high_anomaly_company_ids` is empty, immediately return state unchanged (no-op, zero cost). Otherwise, resolve `historical_context_agent` from `AgentRegistry` and invoke once per high-anomaly company using `asyncio.gather`. Write merged results to `state.analogies` keyed by `company_id`. Update `state.cost_usd` and `state.confidence_scores["historical_context_agent"]`. Calls `WorkflowCostGuard.check_and_accumulate` per invocation.

The conditional invocation is the primary latency-saving mechanism for the 3-minute budget (Architecture §7.5 Workflow 3 note: "high-anomaly names only").

**Tests to write first (TDD)**:
- `test_hca_node_skipped_when_no_high_anomaly_companies` — given `high_anomaly_company_ids=[]`, assert agent is never called and state unchanged.
- `test_hca_node_invokes_once_per_high_anomaly_company` — given 3 high-anomaly companies, assert agent invoked 3 times (verify via mock call count).
- `test_hca_node_uses_asyncio_gather` — assert concurrent execution path is taken for multiple companies.
- `test_hca_node_writes_analogies_keyed_by_company_id` — assert `state.analogies` dict has entry for each high-anomaly company.

**AC covered**: AC-001 (conditional invocation keeps workflow within latency budget)

---

### TASK-008: AgentNode — Recommendation Synthesizer integration · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `recommendation_synthesizer_node(state)`. Resolves `recommendation_synthesizer` agent, invokes with `state.relevant_events`, `state.anomalies`, and `state.analogies`. Writes `state.recommendations` (list of `Recommendation` objects with `action_signal`, `company_id`, `confidence`, `rationale`). Updates `state.cost_usd` and `state.confidence_scores["recommendation_synthesizer"]`. Calls `WorkflowCostGuard.check_and_accumulate`.

**Tests to write first (TDD)**:
- `test_synthesizer_produces_recommendations_for_relevant_events` — given 3 relevant events, assert at least one `Recommendation` is produced.
- `test_synthesizer_recommendation_action_signals_are_valid` — assert all `action_signal` values are in `{HOLD, WATCH, BUY_OPP, REDUCE_RISK, HEDGE, CONTRARIAN}`.
- `test_synthesizer_updates_cost_and_confidence` — assert accumulation correct.

**AC covered**: AC-003 (recommendations are an input to the final report dispatched at confidence ≥ 0.70)

---

### TASK-009: AgentNode — Narrative Writer (last AgentNode) · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `narrative_writer_node(state)`. Resolves `narrative_writer` agent. This node runs last among AgentNodes — it converts `state.recommendations` and `state.analogies` into a human-readable HTML report in FT-columnist voice. Writes to `state.report`. Updates `state.cost_usd` and `state.confidence_scores["narrative_writer"]`. Calls `WorkflowCostGuard.check_and_accumulate`. Must be positioned immediately before `evaluate_quality` in the graph (enforces AC-005).

**Tests to write first (TDD)**:
- `test_narrative_writer_produces_html_report` — given populated recommendations, assert `state.report.content` is non-empty HTML string.
- `test_narrative_writer_is_last_agent_node` — graph structure test: assert no AgentNode follows `narrative_writer` before `evaluate_quality` (introspect graph topology).
- `test_narrative_writer_updates_cost` — assert cost and confidence updated.

**AC covered**: AC-005 (Narrative Writer is enforced as last AgentNode), AC-003 (report content dispatched on auto-send path)

---

### TASK-010: DeterministicNode — evaluate_quality (second-to-last node) · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `evaluate_quality_node(state)`. Computes `state.overall_confidence` as the minimum of all values in `state.confidence_scores` (per Architecture §7.2 workflow-level confidence rule). Sets `state.requires_hil = True` and `state.hil_reason` when `0.40 ≤ overall_confidence < 0.70`. Sets `requires_hil = False` when `overall_confidence ≥ 0.70`. Does not set `requires_hil` when `overall_confidence < 0.40` — the router handles the "block" branch. Must be positioned second-to-last in the graph (enforces AC-005). Writes `workflow_run` episodic memory entry with final confidence and cost.

**Tests to write first (TDD)**:
- `test_evaluate_quality_confidence_is_minimum_across_agents` — given confidence_scores with values [0.9, 0.5, 0.8], assert `overall_confidence = 0.5`.
- `test_evaluate_quality_sets_requires_hil_in_mid_range` — given `overall_confidence = 0.55`, assert `requires_hil = True`.
- `test_evaluate_quality_clears_requires_hil_above_threshold` — given `overall_confidence = 0.75`, assert `requires_hil = False`.
- `test_evaluate_quality_is_second_to_last_node` — graph structure test: assert only the confidence routing branch node follows `evaluate_quality`.

**AC covered**: AC-003 (auto-send path established), AC-004 (HIL path established), AC-005 (evaluate_quality enforced as second-to-last)

---

### TASK-011: WorkflowCostGuard · M/TDD · src/ai/workflows/watchlist_scan/cost_guard.py

Implement `WorkflowCostGuard` class. Constructor accepts `ceiling_usd: float`. Method `check_and_accumulate(state, agent_cost)` adds `agent_cost` to `state.cost_usd` atomically and raises `WorkflowBudgetExceededError` if `state.cost_usd > self.ceiling_usd`. `WorkflowBudgetExceededError` carries `current_cost_usd`, `ceiling_usd`, and `workflow_id` — these are forwarded as `hil_reason` when the workflow routes to HIL. The guard is instantiated once per workflow run and shared across all node invocations.

**Tests to write first (TDD)**:
- `test_cost_guard_accumulates_cost_on_state` — assert `state.cost_usd` incremented after each call.
- `test_cost_guard_raises_when_ceiling_exceeded` — given cumulative cost exceeds ceiling, assert `WorkflowBudgetExceededError` raised with correct fields.
- `test_cost_guard_does_not_raise_at_exactly_ceiling` — assert no exception when `cost_usd == ceiling_usd` (ceiling is inclusive).
- `test_cost_guard_error_carries_workflow_id` — assert exception `workflow_id` matches `state.workflow_id`.

**AC covered**: AC-001 (cost ceiling enforces budget, protecting the $1.00 constraint)

---

### TASK-012: Confidence router and LangGraph graph assembly · L/TDD · src/ai/workflows/watchlist_scan/router.py, src/ai/workflows/watchlist_scan/graph.py

Implement `route_after_quality(state: WatchlistScanState) -> Literal["dispatch", "hil_enqueue", "block_and_notify"]` as a pure function applying D9 thresholds. Then assemble the full LangGraph `StateGraph` in `build_watchlist_scan_graph()`:

Graph node order (mandatory):
1. `fetch_watchlist` (DeterministicNode)
2. `fetch_today_events` (DeterministicNode)
3. `relevance_analyst` (AgentNode)
4. `recompute_scores` (DeterministicNode)
5. `anomaly_detector` (AgentNode)
6. `historical_context_agent` (AgentNode — conditional no-op if no high-anomaly companies)
7. `recommendation_synthesizer` (AgentNode)
8. `narrative_writer` (AgentNode — last AgentNode)
9. `evaluate_quality` (DeterministicNode — second-to-last node)
10. `conditional_branch` → `dispatch` | `hil_enqueue` | `block_and_notify`

Wire PostgreSQL checkpointer via `SqliteSaver` (dev) / `PostgresSaver` (prod) from `langgraph.checkpoint.postgres`. Use `add_conditional_edges` from `evaluate_quality` with `route_after_quality` as the routing function. Configure `StateGraph(WatchlistScanState)`.

**Tests to write first (TDD)**:
- `test_router_returns_dispatch_above_threshold` — `overall_confidence = 0.80` → `"dispatch"`.
- `test_router_returns_hil_in_mid_range` — `overall_confidence = 0.55` → `"hil_enqueue"`.
- `test_router_returns_block_below_threshold` — `overall_confidence = 0.30` → `"block_and_notify"`.
- `test_router_boundary_at_0_70_is_dispatch` — `overall_confidence = 0.70` → `"dispatch"`.
- `test_router_boundary_at_0_40_is_hil` — `overall_confidence = 0.40` → `"hil_enqueue"`.
- `test_graph_node_order_enforces_narrative_writer_before_evaluate_quality` — introspect compiled graph edges; assert `narrative_writer` → `evaluate_quality` edge exists.
- `test_graph_has_postgresql_checkpointer_in_prod_config` — assert graph built with `PostgresSaver` when `ENVIRONMENT=production`.
- `test_graph_conditional_branch_wires_all_three_outcomes` — assert `dispatch`, `hil_enqueue`, and `block_and_notify` are all reachable from `evaluate_quality`.

**AC covered**: AC-003 (dispatch path), AC-004 (hil_enqueue path), AC-005 (structural order enforced in graph)

---

### TASK-013: HIL enqueue node and delivery-deadline enforcement · M/TDD · src/ai/workflows/watchlist_scan/nodes.py

Implement `hil_enqueue_node(state)`. Persists the report to the `brief` table with `hil_status = "pending"`. Enqueues a HIL review item via `hil_service.enqueue(report_id, deadline=today_at(17, 45), workflow_type="watchlist_scan")`. Schedules a deadline-check Celery task (`check_hil_deadline`) for 17:45 that withholds the report and notifies the user if unreviewed. The deadline check must be idempotent (safe to run multiple times).

`block_and_notify_node(state)`: writes an episodic log entry with `status="blocked"` and `confidence=state.overall_confidence`. Sends a system notification to the user that no report will be delivered today (low-confidence block). Does not send the report content.

**Tests to write first (TDD)**:
- `test_hil_enqueue_node_sets_hil_status_pending` — mock DB; assert `brief.hil_status = "pending"` after node executes.
- `test_hil_enqueue_node_schedules_deadline_task_at_1745` — mock Celery; assert `check_hil_deadline` scheduled with ETA = today 17:45.
- `test_hil_enqueue_node_is_idempotent` — calling twice with same `report_id` does not duplicate queue entry.
- `test_block_and_notify_does_not_send_report_content` — mock email dispatcher; assert no email with report content sent.
- `test_block_and_notify_writes_episodic_log_with_blocked_status` — assert `workflow_run.status = "blocked"` and confidence recorded.

**AC covered**: AC-004 (HIL queue with 17:45 deadline; withheld and notified if unreviewed)

---

### TASK-014: Email dispatch node and report persistence · M/TDD · src/ai/workflows/watchlist_scan/nodes.py, src/ai/workflows/watchlist_scan/email_template.html

Implement `dispatch_node(state)`. Persists the report to the `brief` table with `type="watchlist_scan"`, `user_id`, `confidence`, `cost_usd`, `hil_status="approved"` (auto-approved), `sent_at=None` initially. Renders the HTML report using the watchlist scan email template. Calls `alert_service.send_email(user_id, subject, html_body)` targeting 18:00 delivery. Sets `sent_at` on success. Writes an episodic `workflow_run` row with `status="completed"`. The dispatch node is reached only on the auto-send branch (confidence ≥ 0.70); HIL-approved dispatches use the same node, invoked by the HIL queue approval handler in PLAN-F-013.

**Tests to write first (TDD)**:
- `test_dispatch_node_persists_brief_with_correct_type` — mock repo; assert `brief.type = "watchlist_scan"` and `brief.hil_status = "approved"`.
- `test_dispatch_node_sends_email_with_html_content` — mock email service; assert called once with HTML body.
- `test_dispatch_node_sets_sent_at_on_success` — assert `brief.sent_at` is set after successful send.
- `test_dispatch_node_writes_workflow_run_completed` — assert episodic memory row `status="completed"`.
- `test_dispatch_node_does_not_send_on_email_service_failure` — mock email raises; assert `sent_at` not set and error propagates for retry.

**AC covered**: AC-003 (auto-deliver by 18:00 on confidence ≥ 0.70)

---

### TASK-015: Watchlist scan workflow YAML and workflow registration · S/no-TDD · src/ai/workflows/watchlist_scan/watchlist_scan.yaml, src/ai/workflows/__init__.py

Create `watchlist_scan.yaml` declaring: `workflow_id: watchlist_scan`, `cost_ceiling_usd: 1.00`, `timeout_seconds: 480`, `hil_deadline: "17:45"`, `dispatch_target: "18:00"`, `pg_checkpoint: true`. Register `watchlist_scan` in the workflow registry so `build_watchlist_scan_graph` is discovered at startup. Wire `WorkflowStructureValidator` (from PLAN-F-011) to validate the compiled graph's `evaluate_quality → narrative_writer` tail invariant at startup. Log validation result at `INFO` level.

**AC covered**: AC-001 (budget configuration), AC-005 (structure validation at startup)

---

### TASK-016: End-to-end integration test · L/TDD · tests/integration/workflows/test_watchlist_scan_e2e.py

Write an integration test that runs the full compiled graph against a test PostgreSQL database with seeded `watchlist`, `portfolio`, and `geo_event` rows. Mock all LLM agent invocations (use `unittest.mock.AsyncMock`) but run all DeterministicNodes against real DB. Assert: (1) graph completes without exception; (2) `brief` row created with correct `type="watchlist_scan"`; (3) routing correct per mocked confidence value; (4) `cost_usd` is tracked across the full run; (5) PostgreSQL checkpoint row created for the run.

**Tests to write first (TDD)**:
- `test_e2e_auto_dispatch_path` — mock all agents return confidence 0.85; assert `brief.sent_at` is set and `hil_status="approved"`.
- `test_e2e_hil_path` — mock agents return confidence 0.55; assert `brief.hil_status="pending"` and deadline task scheduled.
- `test_e2e_block_path` — mock agents return confidence 0.25; assert no brief row with content and episodic log has `status="blocked"`.
- `test_e2e_budget_exceeded_routes_to_hil` — mock cost accumulation exceeds $1.00 mid-graph; assert `hil_reason` contains "budget exceeded".
- `test_e2e_empty_watchlist_completes_gracefully` — given user has no watchlist entries, assert workflow completes (no-op report) without exception.
- `test_e2e_postgresql_checkpoint_created` — assert LangGraph checkpoint table contains entry for the run's `workflow_id`.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005 (full coverage under realistic conditions)

---

## Acceptance Criteria Coverage

- AC-001: cron fires at 17:30; completes within 3 min target / 8 min hard limit; ≤ $1.00 cost → TASK-001, TASK-006, TASK-007, TASK-011, TASK-015, TASK-016
- AC-002: report covers only events relevant to user's portfolio and watchlist companies → TASK-003, TASK-004, TASK-005, TASK-016
- AC-003: confidence ≥ 0.70 → auto-deliver by 18:00 → TASK-008, TASK-009, TASK-012, TASK-014, TASK-016
- AC-004: confidence 0.40–0.69 → HIL queue; withheld and user notified if unreviewed at 17:45 → TASK-010, TASK-012, TASK-013, TASK-016
- AC-005: evaluate_quality is second-to-last node; Narrative Writer is last AgentNode; structural pattern enforced in LangGraph definition → TASK-009, TASK-010, TASK-012, TASK-015, TASK-016

## Risks and Notes

- The requirement's §Process Sequence lists "Exposure Analyst" as the second agent, but Architecture §7.5 Workflow 3 (authoritative per D10) specifies "Relevance Analyst → recompute_scores → Anomaly Detector → Historical Context Agent → Recommendation Synthesizer → Narrative Writer → evaluate_quality". This plan follows the architecture. Exposure Analyst is not part of Workflow 3; it belongs to Workflows 2 and 5.
- Historical Context Agent is conditioned on `high_anomaly_company_ids` being non-empty. This is the primary latency-saving measure. If many companies are high-anomaly, the `asyncio.gather` call may still push near the 3-minute target. Each Historical Context Agent call has its own 60-second per-agent timeout; if the gather exceeds this, route to HIL with "latency budget" reason.
- PostgreSQL LangGraph checkpointing requires the `langgraph-checkpoint-postgres` package and a dedicated connection pool. Do not reuse the main SQLAlchemy pool — use a separate `asyncpg` connection for the checkpointer to avoid pool exhaustion during long workflows.
- The `check_hil_deadline` Celery task must be idempotent. The HIL approval handler in PLAN-F-013 calls `dispatch_node` directly; if both race at 17:45, only one dispatch must occur. Use a DB-level unique constraint on `(report_id, sent_at IS NOT NULL)` or a Redis lock keyed by `report_id`.
- Cost tracking (`state.cost_usd`) accumulates only LLM inference cost. Tool call latency is not a cost input. Ensure every AgentNode wrapper reads actual token costs from the Anthropic response and does not estimate.
- The `block_and_notify` branch must never send report content — only a system notification that no report is available. This prevents leaking low-confidence analysis to users.
