---
plan_id: PLAN-F-027
slug: qa-chat-interface
title: Q&A Chat Interface
linked_requirement: REQ-F-027
type: functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-003, reason: "cost_ceiling_usd enforced per-agent for qa-analyst; partial-answer path on breach" }
  - { id: REQ-N-006, reason: "all DB queries and tool calls scoped to tenant_id + user_id" }
  - { id: REQ-N-008, reason: "every Q&A session persisted to episodic memory (Layer 1) for audit" }
  - { id: REQ-N-012, reason: "complete reasoning chain stored; session messages append-only in episodic layer" }
dependencies:
  - { id: PLAN-F-011, reason: "qa-analyst agent YAML definition and ExecutionLimiter are prerequisite" }
  - { id: PLAN-F-012, reason: "Tool Library provides portfolio-scoped tools the Q&A Analyst invokes" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-027 — Q&A Chat Interface

## Linked Requirement
**REQ-F-027** — Q&A Chat Interface
Status: approved | Jira:

## Objective

Implement an interactive Q&A chat interface that allows users to ask natural-language questions about their own portfolio companies and event archive. The backend introduces a `QASession` persistence layer, a `QAWorkflow` LangGraph graph that invokes the `qa_analyst` agent (Opus 4.7, `max_iterations=10`, cost-ceiling enforced), and a scope guard that rejects questions about companies outside the user's portfolio or watchlist. The frontend extends the React application with a chat panel that streams responses and renders cited sources and per-answer confidence scores. Every session and message is appended to episodic memory (Layer 1) for auditability.

## Architecture Context

This plan touches three architecture layers. In **Layer 4 — Processing** it introduces `src/ai/workflows/qa_workflow.py`, a LangGraph `StateGraph` with `DeterministicNode` and `AgentNode` following the same pattern as the five core workflows (Architecture §7.5). The `qa_analyst` role, already defined in `agents/qa-analyst.yaml` by PLAN-F-011 (Architecture §7.2, nine named roles), is the sole `AgentNode`; its `max_iterations=10` setting makes it the only looping agent in the system. All tool calls inside the agent node flow through the Tool Library from PLAN-F-012 (Architecture §7.3), which enforces `tenant_id`/`user_id` scoping and the 50-row output bound.

In **Layer 5 — Serving** it extends `src/api/` with two new routes: one to create or retrieve a `QASession`, one to submit a question and stream the response via Server-Sent Events (SSE). The `WorkflowState` already carries `tenant_id` and `user_id` (Architecture §7.1), so cross-tenant leakage is prevented structurally.

In **Layer 6 — Presentation** it introduces a `QAChatPanel` React component reachable from the Deep-Dive report entry point described in Architecture §11 (Progressive Disclosure: "Deep-dive report, scenario tree, Q&A entry point"). The panel uses TanStack Query for session state and the browser `EventSource` API for streaming.

The `QASession` and `QAMessage` rows are written to the `workflow_run` and a new `qa_message` table backed by the episodic memory layer (Architecture §7.4, Layer 1) — append-only, auditable.

Cost governance follows Architecture §12.6: `cost_ceiling_usd` is read from the `qa-analyst.yaml` definition; when the `ExecutionLimiter` from PLAN-F-011 raises `LimitExceededError(LimitType.COST_CEILING, ...)`, the workflow catches it, marks the answer as `cost_limited=True`, and returns the partial answer to the caller rather than raising an unhandled error.

## Component Design

### New Components

```
Backend:
src/ai/workflows/
  qa_workflow.py               — QAWorkflow: LangGraph StateGraph for Q&A
  qa_state.py                  — QAWorkflowState (extends WorkflowState with chat-specific fields)

src/ai/qa/
  __init__.py
  session_service.py           — QASessionService: create/fetch/append session + messages
  scope_guard.py               — QAScopeGuard: validates question scope against user portfolio
  response_builder.py          — QAResponseBuilder: assembles answer, sources, confidence, cost_limited flag

src/storage/models/
  qa_session.py                — SQLAlchemy ORM: QASession, QAMessage tables
src/storage/repositories/
  qa_repository.py             — QARepository (IQARepository interface + implementation)

src/api/routers/
  qa_router.py                 — FastAPI router: POST /api/v1/qa/sessions,
                                  POST /api/v1/qa/sessions/{session_id}/messages (SSE)

Alembic migration:
alembic/versions/XXXX_add_qa_session_tables.py

Tests:
tests/unit/ai/qa/
  test_qa_scope_guard.py
  test_qa_session_service.py
  test_qa_response_builder.py
tests/unit/ai/workflows/
  test_qa_workflow.py
tests/unit/storage/
  test_qa_repository.py
tests/integration/
  test_qa_router.py

Frontend:
src/frontend/src/components/qa/
  QAChatPanel.tsx              — top-level chat panel component
  QAMessageList.tsx            — scrollable message thread
  QAMessageBubble.tsx          — single message with confidence + sources
  QASourcesList.tsx            — collapsible cited-sources section
  QACostLimitNotice.tsx        — inline notice when cost_limited=true
  useQASession.ts              — TanStack Query hook: session CRUD
  useQAStream.ts               — EventSource hook: streaming answer delivery

src/frontend/src/api/
  qaApi.ts                     — typed API client for Q&A endpoints

Prompt file (stub, content managed by PLAN-F-014):
prompts/agents/qa_analyst.md   — already created by PLAN-F-011; this plan adds scope-constraint section
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/startup.py` | Register `QAWorkflow` graph, call `WorkflowStructureValidator` on its node sequence | All workflows validated at startup |
| `src/api/main.py` | Mount `qa_router` under `/api/v1/qa` | Expose Q&A endpoints |
| `src/storage/models/__init__.py` | Export `QASession`, `QAMessage` ORM models | Consistent model surface |
| `prompts/agents/qa_analyst.md` | Append scope-constraint section: agent must decline out-of-portfolio queries and suggest watchlist addition | Fulfils AC-004 instruction path |
| `alembic/env.py` | Include new ORM models in autogenerate metadata | Migration picks up new tables |

### Interfaces and Contracts

```python
# src/storage/repositories/qa_repository.py

from typing import Protocol
from uuid import UUID
from src.storage.models.qa_session import QASession, QAMessage

class IQARepository(Protocol):
    async def create_session(self, session: QASession) -> QASession: ...
    async def get_session(self, session_id: UUID, user_id: UUID, tenant_id: UUID) -> QASession | None: ...
    async def append_message(self, message: QAMessage) -> QAMessage: ...
    async def get_messages(self, session_id: UUID, tenant_id: UUID) -> list[QAMessage]: ...
```

```python
# src/ai/qa/scope_guard.py

from uuid import UUID
from pydantic import BaseModel

class ScopeCheckResult(BaseModel):
    in_scope: bool
    out_of_scope_tickers: list[str]   # tickers referenced in question but not in portfolio/watchlist
    suggestion: str | None            # e.g. "Add TSLA to your watchlist to ask about it"

class QAScopeGuard:
    """Validates that a question does not reference companies outside the user's portfolio/watchlist."""

    async def check(
        self,
        question: str,
        user_id: UUID,
        tenant_id: UUID,
    ) -> ScopeCheckResult:
        """
        Returns ScopeCheckResult. If in_scope is False the caller must NOT invoke the agent;
        instead it returns the suggestion text as the assistant reply.
        """
        ...
```

```python
# src/ai/qa/response_builder.py

from pydantic import BaseModel, Field
from typing import Any

class QASource(BaseModel):
    type: str          # "event" | "filing" | "price_bar" | "recommendation" | "semantic_fact"
    id: str
    description: str

class QAAnswer(BaseModel):
    answer_text: str
    sources: list[QASource]
    confidence: float = Field(ge=0.0, le=1.0)
    cost_usd: float
    cost_limited: bool = False   # True when ExecutionLimiter raised LimitExceededError(COST_CEILING)
```

```python
# src/ai/workflows/qa_state.py

from pydantic import BaseModel
from uuid import UUID
from src.ai.workflows.base import WorkflowState
from src.ai.qa.response_builder import QAAnswer

class QAWorkflowState(WorkflowState):
    session_id: UUID
    question: str
    conversation_history: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": ...}]
    answer: QAAnswer | None = None
    scope_check_passed: bool = False
    out_of_scope_suggestion: str | None = None
```

```python
# src/api/routers/qa_router.py  (key endpoint signatures)

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from uuid import UUID

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])

@router.post("/sessions")
async def create_or_get_session(
    payload: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    """Create a new QASession or return an existing open session for this user."""
    ...

@router.post("/sessions/{session_id}/messages")
async def submit_question(
    session_id: UUID,
    payload: QuestionRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Accepts a user question. Runs QAWorkflow asynchronously.
    Returns an SSE stream: data events carry partial answer chunks;
    a final 'done' event carries the complete QAAnswer JSON.
    """
    ...
```

---

## Implementation Tasks

### TASK-001: QASession and QAMessage ORM models + migration · M/TDD · src/storage/models/qa_session.py,src/storage/models/__init__.py,alembic/versions/XXXX_add_qa_session_tables.py,tests/unit/storage/test_qa_repository.py

Define SQLAlchemy 2.0 async ORM models for `QASession` and `QAMessage` as specified in the requirement data model. `QASession` carries `session_id UUID PK`, `user_id UUID NOT NULL`, `tenant_id UUID NOT NULL`, `workflow_run_id UUID FK→workflow_run`, `created_at`, `updated_at`. `QAMessage` carries `message_id UUID PK`, `session_id UUID FK→qa_session`, `tenant_id UUID NOT NULL`, `role VARCHAR CHECK(role IN ('user','assistant'))`, `content TEXT NOT NULL`, `sources JSONB NULL`, `confidence FLOAT NULL`, `cost_usd FLOAT NULL`, `cost_limited BOOL DEFAULT FALSE`, `created_at`. Both tables have no `DELETE` triggers (append-only per Architecture §7.4 Layer 1). Write `IQARepository` protocol and `QARepository` implementation. Write the Alembic migration.

**Tests to write first (TDD):**
- `test_create_session_persists_all_fields` — assert all columns round-trip through repository
- `test_get_session_enforces_tenant_id` — get_session with wrong tenant_id returns None (IDOR prevention)
- `test_append_message_links_to_session` — message FK resolves to session
- `test_get_messages_returns_ordered_by_created_at` — messages returned in insertion order
- `test_repository_rejects_invalid_role` — role value outside ('user','assistant') raises DB constraint

**AC covered**: AC-005

---

### TASK-002: QAScopeGuard — portfolio-scope enforcement · M/TDD · src/ai/qa/scope_guard.py,src/ai/qa/__init__.py,tests/unit/ai/qa/test_qa_scope_guard.py

Implement `QAScopeGuard`. It uses the `GetPortfolioPositions` and `GetWatchlist` tools from the Tool Library (PLAN-F-012) to retrieve the user's known tickers. It uses a lightweight regex + ticker extraction pass (no LLM call, no cost) to identify any company tickers or names explicitly referenced in the question. If all referenced companies are within the portfolio or watchlist, `in_scope=True`. If any are outside, `in_scope=False` with a `suggestion` string such as "TSLA is not in your portfolio or watchlist. Add it to your watchlist to ask about it." Questions that reference no specific company are always `in_scope=True` — the agent's tool-scoping will naturally constrain results to portfolio data. The guard is a `DeterministicNode` in the `QAWorkflow` graph and must not call any LLM.

**Tests to write first (TDD):**
- `test_question_with_portfolio_ticker_is_in_scope` — question mentioning a held ticker passes
- `test_question_with_no_ticker_reference_is_in_scope` — generic question ("what events affected my holdings?") passes
- `test_question_with_unknown_ticker_is_out_of_scope` — returns in_scope=False with non-empty suggestion
- `test_scope_guard_uses_tenant_id_for_portfolio_lookup` — portfolio tool called with correct tenant_id
- `test_suggestion_names_the_out_of_scope_ticker` — suggestion string contains the unknown ticker

**AC covered**: AC-004

---

### TASK-003: QAResponseBuilder and QAWorkflowState · S/no-TDD · src/ai/qa/response_builder.py,src/ai/workflows/qa_state.py,src/ai/workflows/__init__.py

Define the `QAAnswer` Pydantic model (`answer_text`, `sources: list[QASource]`, `confidence`, `cost_usd`, `cost_limited`). Define `QASource` (`type`, `id`, `description`). Implement `QAResponseBuilder.build(agent_output: dict, cost_limited: bool, accumulated_cost: float) -> QAAnswer` which parses the `qa_analyst` agent's structured JSON output (conforming to `agents/qa-analyst.yaml`'s `output_schema`) into a typed `QAAnswer`. If `cost_limited=True`, it sets the flag and trims `sources` to those collected before the limit was hit. Define `QAWorkflowState` extending `WorkflowState` with the Q&A-specific fields listed in the Interfaces section. The state must be Pydantic-serializable so LangGraph PostgreSQL checkpointing works without modification.

**AC covered**: AC-002, AC-003

---

### TASK-004: QAWorkflow LangGraph graph · M/TDD · src/ai/workflows/qa_workflow.py,tests/unit/ai/workflows/test_qa_workflow.py

Build the `QAWorkflow` as a LangGraph `StateGraph[QAWorkflowState]`. Node sequence:

1. `load_session_context` (DeterministicNode) — loads conversation history and portfolio scope from DB
2. `check_scope` (DeterministicNode) — calls `QAScopeGuard.check()`; if `in_scope=False`, writes the suggestion as the assistant answer and routes to `persist_message` (skipping the agent)
3. `run_qa_analyst` (AgentNode) — invokes `qa_analyst` with `max_iterations=10`; tool calls are scoped to the user's portfolio tools from the Tool Library; `ExecutionLimiter` monitors cost and iterations; on `LimitExceededError(COST_CEILING)`, sets `cost_limited=True` and continues to response builder with partial output
4. `build_response` (DeterministicNode) — calls `QAResponseBuilder.build()`
5. `persist_message` (DeterministicNode) — appends user message and assistant `QAMessage` rows via `QARepository`; writes `workflow_run` row to episodic memory

Call `WorkflowStructureValidator` in the graph constructor — note that this Q&A workflow does not include `evaluate_quality` or `narrative_writer` nodes (it is user-interactive, not a report workflow), so the validator is invoked only if the node list ends with those nodes; this workflow must explicitly be exempted or the validator must support a `skip_tail_invariant=True` parameter for interactive workflows. Document the exemption in code comments.

**Tests to write first (TDD):**
- `test_in_scope_question_reaches_agent_node` — mock scope guard returns in_scope=True; assert AgentNode invoked
- `test_out_of_scope_question_skips_agent_node` — mock scope guard returns in_scope=False; assert AgentNode NOT invoked; answer contains suggestion
- `test_cost_limit_reached_returns_partial_answer_with_flag` — mock ExecutionLimiter raises COST_CEILING; assert QAAnswer.cost_limited=True
- `test_workflow_persists_both_user_and_assistant_messages` — mock repository; assert append_message called twice (one per role)
- `test_workflow_writes_workflow_run_to_episodic_memory` — assert episodic memory service called with correct workflow_type

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-005: Q&A API router (REST + SSE) · M/TDD · src/api/routers/qa_router.py,src/api/main.py,tests/integration/test_qa_router.py

Implement two FastAPI endpoints:

`POST /api/v1/qa/sessions` — creates a new `QASession` for the authenticated user. Returns `{session_id, created_at}`. Requires JWT auth (`get_current_user` dependency). All session rows carry the user's `tenant_id`.

`POST /api/v1/qa/sessions/{session_id}/messages` — accepts `{question: str}`. Validates ownership of the session (IDOR prevention: `user_id + tenant_id` check). Enqueues `QAWorkflow` execution. Returns `StreamingResponse` with `media_type="text/event-stream"`. The SSE stream emits:
- `data: {"type": "chunk", "text": "..."}` — zero or more partial text chunks as the agent iterates
- `data: {"type": "done", "answer": <QAAnswer JSON>}` — final complete answer
- `data: {"type": "cost_limited", "partial_answer": <QAAnswer JSON>}` — when cost ceiling reached

Both endpoints are rate-limited. Mount `qa_router` on `src/api/main.py`.

**Tests to write first (TDD):**
- `test_create_session_returns_session_id` — authenticated POST; assert 200 + session_id UUID
- `test_create_session_requires_auth` — unauthenticated POST returns 401
- `test_submit_question_session_ownership_enforced` — question submitted to another user's session returns 403
- `test_submit_question_streams_done_event` — mock workflow returns QAAnswer; assert SSE stream contains 'done' event with answer JSON
- `test_submit_question_streams_cost_limited_event` — mock workflow returns cost_limited=True; assert SSE stream type is 'cost_limited'

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-006: Frontend QAChatPanel and message thread · M/TDD · src/frontend/src/components/qa/QAChatPanel.tsx,src/frontend/src/components/qa/QAMessageList.tsx,src/frontend/src/components/qa/QAMessageBubble.tsx,src/frontend/src/components/qa/QASourcesList.tsx,src/frontend/src/components/qa/QACostLimitNotice.tsx,src/frontend/src/api/qaApi.ts,src/frontend/src/components/qa/useQASession.ts,src/frontend/src/components/qa/useQAStream.ts

Build the React chat UI. `QAChatPanel` renders a scrollable message thread (`QAMessageList`) and a text-input footer. Each message is a `QAMessageBubble` which for assistant messages shows:
- Answer text
- Confidence score rendered as a labelled percentage badge (e.g. "Confidence: 87%")
- `QASourcesList` — collapsible list of cited sources (type icon + description)
- `QACostLimitNotice` — shown only when `cost_limited=true`; text: "Cost limit reached — this answer may be incomplete."

`useQASession` wraps TanStack Query for session creation and history fetch. `useQAStream` wraps `EventSource` for the streaming message endpoint; it appends chunks to local state in real time and finalises the bubble on the `done` event. Write unit tests using React Testing Library for the rendering logic. Do not test `EventSource` internals — mock `useQAStream` in component tests.

**Tests to write first (TDD):**
- `test_QAMessageBubble_renders_confidence_score` — renders "87%" given confidence=0.87
- `test_QAMessageBubble_renders_sources_list` — renders source descriptions when sources non-empty
- `test_QAMessageBubble_shows_cost_limit_notice_when_flagged` — cost_limited=true shows notice
- `test_QAMessageBubble_hides_cost_limit_notice_when_not_flagged` — cost_limited=false hides notice
- `test_QAChatPanel_submits_question_on_enter_key` — simulates Enter keypress; assert useQAStream called
- `test_QASourcesList_is_collapsed_by_default_and_expands_on_click`

**AC covered**: AC-002, AC-003

---

### TASK-007: qa-analyst.yaml scope-constraint prompt update · S/no-TDD · prompts/agents/qa_analyst.md,agents/qa-analyst.yaml

Add a "Scope Constraint" section to `prompts/agents/qa_analyst.md` instructing the agent to: (1) only use tools that are scoped to the user's portfolio and watchlist companies; (2) if a tool returns no data for a company (because it is outside the portfolio), respond that the company is outside the user's portfolio scope and suggest adding it to the watchlist; (3) never speculate about companies not accessible via tool results. Verify that `agents/qa-analyst.yaml` already contains `max_iterations: 10` and the correct Opus 4.7 model (these were set in PLAN-F-011); add the `cost_ceiling_usd` and `timeout_seconds` values appropriate for an interactive session (cost ceiling: 0.40 USD; timeout: 120 seconds) if not already present.

**AC covered**: AC-001, AC-004

---

### TASK-008: Episodic memory integration for Q&A sessions · S/no-TDD · src/ai/workflows/qa_workflow.py,src/ai/memory/services/memory_service.py

Wire the `persist_message` node in `QAWorkflow` to write a `workflow_run` row via the `MemoryService` from PLAN-F-015. The `workflow_run.workflow_type` must be set to `"qa"`. The `workflow_run.final_state` JSONB must include the full `QAWorkflowState` snapshot (serialized). The `agent_invocation` row must reference the `qa_analyst` role and record `cost_usd`, `input_tokens`, `output_tokens`, `confidence`, and `tools_called`. This satisfies the AC-005 episodic memory requirement without adding new infrastructure — it reuses the `EpisodicRepository.append_workflow_run` and `append_agent_invocation` methods from PLAN-F-015.

**AC covered**: AC-005

---

## Acceptance Criteria Coverage

| AC | Text (condensed) | Covered by |
|----|-----------------|------------|
| AC-001 | User submits question; qa_analyst agent runs with max_iterations=10; returns answer scoped to portfolio tools | TASK-004, TASK-005, TASK-007 |
| AC-002 | Response includes answer text, cited sources list, confidence score (0–1) | TASK-003, TASK-004, TASK-005, TASK-006 |
| AC-003 | Cost ceiling or timeout reached → partial answer with "Cost limit reached" notice, not an error | TASK-003, TASK-004, TASK-005, TASK-006 |
| AC-004 | Out-of-portfolio question → out-of-scope reply with watchlist suggestion | TASK-002, TASK-004, TASK-007 |
| AC-005 | Each user question and agent response stored in episodic memory Layer 1 workflow_run | TASK-001, TASK-004, TASK-008 |

## Acceptance Notes

AC-003 requires that a cost-ceiling breach never surfaces as an HTTP 5xx error to the frontend. The `QAWorkflow.run_qa_analyst` node must catch `LimitExceededError(LimitType.COST_CEILING)` and `LimitExceededError(LimitType.TIMEOUT)` internally and transition to `build_response` with `cost_limited=True`. Only unexpected exceptions (infrastructure failures) may propagate as errors. This must be explicitly tested in TASK-004 and TASK-005.

The `WorkflowStructureValidator` invariant (`evaluate_quality` second-to-last, `narrative_writer` last) applies to report-generating workflows only. The Q&A workflow is interactive and terminates at `persist_message`. The `QAWorkflow` constructor must pass `skip_tail_invariant=True` when calling the validator, or the validator must accept an `interactive=True` flag. This API extension must be coordinated with PLAN-F-011's `WorkflowStructureValidator` — if PLAN-F-011 is not yet executed, a stub validator that accepts the flag is sufficient for this plan's tests.

## Risks and Notes

- The `qa_analyst` agent's `max_iterations=10` makes it the most expensive single-invocation agent in the system. At Opus 4.7 pricing, 10 iterations could approach the `cost_ceiling_usd`. The YAML ceiling must be set at 0.40 USD (TASK-007) which is intentionally lower than the session-level user budget. Monitor Langfuse cost traces after first production use.
- SSE streaming from FastAPI requires that the Celery worker running `QAWorkflow` communicate results back to the API process. For MVP, run the workflow inline within the FastAPI async context (not as a Celery task) to simplify streaming. This means Q&A sessions occupy an API worker thread for up to `timeout_seconds`. Document this as a known scaling concern: if concurrent Q&A sessions grow, extract to a Celery task with a Redis pub/sub streaming bridge.
- The `QAScopeGuard` uses regex ticker extraction, which may miss paraphrased company names ("the iPhone maker" → AAPL). This is an acceptable MVP limitation. The agent's tool scoping provides a second enforcement layer: even if the scope guard passes a question through, tools only return data for companies in the user's portfolio. False negatives in the guard do not create a security breach.
- The `QAMessage` table is separate from the main `workflow_run`/`agent_invocation` tables to allow direct session-message queries without joining through the agentic tables. Both the `QAMessage` row and the `agent_invocation` row are written for every assistant turn — the former is the user-facing record, the latter is the observability record. Ensure both writes succeed in the same database transaction to avoid partial state.
- Dependency on PLAN-F-011 (`qa-analyst.yaml` with `max_iterations=10`) and PLAN-F-012 (Tool Library with portfolio-scoped tools) must be fully executed before this plan's TASK-004 can be integration-tested end-to-end. Unit tests mock both dependencies.
