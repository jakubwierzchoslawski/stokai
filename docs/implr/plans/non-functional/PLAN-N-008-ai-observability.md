---
plan_id: PLAN-N-008
slug: ai-observability
title: AI Observability via Langfuse
linked_requirement: REQ-N-008
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-015, reason: "AI reasoning steps stored to DB as part of episodic memory; agent_invocation and tool_call tables created by that plan are written alongside Langfuse spans" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-03T00:00:00Z
---

# PLAN-N-008 — AI Observability via Langfuse

## Linked Requirement
**REQ-N-008** — AI Observability via Langfuse
Status: approved | Jira:

## Objective

Instrument every Mode A and Mode B workflow run with a complete, hierarchical Langfuse trace that captures a root workflow span plus child spans for every agent invocation and tool call. Deliver a `LangfuseTracer` wrapper in `src/ai/observability/` that (1) opens one trace per workflow run, (2) opens and closes child spans automatically for each agent invocation and tool call, (3) attaches the full standard metadata set — `workflow_id`, `workflow_type`, `tenant_id`, `user_id`, `agent_role_id`, `prompt_version` (git SHA), `model_used`, `confidence`, `cost_usd`, `tokens_in`, `tokens_out`, `latency_ms`, `tools_called`, `state_snapshot_ref` — on every span, and (4) stores the `langfuse_trace_id` on the `workflow_run` row in PostgreSQL so that every Langfuse trace is cross-linked to episodic memory. The Langfuse self-hosted stack (langfuse-server, langfuse-db, clickhouse) is added to `docker-compose.yml`, consistent with the service topology defined in Architecture §15. Integration tests assert trace existence via the Langfuse API and DB row completeness via PostgreSQL after a synthetic workflow run.

## Architecture Context

This plan touches Architecture §12.4 (Observability), §7.1 (LangGraph Runtime — Langfuse spans), §8 (Prompt Management — prompt SHA as version label), §13 (Technology Decisions — Langfuse self-hosted), and §15 (Deployment Topology — langfuse-server, langfuse-db, clickhouse services).

The `LangfuseTracer` wrapper lives in the `ai` backend module at `src/ai/observability/`. It is the sole point in the system that calls the Python Langfuse SDK; no other module imports that SDK directly (Dependency Inversion). The wrapper is injected into the LangGraph workflow execution layer via constructor injection.

The `workflow_run.langfuse_trace_id` column (Architecture §10, Agentic Layer Tables) provides the cross-system audit link: from a PostgreSQL episodic row to the full Langfuse trace tree. PLAN-F-015 creates the `workflow_run`, `agent_invocation`, and `tool_call` tables. This plan writes `langfuse_trace_id` to `workflow_run` and coordinates the dual-write: Langfuse span open/close + PostgreSQL `agent_invocation` row are both issued within the same agent execution boundary.

Docker Compose additions extend the file delivered by PLAN-N-007 (Portability and Self-Hostability), which already provisions the `api`, `worker`, `beat`, `postgres`, and `redis` services.

## Component Design

### New Components

```
src/ai/observability/
  __init__.py
  tracer.py              — LangfuseTracer: trace + span lifecycle manager
  span_metadata.py       — SpanMetadata dataclass; standard field set
  context.py             — WorkflowTracingContext: holds active trace_id + span_id
                           for propagation through async workflow nodes
  exceptions.py          — TracerError, SpanNotOpenError

tests/unit/ai/observability/
  test_tracer.py         — unit tests for LangfuseTracer (mock SDK)
  test_span_metadata.py  — field validation, serialization

tests/integration/
  test_langfuse_integration.py  — end-to-end: synthetic workflow → Langfuse API query
                                   + PostgreSQL DB assertions
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `docker-compose.yml` | Add `langfuse-server`, `langfuse-db`, `clickhouse` services; inject `LANGFUSE_*` env vars into `api` and `worker` | Self-hosted Langfuse topology per Architecture §15 |
| `docker-compose.override.yml` | Expose langfuse-server port 3000 locally; set `LANGFUSE_DEBUG=true` | Local development convenience |
| `.env.example` | Add `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST`, `LANGFUSE_DB_URL`, `CLICKHOUSE_URL` | 12-factor env var documentation |
| `src/config/settings.py` | Add `langfuse_secret_key`, `langfuse_public_key`, `langfuse_host` fields with `required=True`; fail-fast on missing | Secrets management per D3 |
| `src/ai/workflows/base_workflow.py` | Inject `LangfuseTracer`; call `open_trace()` at workflow start, `close_trace()` at end; persist `langfuse_trace_id` on `workflow_run` via repository | Trace lifecycle per workflow run |
| `src/ai/workflows/node_executor.py` | Wrap each `AgentNode` execution: `open_agent_span()` before invoke, `close_agent_span()` with output metadata after | Agent invocation spans |

### Interfaces and Contracts

```python
# src/ai/observability/span_metadata.py
@dataclass(frozen=True)
class SpanMetadata:
    workflow_id: UUID
    workflow_type: str
    tenant_id: UUID
    user_id: UUID
    agent_role_id: str | None        # None for root trace span
    prompt_version: str | None       # git SHA; None when no prompt involved
    model_used: str | None
    confidence: float | None
    cost_usd: float | None
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int | None
    tools_called: list[str] | None
    state_snapshot_ref: str | None   # opaque reference to checkpoint

# src/ai/observability/tracer.py
class ILangfuseTracer(Protocol):
    def open_trace(self, metadata: SpanMetadata) -> str:
        """Returns trace_id."""

    def open_agent_span(
        self,
        trace_id: str,
        parent_span_id: str | None,
        metadata: SpanMetadata,
    ) -> str:
        """Returns span_id."""

    def close_agent_span(
        self,
        span_id: str,
        output_metadata: SpanMetadata,
    ) -> None: ...

    def open_tool_span(
        self,
        trace_id: str,
        parent_span_id: str,
        tool_name: str,
        args_hash: str,
        cached: bool,
    ) -> str:
        """Returns span_id."""

    def close_tool_span(
        self,
        span_id: str,
        result_rows: int,
        latency_ms: int,
        error_type: str | None,
    ) -> None: ...

    def close_trace(self, trace_id: str, cost_usd: float) -> None: ...
```

## Implementation Tasks

### TASK-001: Docker Compose — Langfuse self-hosted services · S/no-TDD · docker-compose.yml, docker-compose.override.yml, .env.example

Add the three Langfuse infrastructure services to `docker-compose.yml`: `langfuse-db` (postgres:16 with a dedicated volume), `clickhouse` (clickhouse/clickhouse-server:23), and `langfuse-server` (ghcr.io/langfuse/langfuse:latest, depends_on both). The `langfuse-server` service receives `LANGFUSE_DATABASE_URL` (pointing to `langfuse-db`) and `CLICKHOUSE_URL` (pointing to `clickhouse`) as environment variables resolved from the root `.env` file. Add `NEXTAUTH_SECRET`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_PUBLIC_KEY` to `langfuse-server`'s env block. The `api` and `worker` services gain `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_HOST=http://langfuse-server:3000` in their env blocks. `docker-compose.override.yml` maps port 3000 on the host. All five new env var names are added to `.env.example` with placeholder values and comments.

No named network changes required: all services already share the default compose network.

**AC covered**: AC-004

---

### TASK-002: LangfuseTracer wrapper — trace and span lifecycle · M/TDD · src/ai/observability/tracer.py, src/ai/observability/span_metadata.py, src/ai/observability/context.py, src/ai/observability/exceptions.py, src/ai/observability/__init__.py, tests/unit/ai/observability/test_tracer.py

**Tests to write first (TDD)**:
- `test_open_trace_returns_trace_id` — mock SDK `langfuse.trace()` call; assert returned ID is a non-empty string.
- `test_open_agent_span_uses_parent_span_id` — assert the SDK `trace.span(parent_observation_id=...)` receives the parent span ID.
- `test_close_agent_span_flushes_metadata` — assert `span.update(metadata=...)` is called with all required SpanMetadata fields.
- `test_open_tool_span_sets_tool_name` — assert tool_name is passed as the span `name` field.
- `test_close_trace_flushes_cost` — assert `trace.update(metadata={"cost_usd": ...})` and `client.flush()` are both called.
- `test_span_not_open_error` — calling `close_agent_span` without prior `open_agent_span` raises `SpanNotOpenError`.

Implement `LangfuseTracer` as the concrete implementation of `ILangfuseTracer`. It holds a `langfuse.Langfuse` client instance (injected or constructed from `Settings`). `WorkflowTracingContext` is an `asyncio`-safe context var holder (using `contextvars.ContextVar`) that propagates the active `(trace_id, span_id)` tuple through async node chains without explicit parameter passing.

`SpanMetadata` is a frozen dataclass with all 13 standard fields. `None` is permitted on all optional fields; the serializer skips `None`-valued fields when calling the SDK to avoid polluting the Langfuse UI.

**AC covered**: AC-001, AC-002

---

### TASK-003: Agent node instrumentation — standard metadata on every agent span · M/TDD · src/ai/workflows/node_executor.py, src/ai/workflows/base_workflow.py, tests/unit/ai/workflows/test_node_executor.py

**Tests to write first (TDD)**:
- `test_agent_node_opens_span_before_invoke` — mock tracer; assert `open_agent_span` is called before the agent's `invoke()` method.
- `test_agent_node_closes_span_after_invoke` — assert `close_agent_span` is called with output metadata including `tokens_in`, `tokens_out`, `cost_usd`, `confidence`, and `latency_ms`.
- `test_agent_node_records_model_used` — assert `model_used` in the closed span matches the agent YAML config's `model` field.
- `test_agent_node_span_closed_on_exception` — even when `invoke()` raises, `close_agent_span` is still called (use `try/finally`).
- `test_base_workflow_stores_trace_id_on_run` — assert `workflow_run.langfuse_trace_id` is set to the value returned by `open_trace`.

`node_executor.py` wraps every `AgentNode.execute(state)` call in an `open_agent_span` / `close_agent_span` bracket. It reads `agent_role_id`, `model_used`, and YAML limits from the agent config already loaded by the Agent Registry (PLAN-F-011). Output metadata fields (`tokens_in`, `tokens_out`, `cost_usd`, `confidence`) are extracted from the agent output object, which must implement the `AgentOutput` protocol (defined in PLAN-F-011).

`base_workflow.py` calls `tracer.open_trace(metadata)` at workflow entry and stores the returned `trace_id` on the `WorkflowState`. At workflow exit it calls `tracer.close_trace(trace_id, cost_usd=state.cost_usd)` and persists `langfuse_trace_id = trace_id` to `workflow_run` via the episodic repository (from PLAN-F-015).

**AC covered**: AC-001, AC-002

---

### TASK-004: Prompt SHA version recording on agent spans · S/no-TDD · src/ai/observability/prompt_version.py, src/ai/workflows/node_executor.py

Add a `PromptVersionResolver` utility in `src/ai/observability/prompt_version.py` with one method:

```python
def resolve(self, prompt_path: str) -> str:
    """Return the git blob SHA for the given prompt file path.
    Falls back to 'unknown' if not in a git repo or path is absent."""
```

It shells out to `git rev-parse HEAD:prompts/...` (path relative to project root). The result is cached in a module-level dict on first call per path to avoid repeated subprocess calls in a high-throughput run.

`node_executor.py` calls `PromptVersionResolver.resolve(agent_config.prompt_path)` and includes the SHA as `prompt_version` in the `SpanMetadata` passed to `open_agent_span`. The same SHA is also passed to the episodic `agent_invocation` row (PLAN-F-015 field `prompt_version`).

**AC covered**: AC-002 (prompt_version field)

---

### TASK-005: PostgreSQL dual-write — agent_invocation row synced to Langfuse span · M/TDD · src/ai/workflows/node_executor.py, tests/unit/ai/workflows/test_node_executor_db_write.py

**Tests to write first (TDD)**:
- `test_agent_invocation_row_written_after_span_close` — mock episodic repository; assert `EpisodicRepository.append_agent_invocation(...)` is called once per agent node execution, with `workflow_run_id`, `agent_role`, `prompt_version`, and `cost_usd` matching the span metadata.
- `test_tool_call_row_written_after_tool_span_close` — assert `EpisodicRepository.append_tool_call(...)` is called with matching `invocation_id` and `tool_name`.
- `test_db_write_failure_does_not_suppress_span` — if `append_agent_invocation` raises, the exception is logged at ERROR level but the Langfuse span still closes; the workflow is not aborted (observability writes are best-effort, episodic writes are mandatory — raise for episodic, not for Langfuse).
- `test_agent_invocation_cost_matches_span_cost` — cost_usd on the DB row equals the cost passed to `close_agent_span`.

The dual-write is coordinated inside `node_executor.py`: after `close_agent_span` returns, `EpisodicRepository.append_agent_invocation` is awaited. Both writes happen in the same method scope. The episodic write is the authoritative one: if it fails, the exception propagates and the workflow fails (episodic completeness is an invariant per PLAN-F-015 NFR constraints). The Langfuse span close is wrapped in `try/except` with error logging so a Langfuse outage does not abort the workflow.

**AC covered**: AC-003

---

### TASK-006: Integration tests — trace completeness and DB row assertions · M/TDD · tests/integration/test_langfuse_integration.py

**Tests to write first (TDD)**:
- `test_workflow_run_produces_langfuse_trace` — run a synthetic `MinimalWorkflow` (two nodes: one DeterministicNode + one AgentNode stub) against the live Langfuse container; query the Langfuse public API `/api/public/traces/{trace_id}`; assert HTTP 200 and `trace.observations` count ≥ 2 (root + one agent span).
- `test_agent_span_contains_required_fields` — from the same trace, assert the agent observation contains non-null values for `agent_role_id`, `model_used`, `prompt_version`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`, `confidence`.
- `test_agent_invocation_row_in_postgres` — query `agent_invocation` WHERE `workflow_run_id = <run_id>`; assert the row exists and `prompt_version` equals the SHA recorded in the Langfuse span.
- `test_langfuse_accessible_without_external_network` — assert that the Langfuse `GET /api/public/health` endpoint returns 200 using only the `LANGFUSE_HOST` env var (no external hostname); this test runs in Docker network context.

The `MinimalWorkflow` fixture is defined in the test module. The `AgentNode` stub returns a deterministic `AgentOutput` with known cost, tokens, and confidence values so that assertions are exact rather than presence-only.

Tests are marked `pytest.mark.integration` and require a running Docker Compose stack (detected via `LANGFUSE_HOST` env var presence). The CI job runs them in a `docker compose --profile integration up -d` step before pytest.

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

## Acceptance Criteria Coverage

- AC-001: Given any Mode A or Mode B workflow run, a Langfuse trace exists with a root span for the workflow and child spans for each agent invocation and tool call, all linked by the same workflow_id. → TASK-002, TASK-003, TASK-006
- AC-002: Given any agent invocation span in Langfuse, it records: agent_role, model_id, prompt_version (git SHA), input_tokens, output_tokens, cost_usd, latency_ms, and confidence. → TASK-002, TASK-003, TASK-004, TASK-006
- AC-003: Given any agent invocation, a corresponding agent_invocation row is present in PostgreSQL with matching workflow_run_id, agent_role, prompt_version, and cost_usd. → TASK-005, TASK-006
- AC-004: Given the Langfuse self-hosted service is started via Docker Compose, it is accessible on its configured port and accepts trace writes from the application without any external SaaS dependency. → TASK-001, TASK-006

## Acceptance Notes

Integration tests (TASK-006) require a Docker Compose stack with `langfuse-server`, `langfuse-db`, and `clickhouse` running. CI must execute `docker compose up -d` (with the Langfuse services) and wait for the health endpoint before running `pytest -m integration`. Test authors must document the warm-up wait in the CI job definition.

## Risks and Notes

- The Langfuse Python SDK operates with an internal background flush queue. Calling `client.flush()` explicitly after each trace close is required in test contexts to guarantee the trace is queryable via the API before the assertion runs. Production workflows need not flush synchronously.
- Langfuse server first-boot requires database migration; the langfuse-db container must be fully healthy before langfuse-server starts. Use `depends_on: condition: service_healthy` with a `pg_isready` healthcheck on langfuse-db.
- The `clickhouse` service must be confirmed to start cleanly on the target host OS (arm64 support is image-version-dependent). Pin to a specific ClickHouse image tag rather than `latest` to avoid regressions.
- The episodic write in TASK-005 is the authoritative path (PLAN-F-015 invariant). If a developer is tempted to skip the DB write and rely solely on Langfuse for audit, this plan explicitly prohibits that: the two writes are complementary, not alternatives.
- `PromptVersionResolver` (TASK-004) falls back to `'unknown'` in environments without a git repo (e.g., Docker container built without `.git`). In production this means deploying with the git SHA baked into an env var `PROMPT_SHA_FALLBACK` that the resolver reads when the subprocess fails.
