---
plan_id: PLAN-F-006
slug: morning-brief-workflow
title: Morning Brief Workflow (Mode B — Workflow 1)
linked_requirement: REQ-F-006
type: functional
status: done
blocked_reason:
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-002, reason: "Workflow must complete within 5 minutes (10-minute hard cap) from cron trigger to delivery or HIL routing" }
  - { id: REQ-N-004, reason: "Per-report LLM cost ceiling of $2.00 enforced at workflow and per-agent YAML levels" }
  - { id: REQ-N-008, reason: "One Langfuse trace per workflow run; every agent invocation is a child span with prompt_version, model, tokens, cost, latency" }
dependencies:
  - { id: PLAN-F-011, reason: "Named-role agents (relevance_analyst, anomaly_detector, historical_context_agent, recommendation_synthesizer, narrative_writer, evaluate_quality) must be defined in AgentRegistry before this workflow can load and invoke them" }
  - { id: PLAN-F-015, reason: "Memory layers required: Layer 1 episodic record for every workflow run; Layer 4 user_feedback written on every HIL action" }
  - { id: PLAN-F-013, reason: "HIL review path required for confidence 0.4–0.69 outputs; workflow pauses on LangGraph checkpoint and resumes only on HIL approval; timeout handler reads HIL status at 05:45" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-006 — Morning Brief Workflow (Mode B — Workflow 1)

## Linked Requirement
**REQ-F-006** — Morning Brief Workflow (Mode B)
Status: approved | Jira:

## Objective

Implement the daily LangGraph StateGraph workflow (Workflow 1 — Morning Brief) that is triggered by a Celery beat cron at ~05:30 per subscribed user and delivers a personalized HTML email by 06:00 local time (configurable per user, per D7). The workflow executes seven ordered nodes — four DeterministicNodes (`fetch_portfolio`, `fetch_overnight_events`, `recompute_scores`, `format_email_and_dispatch`) and five AgentNodes (`relevance_analyst`, `anomaly_detector`, `historical_context_agent` in parallel per event, `recommendation_synthesizer`, `evaluate_quality`, `narrative_writer`) — all sharing a Pydantic `WorkflowState` object that is checkpointed to PostgreSQL after every node. The `evaluate_quality` node (Opus 4.7 LLM-as-judge) runs second-to-last and produces the determinative confidence score that routes the workflow to auto-send (≥ 0.7), HIL queue (0.4–0.69, with 05:45 timeout and hold-and-notify fallback), or block-and-log (< 0.4). Email dispatch uses SendGrid with a responsive HTML template. The entire run budget is ≤ 5 minutes and ≤ $2.00 (REQ-N-002, REQ-N-004). Every run emits exactly one Langfuse trace (REQ-N-008).

## Architecture Context

This plan lives entirely within the `ai` module (`src/ai/`), with narrow reach into `alerts` (SendGrid dispatch) and `storage` (repositories for `workflow_run`, `brief`, `user` settings).

Relevant ARCHITECTURE.md sections:
- **§7.1 LangGraph Runtime** — two-node-type model, PostgreSQL checkpointing, `asyncio.gather` for parallelism, bounded execution per agent YAML.
- **§7.2 Agent Registry** — `relevance_analyst` (Sonnet 4.6), `anomaly_detector` (Sonnet 4.6), `historical_context_agent` (Opus 4.7), `recommendation_synthesizer` (Opus 4.7), `narrative_writer` (Opus 4.7).
- **§7.3 Tool Library** — agents call typed tools only; no direct DB/API access.
- **§7.4 Memory Subsystem** — Layer 1 episodic entry written at workflow end; Layer 4 feedback written on every HIL action (owned by PLAN-F-015 and PLAN-F-013).
- **§7.5 Workflow 1** — canonical node sequence and budget.
- **§7.6 HIL Review Queue** — timing window 22:00 prev–05:45; unreviewed → hold and notify.
- **§7.7 Confidence Model** — D9 thresholds: ≥ 0.7 auto-send, 0.4–0.69 HIL, < 0.4 block.
- **§12.4 Observability** — one Langfuse trace per run, standard span metadata.
- **§12.6 Cost Governance** — per-agent `cost_ceiling_usd` enforced in agent YAML; per-workflow ceiling $2.00.
- **§13 Technology** — LangGraph (Python), Celery beat, Celery workers, SendGrid, PostgreSQL 16.

**New source files** all live under `src/ai/workflows/morning_brief/`. The Celery task lives in `src/ai/tasks/morning_brief_task.py`. DB migrations live in `src/db/migrations/`. Frontend changes are scoped to an informational notification component only (not a UI workflow plan).

**Layering rule respected:** Workflow nodes call the Tool Library (PLAN-F-012). Tool Library calls Repositories (storage module). No node writes SQL directly.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-002 | Morning Brief end-to-end ≤ 5 min (10-min hard cap) | Per-agent `timeout_seconds` set in YAML; `asyncio.gather` for parallel Historical Context invocations; workflow-level deadline guard cancels run and logs timeout at T+10 min |
| REQ-N-004 | Per-report AI cost ≤ $2.00 | `cost_ceiling_usd: 2.00` on the workflow YAML; each agent YAML carries individual ceiling; running cost tracked in `WorkflowState.cost_usd`; approach-ceiling triggers reduced token budgets for remaining agents |
| REQ-N-008 | One Langfuse trace per workflow run | `MorningBriefWorkflow` opens a trace at start; every AgentNode is a child span; `langfuse_trace_id` written to `workflow_run` row on completion |

## Component Design

### New Components

```
src/ai/workflows/morning_brief/
  __init__.py
  graph.py                   — LangGraph StateGraph definition (node wiring, edges, conditional branches)
  state.py                   — MorningBriefState (extends WorkflowState with brief-specific fields)
  nodes/
    __init__.py
    fetch_portfolio.py        — DeterministicNode: load portfolio snapshot via Tool Library
    fetch_overnight_events.py — DeterministicNode: query geo_events since prior close via Tool Library
    recompute_scores.py       — DeterministicNode: invoke scoring service for portfolio companies
    relevance_analyst_node.py — AgentNode wrapper: invokes relevance_analyst agent
    anomaly_detector_node.py  — AgentNode wrapper: invokes anomaly_detector agent
    historical_context_node.py— AgentNode wrapper: asyncio.gather over relevant events (parallel)
    recommendation_node.py    — AgentNode wrapper: invokes recommendation_synthesizer agent
    evaluate_quality_node.py  — AgentNode wrapper: invokes evaluate_quality LLM-as-judge (Opus 4.7)
    narrative_writer_node.py  — AgentNode wrapper: invokes narrative_writer agent (always last AgentNode)
    format_and_dispatch.py    — DeterministicNode: renders HTML email, calls SendGrid
  routing.py                 — confidence_router(): conditional edge function (auto-send/HIL/block)
  hil_timeout_handler.py     — checks HIL status at 05:45; triggers hold-and-notify if unreviewed
  cost_guard.py              — accumulates WorkflowState.cost_usd; reduces tokens if ceiling approached

src/ai/tasks/
  morning_brief_task.py      — Celery task: entry point per user; instantiates and runs the graph

src/ai/schemas/
  morning_brief_state.py     — Pydantic models: MorningBriefState, BriefRow, ConfidenceRoute enum

src/db/migrations/
  XXXX_add_brief_table.py    — Alembic migration: `brief` table (brief_id, type, user_id, content,
                               confidence, hil_status, sent_at, cost_usd, workflow_id FK)

agents/
  morning_brief_workflow.yaml — Workflow-level config: cost_ceiling_usd, timeout_seconds, cron_schedule

prompts/evaluators/
  quality_judge.md           — Prompt for the evaluate_quality LLM-as-judge (Opus 4.7)

src/alerts/
  email_templates/
    morning_brief.html        — Responsive SendGrid HTML template (Jinja2)
  sendgrid_dispatcher.py     — Extended with send_morning_brief() method (adds brief_id header)

tests/ai/workflows/morning_brief/
  test_graph.py              — Unit + integration tests for the full graph
  test_nodes.py              — Unit tests per node (mocked Tool Library)
  test_routing.py            — Unit tests for confidence_router()
  test_hil_timeout.py        — Unit tests for hil_timeout_handler
  test_cost_guard.py         — Unit tests for cost_guard
  test_morning_brief_task.py — Celery task integration tests

tests/integration/
  test_morning_brief_e2e.py  — Full workflow integration test (real DB, mocked LLM + SendGrid)
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Add `morning_brief` beat schedule entry (cron `30 5 * * *`) | Trigger workflow daily at 05:30 |
| `src/config/settings.py` | Add `SENDGRID_MORNING_BRIEF_TEMPLATE_ID`, `MORNING_BRIEF_DEFAULT_SEND_TIME` env vars | Email template and configurable dispatch time |
| `src/db/migrations/` | New Alembic migration for `brief` table | Persist brief rows with HIL status |
| `src/ai/workflows/__init__.py` | Register `MorningBriefWorkflow` in workflow registry | Discoverable by dev-executor and admin panel |

### Interfaces and Contracts

```python
# src/ai/schemas/morning_brief_state.py

from enum import Enum
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from typing import Any

class ConfidenceRoute(str, Enum):
    AUTO_SEND = "auto_send"       # confidence >= 0.7
    HIL = "hil"                   # confidence 0.4-0.69
    BLOCK = "block"               # confidence < 0.4

class HilStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"

class BriefRow(BaseModel):
    brief_id: UUID
    type: str = "morning_brief"
    user_id: UUID
    workflow_id: UUID
    content: str          # HTML
    confidence: float
    hil_status: HilStatus
    sent_at: datetime | None = None
    cost_usd: float

class MorningBriefState(BaseModel):
    # Inherited from WorkflowState (§7.1)
    workflow_id: UUID
    workflow_type: str = "morning_brief"
    tenant_id: UUID
    user_id: UUID
    started_at: datetime
    inputs: dict[str, Any]
    portfolio_state: dict[str, Any] | None = None
    events: list[dict] = []
    relevant_events: list[dict] = []
    score_changes: list[dict] = []
    anomalies: list[dict] = []
    analogies: dict[str, list[dict]] = {}
    recommendations: list[dict] = []
    report: str | None = None           # HTML produced by narrative_writer
    confidence_scores: dict[str, float] = {}
    requires_hil: bool = False
    hil_reason: str | None = None
    cost_usd: float = 0.0
    tokens_consumed: dict[str, int] = {}
    # Brief-specific
    langfuse_trace_id: str | None = None
    confidence_route: ConfidenceRoute | None = None
    brief_id: UUID | None = None        # set after BriefRow is persisted
    dispatch_time: str = "06:00"        # from user.dispatch_time (D7)

# src/ai/workflows/morning_brief/routing.py

def confidence_router(state: MorningBriefState) -> str:
    """
    Conditional edge function for LangGraph.
    Returns node name to route to after evaluate_quality.
    """
    overall = min(state.confidence_scores.values()) if state.confidence_scores else 0.0
    if overall >= 0.70:
        return "narrative_writer"       # then format_and_dispatch
    elif overall >= 0.40:
        return "hil_queue"              # pause graph; HIL review
    else:
        return "block_and_log"          # terminal node; no email
```

## Implementation Tasks

### TASK-001: MorningBriefState Pydantic model and `brief` DB table migration · M/TDD · src/ai/schemas/morning_brief_state.py, src/db/migrations/XXXX_add_brief_table.py, tests/ai/workflows/morning_brief/test_nodes.py

Define the `MorningBriefState` Pydantic model extending `WorkflowState` (§7.1) with brief-specific fields: `langfuse_trace_id`, `confidence_route`, `brief_id`, `dispatch_time`. Define `BriefRow`, `ConfidenceRoute`, and `HilStatus` enums. Write the Alembic migration creating the `brief` table with columns: `brief_id UUID PK`, `type VARCHAR`, `user_id UUID FK→user`, `workflow_id UUID FK→workflow_run`, `content TEXT`, `confidence FLOAT`, `hil_status VARCHAR`, `sent_at TIMESTAMPTZ NULL`, `cost_usd FLOAT`. Apply multi-tenancy: add `tenant_id UUID NOT NULL` column and index.

**Tests to write first (TDD):**
- `test_morning_brief_state_defaults()` — verify default field values and Pydantic validation constraints
- `test_confidence_route_enum_values()` — verify enum strings match routing logic expectations
- `test_brief_row_serialization()` — round-trip JSON serialization of `BriefRow`
- `test_brief_table_migration_applies_cleanly()` — Alembic upgrade/downgrade against test DB

**AC covered:** AC-005 (checkpointing state schema required), AC-006 (confidence_route field drives routing)

---

### TASK-002: Workflow-level YAML config and `morning_brief_workflow.yaml` · S/no-TDD · agents/morning_brief_workflow.yaml, src/config/settings.py

Create `agents/morning_brief_workflow.yaml` with the workflow-level configuration block:

```yaml
workflow_id: morning_brief
display_name: "Morning Brief"
cost_ceiling_usd: 2.00
timeout_seconds: 600       # 10-minute hard cap (REQ-N-002 hard limit)
target_duration_seconds: 300  # 5-minute soft target
cron_schedule: "30 5 * * *"
hil_deadline: "05:45"
nodes:
  - relevance_analyst
  - anomaly_detector
  - historical_context_agent
  - recommendation_synthesizer
  - evaluate_quality          # always second-to-last
  - narrative_writer          # always last AgentNode
```

Add `MORNING_BRIEF_DEFAULT_SEND_TIME=06:00` and `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` to `settings.py` and `.env.example`. Validate required vars at startup (fail fast).

**AC covered:** AC-001 (budget and timing config), AC-002 (default dispatch time D7)

---

### TASK-003: DeterministicNodes — `fetch_portfolio`, `fetch_overnight_events`, `recompute_scores` · M/TDD · src/ai/workflows/morning_brief/nodes/fetch_portfolio.py, src/ai/workflows/morning_brief/nodes/fetch_overnight_events.py, src/ai/workflows/morning_brief/nodes/recompute_scores.py, tests/ai/workflows/morning_brief/test_nodes.py

Implement the three opening DeterministicNodes. Each is a plain Python function `(state: MorningBriefState) -> MorningBriefState`.

- `fetch_portfolio`: calls `get_portfolio_state(user_id, tenant_id)` tool; populates `state.portfolio_state`; raises `WorkflowAbortError` if portfolio is empty.
- `fetch_overnight_events`: calls `query_recent_events(since=prev_market_close, tenant_id)` tool; populates `state.events`; handles `InsufficientData` gracefully (empty events → workflow logs "no events" and exits cleanly without sending brief).
- `recompute_scores`: calls `get_company_score_history` and scoring service for each portfolio company affected by `state.relevant_events`; populates `state.score_changes`.

No LLM calls. All tool calls return bounded Pydantic results (≤ 50 rows per call per §7.3).

**Tests to write first (TDD):**
- `test_fetch_portfolio_populates_state()` — mock tool returns portfolio; assert state.portfolio_state populated
- `test_fetch_portfolio_aborts_on_empty_portfolio()` — tool returns empty; assert WorkflowAbortError
- `test_fetch_overnight_events_handles_insufficient_data()` — tool raises InsufficientData; assert state.events == [] and workflow continues
- `test_recompute_scores_updates_score_changes()` — mock score history; assert state.score_changes populated

**AC covered:** AC-001 (pipeline preconditions), AC-005 (node failures must not lose prior state)

---

### TASK-004: AgentNode wrappers — Relevance Analyst and Anomaly Detector · L/TDD · src/ai/workflows/morning_brief/nodes/relevance_analyst_node.py, src/ai/workflows/morning_brief/nodes/anomaly_detector_node.py, tests/ai/workflows/morning_brief/test_nodes.py

Implement `relevance_analyst_node` and `anomaly_detector_node` as `AgentNode` wrappers. Each:
1. Retrieves the agent definition from `AgentRegistry` by `role_id`.
2. Invokes the agent via `AgentRegistry.invoke(role_id, state_dict, tools_allowed)`.
3. Parses the typed output (`RelevanceAnalysis` / `AnomalyReport`) and merges it into `WorkflowState`.
4. Accumulates `cost_usd` and `tokens_consumed` into `state`.
5. Stores `agent.confidence` in `state.confidence_scores[role_id]`.
6. On `LimitExceededError` from `ExecutionLimiter`, sets `state.requires_hil = True`, `state.hil_reason = "budget_exceeded"`, and returns state to trigger routing.
7. Records agent invocation via `agent_invocation` repository (Layer 1 episodic — from PLAN-F-015 tables).

`relevance_analyst` runs on Sonnet 4.6 and populates `state.relevant_events` from `state.events`.
`anomaly_detector` runs on Sonnet 4.6 and populates `state.anomalies` from `state.score_changes`.

**Tests to write first (TDD):**
- `test_relevance_analyst_filters_events()` — mock agent returns 2 of 5 events as relevant; assert state.relevant_events has 2
- `test_relevance_analyst_accumulates_cost()` — mock agent costs $0.05; assert state.cost_usd == 0.05
- `test_relevance_analyst_sets_confidence_score()` — mock agent confidence 0.82; assert state.confidence_scores["relevance_analyst"] == 0.82
- `test_relevance_analyst_routes_to_hil_on_limit_exceeded()` — mock LimitExceededError; assert state.requires_hil == True
- `test_anomaly_detector_populates_anomalies()` — mock agent; assert state.anomalies populated
- `test_anomaly_detector_confidence_stored()` — mock agent confidence 0.55; assert stored in confidence_scores

**AC covered:** AC-001 (node execution), AC-005 (LimitExceededError handled without crash), AC-006 (confidence accumulated)

---

### TASK-005: AgentNode wrapper — Historical Context Agent (parallel per event) · L/TDD · src/ai/workflows/morning_brief/nodes/historical_context_node.py, tests/ai/workflows/morning_brief/test_nodes.py

Implement `historical_context_node`. This node uses `asyncio.gather` to invoke the `historical_context_agent` (Opus 4.7) in parallel for each event in `state.relevant_events`. Each parallel invocation:
- Calls `find_similar_events` and `get_price_reaction_to_event` tools.
- Returns an `AnalogiesResult` keyed by `event_id`.
- Is recorded as a sibling Langfuse span under the workflow trace.

After all invocations resolve, merge results into `state.analogies: dict[event_id, list[Analogy]]`. Overall `historical_context_agent` confidence = minimum confidence across all parallel invocations (per §7.2 minimum-confidence rule).

Cost and token counts from all parallel calls are summed into `state.cost_usd` and `state.tokens_consumed`. If total accumulated cost exceeds `cost_ceiling_usd * 0.80` at this point, log a warning and pass reduced token budgets to the remaining agents.

**Tests to write first (TDD):**
- `test_historical_context_parallel_invocations()` — 3 relevant events; mock agent called 3 times via gather; assert len(state.analogies) == 3
- `test_historical_context_minimum_confidence()` — 3 invocations with confidences [0.9, 0.45, 0.8]; assert state.confidence_scores["historical_context_agent"] == 0.45
- `test_historical_context_cost_accumulation()` — 3 invocations each $0.10; assert state.cost_usd += 0.30
- `test_historical_context_empty_events_no_op()` — state.relevant_events == []; assert state.analogies == {} and no agent invoked
- `test_historical_context_span_per_invocation()` — mock Langfuse; assert 3 child spans created

**AC covered:** AC-001 (parallel execution within budget), AC-005 (each parallel call checkpointed), AC-006 (confidence minimum propagated)

---

### TASK-006: AgentNode wrappers — Recommendation Synthesizer · M/TDD · src/ai/workflows/morning_brief/nodes/recommendation_node.py, tests/ai/workflows/morning_brief/test_nodes.py

Implement `recommendation_node` wrapping the `recommendation_synthesizer` agent (Opus 4.7). The node receives the merged state after Historical Context and produces `state.recommendations: list[Recommendation]`. Each `Recommendation` carries: `action_signal` (HOLD/WATCH/BUY_OPP/REDUCE_RISK/HEDGE/CONTRARIAN), `company_id`, `direction`, `confidence`, `rationale`, `analogies_used`. The node also persists each recommendation to the `ai_recommendation` table via the storage repository. Confidence from this agent is stored in `state.confidence_scores["recommendation_synthesizer"]`.

**Tests to write first (TDD):**
- `test_recommendation_node_produces_recommendations()` — mock agent output; assert state.recommendations populated with correct action signals
- `test_recommendation_node_persists_to_db()` — mock repository; assert save_recommendation called once per recommendation
- `test_recommendation_node_confidence_stored()` — mock agent confidence 0.75; assert in confidence_scores
- `test_recommendation_node_on_empty_analogies()` — no analogies; agent still invoked; assert recommendations may be empty list

**AC covered:** AC-001 (synthesis step), AC-006 (confidence stored)

---

### TASK-007: AgentNode wrapper — evaluate_quality (LLM-as-judge, second-to-last) · L/TDD · src/ai/workflows/morning_brief/nodes/evaluate_quality_node.py, prompts/evaluators/quality_judge.md, tests/ai/workflows/morning_brief/test_nodes.py

Implement the `evaluate_quality_node` as the Tier 1 LLM-as-judge gate (§9). This is always the second-to-last node. It:
1. Invokes the `evaluate_quality` agent (Opus 4.7, model different from producing agents as required by §9).
2. Uses the `quality_judge.md` prompt assessing: factual grounding, confidence calibration, internal consistency, tool-use appropriateness.
3. Computes the overall `workflow_confidence` = `min(state.confidence_scores.values())`.
4. Sets `state.confidence_scores["evaluate_quality"]` to the judge's own score.
5. Sets `state.requires_hil = True` and `state.hil_reason` if `workflow_confidence < 0.70`.
6. Writes a Langfuse score linked to the producing trace.

This node outputs the final `confidence_route` that drives the conditional edge: auto-send / HIL / block.

Write `prompts/evaluators/quality_judge.md` with the judging dimensions, scoring rubric (0.0–1.0), and structured JSON output schema.

**Tests to write first (TDD):**
- `test_evaluate_quality_computes_minimum_confidence()` — confidence_scores has values [0.9, 0.65, 0.8]; assert workflow_confidence == 0.65
- `test_evaluate_quality_sets_requires_hil_on_low_confidence()` — workflow_confidence == 0.55; assert state.requires_hil == True
- `test_evaluate_quality_auto_send_path()` — all scores ≥ 0.7; assert state.requires_hil == False; route == AUTO_SEND
- `test_evaluate_quality_block_path()` — min score < 0.4; assert confidence_route == BLOCK
- `test_evaluate_quality_writes_langfuse_score()` — mock Langfuse client; assert score written with correct trace_id
- `test_evaluate_quality_is_second_to_last_enforced()` — WorkflowStructureValidator (PLAN-F-011) rejects graph where evaluate_quality is not second-to-last

**AC covered:** AC-006 (evaluate_quality is second-to-last; its confidence is the determinative routing input)

---

### TASK-008: confidence_router conditional edge and `block_and_log` terminal node · M/TDD · src/ai/workflows/morning_brief/routing.py, src/ai/workflows/morning_brief/nodes/block_and_log.py, tests/ai/workflows/morning_brief/test_routing.py

Implement `confidence_router(state) -> str` as the LangGraph conditional edge function called after `evaluate_quality_node`. Returns one of: `"narrative_writer"` (≥ 0.70), `"hil_queue"` (0.40–0.69), `"block_and_log"` (< 0.40).

Implement `block_and_log` as a terminal `DeterministicNode`:
1. Creates a `BriefRow` with `hil_status=NOT_REQUIRED` and `sent_at=None`.
2. Persists the `BriefRow` to the `brief` table via storage repository.
3. Writes a `workflow_run` row with `status="blocked"`.
4. Writes a Layer 1 episodic memory entry recording the blocked run.
5. Does NOT dispatch any email.

This node satisfies the requirement that "admin AI audit console records the blocked run" (AC-004).

**Tests to write first (TDD):**
- `test_router_returns_narrative_writer_on_high_confidence()` — confidence 0.75; assert returns "narrative_writer"
- `test_router_returns_hil_on_medium_confidence()` — confidence 0.55; assert returns "hil_queue"
- `test_router_returns_block_on_low_confidence()` — confidence 0.35; assert returns "block_and_log"
- `test_router_boundary_0_70_is_auto_send()` — confidence exactly 0.70; assert "narrative_writer"
- `test_router_boundary_0_40_is_hil()` — confidence exactly 0.40; assert "hil_queue"
- `test_block_and_log_persists_brief_row()` — mock repository; assert BriefRow saved with hil_status NOT_REQUIRED
- `test_block_and_log_writes_episodic_memory()` — mock episodic repo; assert entry written with status "blocked"

**AC covered:** AC-004 (block path recorded in audit), AC-006 (routing decision driven by evaluate_quality output)

---

### TASK-009: AgentNode wrapper — Narrative Writer (last AgentNode) · M/TDD · src/ai/workflows/morning_brief/nodes/narrative_writer_node.py, src/alerts/email_templates/morning_brief.html, tests/ai/workflows/morning_brief/test_nodes.py

Implement `narrative_writer_node` wrapping the `narrative_writer` agent (Opus 4.7). This is always the last AgentNode in the workflow. It receives the complete state (portfolio, events, recommendations, analogies) and produces an HTML email body in the `state.report` field. The agent uses the "FT columnist voice, not AI assistant voice" persona (§7.2). The output HTML is rendered into the `morning_brief.html` Jinja2 template (responsive, SendGrid-compatible).

This node runs only when confidence routing directed to `narrative_writer` (i.e., after auto-send or HIL-approved path). It must not run on the block path.

Write `src/alerts/email_templates/morning_brief.html`: responsive two-column layout, company score cards, event summaries, recommendation table, confidence indicator, and a traceable "Why this read?" footer link.

**Tests to write first (TDD):**
- `test_narrative_writer_produces_html_report()` — mock agent returns prose; assert state.report is non-empty HTML string
- `test_narrative_writer_injects_into_template()` — rendered HTML contains expected portfolio and event content
- `test_narrative_writer_not_invoked_on_block_path()` — state.confidence_route == BLOCK; assert narrative_writer not called
- `test_narrative_writer_is_last_agent_node()` — WorkflowStructureValidator (PLAN-F-011) rejects graph where narrative_writer is not last

**AC covered:** AC-002 (email content produced before dispatch), AC-006 (narrative_writer only runs after evaluate_quality routing)

---

### TASK-010: `format_and_dispatch` DeterministicNode and SendGrid integration · M/TDD · src/ai/workflows/morning_brief/nodes/format_and_dispatch.py, src/alerts/sendgrid_dispatcher.py, tests/ai/workflows/morning_brief/test_nodes.py

Implement the `format_and_dispatch` DeterministicNode (runs after `narrative_writer_node` on the auto-send or HIL-approved path):
1. Reads `state.report` (HTML).
2. Reads `user.dispatch_time` from the user settings repository (D7 per-user configurable send time; defaults to `06:00`).
3. Calls `sendgrid_dispatcher.send_morning_brief(to_email, subject, html_body, brief_id, scheduled_for)` using SendGrid's scheduled send feature to land at the user's configured dispatch time.
4. On successful dispatch: updates `BriefRow.sent_at = now()`, `BriefRow.hil_status = NOT_REQUIRED` (or `APPROVED` if HIL path).
5. On SendGrid error: logs structured error, sets `workflow_run.status = "dispatch_failed"`, does not raise (brief is persisted; retry can be triggered manually).

`sendgrid_dispatcher.send_morning_brief()` sends via SendGrid API with the `SENDGRID_MORNING_BRIEF_TEMPLATE_ID` and a `X-Brief-ID` custom header for deduplication.

**Tests to write first (TDD):**
- `test_format_and_dispatch_calls_sendgrid_with_correct_params()` — mock SendGrid client; assert called with user email, brief_id in header, scheduled send time
- `test_format_and_dispatch_updates_brief_sent_at()` — mock repo; assert BriefRow.sent_at updated on success
- `test_format_and_dispatch_handles_sendgrid_error_gracefully()` — mock SendGrid raises; assert no exception raised; workflow_run status = "dispatch_failed"
- `test_format_and_dispatch_reads_user_dispatch_time()` — user settings has dispatch_time 07:30; assert SendGrid scheduled_for = 07:30 local
- `test_format_and_dispatch_uses_default_time_if_unset()` — user.dispatch_time is null; assert defaults to 06:00

**AC covered:** AC-002 (email dispatched by user's configured time), AC-003 (HIL-approved path leads here)

---

### TASK-011: HIL queue routing node and `hil_timeout_handler` · L/TDD · src/ai/workflows/morning_brief/nodes/hil_queue_node.py, src/ai/workflows/morning_brief/hil_timeout_handler.py, tests/ai/workflows/morning_brief/test_hil_timeout.py

Implement `hil_queue_node` as a `DeterministicNode` invoked when confidence is 0.40–0.69:
1. Persists a `BriefRow` with `hil_status=PENDING`.
2. Calls `HILQueueRepository.enqueue(brief_id, review_deadline="05:45", workflow_checkpoint_id)` (from PLAN-F-013).
3. Checkpoints the LangGraph state to PostgreSQL (graph pauses; not killed).
4. Returns without dispatching email.

Implement `hil_timeout_handler`: a Celery beat task scheduled at `45 5 * * *` (05:45) that:
1. Queries `brief` table for rows with `hil_status=PENDING` and `type=morning_brief`.
2. For each unreviewed row: sets `hil_status=TIMED_OUT`, does NOT resume the graph, notifies the user via SendGrid (plain-text "No Morning Brief today" email).
3. For each approved row (set by HIL reviewer via PLAN-F-013 API): resumes the LangGraph graph from checkpoint → runs `narrative_writer_node` → `format_and_dispatch`.
4. Writes Layer 4 feedback entry for every timed-out item.

**Tests to write first (TDD):**
- `test_hil_queue_node_persists_pending_brief()` — mock repo; assert BriefRow saved with hil_status PENDING
- `test_hil_queue_node_calls_hil_enqueue()` — mock HILQueueRepository; assert enqueue called with correct deadline
- `test_hil_queue_node_does_not_dispatch_email()` — mock SendGrid; assert never called
- `test_hil_timeout_handler_marks_unreviewed_as_timed_out()` — 2 pending briefs at 05:45; neither reviewed; assert both set to TIMED_OUT
- `test_hil_timeout_handler_sends_notification_on_timeout()` — mock SendGrid; assert "No Morning Brief today" email sent per user
- `test_hil_timeout_handler_resumes_graph_for_approved()` — 1 pending brief approved by reviewer; assert graph.resume() called with checkpoint_id
- `test_hil_timeout_handler_writes_feedback_on_timeout()` — mock user_feedback repo; assert Layer 4 entry written

**AC covered:** AC-003 (HIL routing, 05:45 timeout, hold-and-notify), AC-005 (checkpoint and resume on HIL path)

---

### TASK-012: LangGraph StateGraph assembly and PostgreSQL checkpointing · L/TDD · src/ai/workflows/morning_brief/graph.py, tests/ai/workflows/morning_brief/test_graph.py

Assemble the `MorningBriefGraph` using LangGraph `StateGraph(MorningBriefState)`:

```
fetch_portfolio
  → fetch_overnight_events
  → relevance_analyst_node
  → recompute_scores
  → anomaly_detector_node
  → historical_context_node (asyncio.gather internally)
  → recommendation_node
  → evaluate_quality_node
  → [conditional edge: confidence_router]
      "narrative_writer"  → narrative_writer_node → format_and_dispatch  [END]
      "hil_queue"         → hil_queue_node                                [PAUSE]
      "block_and_log"     → block_and_log                                 [END]
```

Configure PostgreSQL checkpointing: `AsyncPostgresSaver` from `langgraph.checkpoint.postgres` using `DATABASE_URL`. Checkpoint is written after every node by LangGraph. Verify `WorkflowStructureValidator` (from PLAN-F-011) passes before compilation.

Implement `MorningBriefWorkflow.run(user_id, tenant_id) -> WorkflowResult` as the single public interface: creates `MorningBriefState`, opens Langfuse trace, calls `graph.ainvoke(state)`, persists `workflow_run` row, closes trace.

**Tests to write first (TDD):**
- `test_graph_compiles_without_error()` — assert StateGraph.compile() raises no exception
- `test_graph_workflow_structure_validator_passes()` — WorkflowStructureValidator from PLAN-F-011 validates the compiled graph
- `test_graph_checkpoint_written_after_each_node()` — mock AsyncPostgresSaver; assert checkpoint saved after each node invocation
- `test_graph_resume_from_checkpoint()` — simulate node failure after recompute_scores; restore from checkpoint; assert workflow resumes from recompute_scores not fetch_portfolio
- `test_graph_langfuse_trace_opened_and_closed()` — mock Langfuse; assert trace.start() and trace.end() called; langfuse_trace_id written to workflow_run
- `test_graph_workflow_run_row_persisted()` — mock workflow_run repo; assert row written with workflow_id, tenant_id, cost_usd, langfuse_trace_id

**AC covered:** AC-005 (PostgreSQL checkpointing and resume), AC-006 (graph structure enforces evaluate_quality second-to-last), REQ-N-008 (one Langfuse trace per run)

---

### TASK-013: Celery cron task — `morning_brief_task` · S/no-TDD · src/ai/tasks/morning_brief_task.py, src/config/celery_app.py

Implement the Celery task `run_morning_brief_for_user(user_id: str, tenant_id: str)` with:
- `@celery_app.task(name="morning_brief.run_for_user", max_retries=1, acks_late=True)`
- Resolves `user.dispatch_time` from DB to check user has an active morning brief subscription.
- Instantiates `MorningBriefWorkflow` and calls `await workflow.run(user_id, tenant_id)`.
- On exception: logs error with `workflow_id`, `user_id`, `tenant_id`; does not retry automatically (the 05:45 window is too narrow for safe retry without risk of duplicate send).

Register in `celery_app.py` beat schedule:
```python
"morning-brief-dispatch": {
    "task": "morning_brief.dispatch_all_users",
    "schedule": crontab(hour=5, minute=30),
}
```

Add dispatcher task `morning_brief.dispatch_all_users` that queries all users with `morning_brief_enabled=True` and enqueues one `run_morning_brief_for_user` per user.

**AC covered:** AC-001 (cron fires at 05:30, dispatches per user)

---

### TASK-014: CostGuard and per-workflow budget enforcement · M/TDD · src/ai/workflows/morning_brief/cost_guard.py, tests/ai/workflows/morning_brief/test_cost_guard.py

Implement `CostGuard` class that:
1. Holds a reference to `MorningBriefState` (by reference, updated in-place).
2. After each agent node, calls `guard.check(state)` to compare `state.cost_usd` against `cost_ceiling_usd`.
3. At 80% of ceiling: logs `WARNING cost_ceiling_approach`; calls `guard.reduce_token_budgets(remaining_agents)` which injects a `token_budget_override` dict into state.
4. At 100% of ceiling: raises `WorkflowCostCeilingExceeded`; graph routes to `block_and_log`.

`MorningBriefGraph` wraps each AgentNode call in a `CostGuard.check()` call via a decorator pattern — no change to node function signatures.

**Tests to write first (TDD):**
- `test_cost_guard_allows_below_ceiling()` — cost 0.50, ceiling 2.00; assert no warning, no exception
- `test_cost_guard_warns_at_80_pct()` — cost 1.62, ceiling 2.00; assert WARNING logged; reduce_token_budgets called
- `test_cost_guard_raises_at_ceiling()` — cost 2.01, ceiling 2.00; assert WorkflowCostCeilingExceeded raised
- `test_cost_guard_reduce_token_budgets_injects_override()` — assert state gains token_budget_override dict with reduced values

**AC covered:** AC-001 (cost ≤ $2.00 enforced at runtime), REQ-N-004

---

### TASK-015: Integration tests — full workflow happy path and all routing branches · XL/TDD · tests/integration/test_morning_brief_e2e.py, tests/ai/workflows/morning_brief/test_graph.py

Write integration tests covering the complete workflow against a real PostgreSQL test database with mocked LLM (Anthropic) and mocked SendGrid:

1. **Happy path (auto-send):** Seed portfolio + 3 overnight events; run `MorningBriefWorkflow.run()`; assert `workflow_run.status = "completed"`; `brief.sent_at` is set; `brief.hil_status = NOT_REQUIRED`; `state.report` is non-empty HTML; SendGrid mock received one call.

2. **HIL path (medium confidence):** Mock `evaluate_quality` to return confidence 0.55; assert workflow pauses at `hil_queue_node`; `brief.hil_status = PENDING`; graph checkpoint saved to PostgreSQL. Then simulate HIL approval: call `hil_timeout_handler` with approved=True; assert graph resumes; `narrative_writer_node` called; email dispatched.

3. **HIL timeout path:** Mock `evaluate_quality` to return confidence 0.55; run workflow; run `hil_timeout_handler` without approving; assert `brief.hil_status = TIMED_OUT`; "No Morning Brief today" email sent; original brief not dispatched.

4. **Block path (low confidence):** Mock `evaluate_quality` to return confidence 0.30; assert `brief.hil_status = NOT_REQUIRED`; `brief.sent_at = None`; `workflow_run.status = "blocked"`; SendGrid mock never called.

5. **Node failure recovery:** Simulate exception mid-graph (after `anomaly_detector_node`); assert `workflow_run.status = "failed"`; checkpoint in PostgreSQL at `anomaly_detector_node`; re-running workflow from checkpoint skips `fetch_portfolio` and `fetch_overnight_events` and resumes from `anomaly_detector_node`.

6. **Cost ceiling breach:** Mock cumulative cost > $2.00 mid-run; assert `WorkflowCostCeilingExceeded`; workflow routes to block; brief not sent.

**Tests to write first (TDD):**
- (All six scenarios above, each as a distinct `pytest` function using `pytest-asyncio` and a real `AsyncPostgresSaver`.)

**AC covered:** AC-001, AC-002, AC-003, AC-004, AC-005, AC-006 (all ACs covered by this task via integration-level verification)

---

## Acceptance Criteria Coverage

- AC-001: Cron fires at 05:30; workflow completes within 10 min or routes to HIL; cost ≤ $2.00 → TASK-002 (cron config), TASK-003 (DeterministicNodes), TASK-013 (Celery task), TASK-014 (CostGuard), TASK-015 (e2e)
- AC-002: Confidence ≥ 0.7 → HTML email dispatched by user's configured time → TASK-009 (Narrative Writer), TASK-010 (SendGrid dispatch), TASK-012 (routing graph), TASK-015 (happy path e2e)
- AC-003: Confidence 0.4–0.69 → HIL queue; if unreviewed by 05:45, withheld and user notified → TASK-011 (HIL node + timeout handler), TASK-015 (HIL path + timeout e2e)
- AC-004: Confidence < 0.4 → blocked; admin audit console records run → TASK-008 (block_and_log node), TASK-015 (block path e2e)
- AC-005: Node failure → LangGraph checkpoint persisted; replay from last successful node → TASK-001 (state schema), TASK-012 (graph + PostgreSQL checkpointing), TASK-015 (failure recovery e2e)
- AC-006: evaluate_quality runs second-to-last; its confidence is the determinative routing input → TASK-007 (evaluate_quality node), TASK-008 (confidence_router), TASK-012 (graph structure validation)

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | What is the exact per-workflow HIL timing window between 05:30 start and 05:45 deadline? Is 05:45 a hard deadline for all users regardless of timezone? | Unresolved at planning time. ARCHITECTURE.md §7.6 documents the 05:45 deadline without timezone qualification. This plan implements 05:45 as a wall-clock UTC cutoff (the cron fires at 05:30 UTC). If per-timezone HIL deadlines are required, `hil_timeout_handler` must be extended to compute per-user deadline from `user.dispatch_time` — this is a one-function change isolated in `hil_timeout_handler.py`. |

## Risks and Notes

- **LangGraph version pinning:** The `AsyncPostgresSaver` API changed between LangGraph 0.1 and 0.2. Pin `langgraph>=0.2` in `pyproject.toml` and test checkpoint round-trips in TASK-015 against the pinned version.
- **HIL resume race condition:** If a HIL reviewer approves at 05:44:59 and the `hil_timeout_handler` beat task fires at 05:45:00, a race is possible. Implement the timeout handler with a `SELECT ... FOR UPDATE SKIP LOCKED` advisory lock on the `brief` row to prevent double-processing.
- **asyncio.gather and LangGraph event loop:** LangGraph's async runner must be confirmed to support nested `asyncio.gather` inside a node. If not, use `asyncio.run_coroutine_threadsafe` from within the node or upgrade to a LangGraph version that supports it. Validate in TASK-005.
- **SendGrid scheduled send:** The SendGrid API's scheduled send feature has a minimum future delay of 10 minutes. If the workflow completes at 05:58 with a 06:00 target, scheduled delivery may not be possible and the dispatcher should send immediately instead. Implement fallback in `format_and_dispatch`.
- **Missing PLAN-F-012 (Tool Library):** The agent nodes depend on typed tool functions from PLAN-F-012. Mocking those tools is sufficient for unit tests (TASK-004 to TASK-009), but TASK-015 integration tests require the real Tool Library to be available. Confirm PLAN-F-012 is executed before TASK-015.
- **`evaluate_quality` prompt cold-start:** `prompts/evaluators/quality_judge.md` is written in TASK-007 but is not Langfuse-published until the CI pipeline runs. For the first integration test run, the prompt must be loaded from the local file system, not Langfuse (add a `LOCAL_PROMPTS=true` env var for test environments).
- **Cost tracking precision:** `WorkflowState.cost_usd` accumulates float additions. Use `decimal.Decimal` internally and convert to float only when persisting to the `brief` and `workflow_run` tables to avoid floating-point drift across 6–7 agent invocations.
