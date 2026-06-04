---
plan_id: PLAN-N-001
slug: mode-a-latency
title: Mode A Pipeline Latency Enforcement
linked_requirement: REQ-N-001
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-001, reason: "The pipeline being measured — PipelineExecutor and all 12 steps must exist before latency guards and timing instrumentation can be layered on" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-001 — Mode A Pipeline Latency Enforcement

## Linked Requirement
**REQ-N-001** — Mode A Pipeline Latency
Status: approved | Jira:

## Objective
Instrument the 12-step Mode A Reactive Pipeline with per-step timeout guards, a whole-pipeline wall-clock timer, and Langfuse latency spans so that SLA violations are detected immediately rather than discovered retrospectively. Provide an automated pytest latency test suite that fires synthetic events at varied intensities and asserts p95 end-to-end latency ≤ 90 s, p95 tweet-to-alert ≤ 30 s, p95 score-change alert ≤ 5 min, and p95 SEC-filing alert ≤ 20 min. Configure a Langfuse score alert that fires when the production p95 crosses 80 s (10-second headroom before the SLA).

## Architecture Context
Mode A is defined in Architecture §6. Each of the 12 deterministic and LLM steps has an explicit latency budget (< 1 s–8 s per step; total ≤ 60 s processing plus 30-second SLA margin). The pipeline executor lives in the `events` module (`src/event_pipeline/`). Observability is handled by Langfuse (§12.4): every event produces one root trace; each step should be a child span carrying `latency_ms`. Timeout guards wrap each step call; a `StepTimeoutError` cancels the current step and records the failure in the Langfuse span before re-raising, keeping pipeline failures visible.

This plan adds three new artefacts to the `events` module:
- `src/event_pipeline/latency.py` — `StepLatencyGuard` context-manager / decorator and per-step budget registry.
- `src/event_pipeline/langfuse_spans.py` — thin wrapper that opens/closes Langfuse child spans and records `latency_ms`, `step_name`, and `budget_ms` on each step.
- `tests/performance/test_mode_a_latency.py` — pytest latency test suite with synthetic event fixtures.

The pipeline executor (`src/event_pipeline/pipeline_executor.py`) is extended to call the guard and the span wrapper around every step, and to record end-to-end wall-clock time on the root trace.

## Component Design

### New Components

```
src/event_pipeline/
  latency.py
    StepBudget          — dataclass: step_name, budget_ms, is_llm
    STEP_BUDGETS        — dict[str, StepBudget] (all 12 steps, authoritative from §6)
    StepTimeoutError    — subclass of PipelineError
    StepLatencyGuard    — async context manager; records actual_ms, raises on breach

src/event_pipeline/
  langfuse_spans.py
    LangfuseSpanContext — async context manager wrapping langfuse.span(); captures
                          step_name, budget_ms, actual_ms, breach bool as span metadata

tests/performance/
  conftest.py           — synthetic event factories (intensity 1–5, TIER1-tweet,
                          score-change, SEC-filing variants); fake pipeline executor
                          that injects configurable sleep per step
  test_mode_a_latency.py — latency assertion suite (see TASK-004)

src/config/
  langfuse_alerts.py    — register_latency_alerts() — calls Langfuse API to upsert
                          the p95 > 80 s score monitor; idempotent, run at startup
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/event_pipeline/pipeline_executor.py` | Wrap each step call with `StepLatencyGuard` and `LangfuseSpanContext`; record end-to-end wall time on root trace as `pipeline_latency_ms` | Central execution loop must own timing |
| `src/event_pipeline/exceptions.py` | Add `StepTimeoutError(step_name, budget_ms, actual_ms)` | Typed failure for SLA violation |

### Interfaces and Contracts

```python
# src/event_pipeline/latency.py

from dataclasses import dataclass

@dataclass(frozen=True)
class StepBudget:
    step_name: str
    budget_ms: int
    is_llm: bool

STEP_BUDGETS: dict[str, StepBudget] = {
    "persist_raw_event":      StepBudget("persist_raw_event",      1_000,  False),
    "classify_event":         StepBudget("classify_event",         5_000,  True),
    "extract_tickers":        StepBudget("extract_tickers",        3_000,  True),
    "compute_exposure_map":   StepBudget("compute_exposure_map",   3_000,  False),
    "persist_event_record":   StepBudget("persist_event_record",   1_000,  False),
    "embed_event":            StepBudget("embed_event",            2_000,  True),
    "find_historical_analogies": StepBudget("find_historical_analogies", 3_000, False),
    "generate_alert_text":    StepBudget("generate_alert_text",    8_000,  True),
    "evaluate_alert_rules":   StepBudget("evaluate_alert_rules",   1_000,  False),
    "dispatch_or_log_silent": StepBudget("dispatch_or_log_silent", 2_000,  False),
    "enqueue_deep_dive":      StepBudget("enqueue_deep_dive",      1_000,  False),
    "return_pipeline_result": StepBudget("return_pipeline_result", 1_000,  False),
}

class StepTimeoutError(PipelineError):
    def __init__(self, step_name: str, budget_ms: int, actual_ms: float) -> None: ...

class StepLatencyGuard:
    """Async context manager. Raises StepTimeoutError if step exceeds budget_ms."""
    def __init__(self, budget: StepBudget) -> None: ...
    async def __aenter__(self) -> "StepLatencyGuard": ...
    async def __aexit__(self, *exc: object) -> bool: ...
    @property
    def actual_ms(self) -> float: ...  # available after __aexit__
```

```python
# src/event_pipeline/langfuse_spans.py

class LangfuseSpanContext:
    """Async context manager that wraps a Langfuse child span for one pipeline step."""
    def __init__(
        self,
        parent_trace_id: str,
        budget: StepBudget,
        langfuse_client: "Langfuse",
    ) -> None: ...
    async def __aenter__(self) -> "LangfuseSpanContext": ...
    async def __aexit__(self, *exc: object) -> bool: ...
    # On exit writes: latency_ms, budget_ms, step_name, sla_breach (bool) to span metadata
```

```python
# pipeline_executor.py — changed call pattern (pseudocode)

async def _run_step(
    self,
    step_name: str,
    coro: Coroutine[Any, Any, T],
    *,
    trace_id: str,
) -> T:
    budget = STEP_BUDGETS[step_name]
    async with LangfuseSpanContext(trace_id, budget, self._langfuse):
        async with StepLatencyGuard(budget):
            return await coro
```

## Implementation Tasks

### TASK-001: Step budget registry and StepLatencyGuard · S/no-TDD · src/event_pipeline/latency.py, src/event_pipeline/exceptions.py

Create `src/event_pipeline/latency.py` with the `StepBudget` dataclass, the `STEP_BUDGETS` dict (all 12 steps, values from Architecture §6), and the `StepLatencyGuard` async context manager. `StepLatencyGuard` uses `asyncio.wait_for` (or a manual `time.perf_counter` check on `__aexit__`) to enforce `budget_ms`. On breach it raises `StepTimeoutError`.

Add `StepTimeoutError` to `src/event_pipeline/exceptions.py`.

**AC covered**: enables AC-001, AC-002 (per-step enforcement is prerequisite for end-to-end guarantee)

---

### TASK-002: Integrate StepLatencyGuard into PipelineExecutor · M/TDD · src/event_pipeline/pipeline_executor.py, src/event_pipeline/latency.py

Modify `PipelineExecutor._run_step` to wrap every step coroutine with `StepLatencyGuard`. Each step call already exists from PLAN-F-001; this task adds the guard without altering step logic.

Behaviour on `StepTimeoutError`:
- Log the breach at ERROR level with `step_name`, `budget_ms`, `actual_ms`.
- Re-raise; the pipeline marks the event as `failed` and writes an episodic-memory failure entry (existing failure path from PLAN-F-001).

**Tests to write first (TDD)**:
- Given a step coroutine that sleeps 10 ms under a 50 ms budget, `StepLatencyGuard` completes without raising.
- Given a step coroutine that sleeps 200 ms under a 50 ms budget, `StepLatencyGuard` raises `StepTimeoutError` with `step_name` and both ms values populated.
- Given the `classify_event` step is injected with a 6 000 ms sleep (over the 5 000 ms budget), `PipelineExecutor.run` propagates `StepTimeoutError` with `step_name="classify_event"`.
- Given all 12 steps complete within budget, `PipelineExecutor.run` returns successfully without raising.

**AC covered**: AC-001 (enforce ≤90s by enforcing per-step budgets that sum to ≤60s), AC-002 (tweet path traverses the same executor, classify+extract+embed+alert budgets sum to 18s well within 30s TIER1 target)

---

### TASK-003: End-to-end pipeline timer and Langfuse span integration · M/TDD · src/event_pipeline/pipeline_executor.py, src/event_pipeline/langfuse_spans.py

Add `LangfuseSpanContext` to `src/event_pipeline/langfuse_spans.py`. Extend `PipelineExecutor`:
1. Record `pipeline_start_ns = time.perf_counter_ns()` before step 1.
2. Wrap each step call in `LangfuseSpanContext(trace_id, budget, langfuse_client)` in addition to `StepLatencyGuard`.
3. After step 12 (or on failure), compute `pipeline_latency_ms` and write it to the root Langfuse trace as a numeric score named `"pipeline_latency_ms"`.
4. If `pipeline_latency_ms > 80_000` (80 s), also write a boolean score `"sla_warning": 1` on the trace for Langfuse alert filtering.

`LangfuseSpanContext` records on each span: `latency_ms` (actual), `budget_ms`, `step_name`, `sla_breach` (bool). When the span's `__aexit__` receives a `StepTimeoutError`, it marks the span with `"status": "error"` before propagating.

**Tests to write first (TDD)**:
- `LangfuseSpanContext.__aexit__` with a happy-path coroutine writes `latency_ms > 0` and `sla_breach=False` to the mock Langfuse span.
- `LangfuseSpanContext.__aexit__` with a coroutine that raises `StepTimeoutError` marks the span `"status": "error"` and sets `sla_breach=True`.
- `PipelineExecutor.run` on a 12-step all-fast fake pipeline writes `pipeline_latency_ms` score to the root trace.
- `PipelineExecutor.run` on a fake pipeline where total time exceeds 80 s writes `sla_warning=1` to the root trace.

**AC covered**: AC-001 (Langfuse captures end-to-end ms; operator can verify p95 ≤ 90 s from Langfuse dashboard), AC-003 (score-change path flows through same executor timer), AC-004 (SEC filing path flows through same executor timer)

---

### TASK-004: Automated pytest latency test suite · M/TDD · tests/performance/test_mode_a_latency.py, tests/performance/conftest.py

Create `tests/performance/conftest.py` with:
- `synthetic_event_factory(intensity, source)` — builds a `GeoEvent`-like dict for sources `gdelt`, `twitter_tier1`, `edgar`, `price_anomaly`.
- `FakePipelineExecutor(step_delays_ms)` — runs all 12 steps with injected sleep values; uses real `StepLatencyGuard` and the same wall-clock timer as `PipelineExecutor`. Reports `pipeline_latency_ms`.

Create `tests/performance/test_mode_a_latency.py`:

**Tests to write first (TDD)**:
- **AC-001**: Run 100 intensity-4 events through `FakePipelineExecutor` where each step sleeps at 80% of its budget. Assert `statistics.quantiles(latencies, n=20)[18]` (p95) ≤ 90 000 ms.
- **AC-001 breach detection**: Run 100 intensity-4 events where `classify_event` sleeps 5 100 ms (just over budget). Assert all runs raise `StepTimeoutError` on that step.
- **AC-002**: Run 100 TIER1-tweet events through `FakePipelineExecutor` where all steps sleep at 50% of budget. Assert p95 total latency ≤ 30 000 ms. (TIER1 tweets hit the same pipeline; the 30 s window is achievable because per-step budgets sum to ≤ 18 s LLM + ≤ 10 s deterministic = ≤ 28 s at nominal load.)
- **AC-003**: Run 100 score-change events (intensity 3, source `price_anomaly`) through `FakePipelineExecutor` at nominal step latencies. Assert p95 ≤ 300 000 ms (5 min).
- **AC-004**: Run 100 SEC-filing events through `FakePipelineExecutor` at nominal step latencies. Assert p95 ≤ 1 200 000 ms (20 min).
- **Budget registry completeness**: Assert `len(STEP_BUDGETS) == 12` and all step names match the canonical list from Architecture §6.
- **Budget sum sanity**: Assert `sum(b.budget_ms for b in STEP_BUDGETS.values()) <= 27_000` (sum of all per-step budgets ≤ 27 s, well within 60 s processing budget).

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-005: Langfuse p95 latency alert configuration · S/no-TDD · src/config/langfuse_alerts.py

Create `src/config/langfuse_alerts.py` with `register_latency_alerts(langfuse_client)`. This function calls the Langfuse Python SDK to upsert a numeric score monitor:
- Score name: `"pipeline_latency_ms"`
- Condition: p95 over a rolling 1-hour window exceeds `80_000` ms.
- Notification channel: operator email (read from `LANGFUSE_ALERT_EMAIL` env var; optional — skipped if not set).

The function is idempotent (safe to call at every application startup). It is invoked from the application startup hook alongside other Langfuse initialisation.

**AC covered**: AC-001 (production monitoring closes the loop — automated alert at p95 > 80 s gives 10 s headroom before SLA breach at 90 s)

---

## Acceptance Criteria Coverage

- AC-001: End-to-end p95 ≤ 90 s for intensity-4/5 events → TASK-001, TASK-002, TASK-003, TASK-004, TASK-005
- AC-002: TIER1 tweet p95 ≤ 30 s → TASK-002, TASK-004
- AC-003: Score-change alert p95 ≤ 5 min → TASK-003, TASK-004
- AC-004: SEC filing alert p95 ≤ 20 min → TASK-003, TASK-004

## Acceptance Notes

The pytest latency suite (TASK-004) uses `FakePipelineExecutor` with injected step delays and real `StepLatencyGuard` logic. It does not call any LLM API. The AC-002 TIER1-tweet assertion relies on the fact that the same 12-step executor is used regardless of source (per Architecture §6 — the pipeline is uniform); the 30 s target is achievable because per-step budgets sum to ≤ 28 s at nominal operation.

AC-003 and AC-004 latency targets (5 min and 20 min) encompass the full path from source ingestion to alert dispatch, not just pipeline execution time. The pipeline itself must complete in ≤ 60 s; any remaining budget is consumed by ingestion polling intervals (GDELT 15-min poll for score-change events, EDGAR feed latency for SEC filings). The test asserts the pipeline-execution portion stays within the allocated share of the budget.

Production p95 verification (AC-001 at scale) must be confirmed from the Langfuse dashboard after the first 100 production events have been processed.

## Risks and Notes

- `asyncio.wait_for` imposes a hard cancellation on an in-flight LLM coroutine. If the Anthropic or OpenAI client does not honour cancellation cleanly, the underlying HTTP connection may leak. Use an `httpx.AsyncClient` with an explicit `timeout` parameter equal to `budget_ms / 1000` as a belt-and-suspenders measure alongside `wait_for`.
- The Langfuse Python SDK `span()` call is synchronous in some versions. Wrap it in `asyncio.to_thread` if the SDK does not provide an async context manager by the time this task is executed.
- The p95 computation in TASK-004 uses Python's `statistics.quantiles` which requires ≥ 2 samples; the test fixture must always produce exactly 100 samples to avoid flakiness.
- PLAN-F-001 must be `done` (or at minimum the `PipelineExecutor._run_step` interface must be finalised) before TASK-002 can be implemented. This plan treats PLAN-F-001 as a hard dependency.
