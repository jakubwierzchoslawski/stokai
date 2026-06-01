---
plan_id: PLAN-N-001
slug: n-mode-a-latency
title: NFR — Mode A Reactive Pipeline Latency
linked_requirement: REQ-N-001
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-001, reason: "Pipeline implementation and EventRecord/AlertRecord models required for latency testing" }
executed_at: 2026-06-01T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-05-31T00:00:00Z
updated_at: 2026-05-31T00:00:00Z
---

# PLAN-N-001 — NFR — Mode A Reactive Pipeline Latency

## Linked Requirement
**REQ-N-001** — NFR — Mode A Reactive Pipeline Latency
Status: approved | Jira: (blank)

## Objective

This plan measures and enforces the end-to-end latency guarantees for the Mode A Reactive
Pipeline defined in PLAN-F-001. No new pipeline logic is introduced. Instead, a
`tests/performance/` test suite is built that injects synthetic test events directly into
the production `PipelineExecutor`, reads the `detected_at` and `generated_at` timestamps
from the resulting `EventRecord`, reads `dispatched_at` from the resulting `AlertRecord`,
and asserts that the p95 of the elapsed durations stays within the per-source SLAs:
tweet/X-class < 30 seconds, GDELT geo-events < 90 seconds, SEC EDGAR filings < 20 minutes.
A complementary timestamp-presence assertion verifies that `detected_at`, `generated_at`,
and `dispatched_at` are never null on any completed pipeline run. All performance tests are
tagged `@pytest.mark.performance`, run in a dedicated CI stage that blocks merge on SLA
breach, and are isolated from the default test suite.

## Architecture Context

This plan touches:

- **`tests/performance/`** — new test module (ARCHITECTURE.md §4 folder structure under
  `tests/`). No changes to `src/`.
- **`src/event_pipeline/pipeline_executor.py`** (read-only) — the production executor whose
  timestamps are measured.
- **`src/db/models/event_record.py`** and **`src/db/models/alert_record.py`** (read-only)
  — the ORM models that carry `detected_at`, `generated_at`, and `dispatched_at`; both
  produced by PLAN-F-001.
- **`src/event_pipeline/pipeline_state.py`** (read-only) — `PipelineState` carries
  `detected_at` and `generated_at` through all 13 steps; `TraceStep` (Step 13) sets
  `generated_at`.
- **`pyproject.toml` / `pytest.ini`** — registers the `performance` mark and the CI gate
  configuration.

Architecture sections directly relevant:

- §6 Mode A Reactive Pipeline — latency budget per source tier (the target numbers this plan
  enforces).
- §14 NFR Summary — latency row: tweet < 30 s, geo < 90 s, SEC < 20 min.
- §12 Observability — `detected_at` and `generated_at` are already written to Langfuse
  traces by TraceStep; this plan cross-checks the same values via the DB models.

SOLID design is enforced in the test infrastructure:

- **SRP**: `LatencyCollector` measures a single pipeline run and returns elapsed seconds;
  `PerformanceReporter` aggregates a list of durations and computes percentiles;
  `EventInjector` (abstract base class) creates typed test events per source.
- **OCP**: adding a new source type (e.g. `PRICE_ANOMALY`) requires only a new
  `EventInjector` subclass — zero changes to `LatencyCollector` or `PerformanceReporter`.
- **DIP**: `LatencyCollector` depends on the `EventInjector` Protocol abstraction, not on
  concrete adapters.

## Applied NFR Constraints

This plan IS the NFR. It does not consume a separate NFR constraint table. For reference,
the latency targets this plan enforces come directly from ARCHITECTURE.md §6 and §14:

| Source tier | SLA (p95 detected_at → dispatched_at) |
|-------------|---------------------------------------|
| Tweet / X   | < 30 seconds                          |
| GDELT geo   | < 90 seconds                          |
| SEC EDGAR   | < 20 minutes (1 200 seconds)          |

Budget constraint C-001 is satisfied by the existing pipeline design (Haiku 4.5 for
classification at ~$0.01/classify). This plan does not introduce additional LLM calls.

## Component Design

### New Components

```
tests/performance/
  ├── conftest.py                   — pytest fixtures: test DB session, isolated Redis,
  │                                   PipelineExecutor instance with mocked LLM providers
  ├── collectors/
  │   ├── __init__.py
  │   ├── latency_collector.py      — LatencyCollector: runs one pipeline invocation,
  │   │                               reads EventRecord.detected_at and AlertRecord.dispatched_at,
  │   │                               returns elapsed float seconds
  │   └── performance_reporter.py  — PerformanceReporter: accepts list[float], computes
  │                                   p50/p95/p99/max; returns LatencyReport dataclass
  ├── injectors/
  │   ├── __init__.py
  │   ├── base.py                   — EventInjector Protocol: source_type property,
  │   │                               build_payload(index: int) -> RawEventPayload
  │   ├── tweet_injector.py         — TweetEventInjector: builds X_FILTERED_STREAM payloads;
  │   │                               payload size calibrated to realistic tweet content
  │   ├── gdelt_injector.py         — GdeltEventInjector: builds GDELT geo-event payloads
  │   │                               with lat/lon and category fields
  │   └── edgar_injector.py         — EdgarEventInjector: builds SEC_EDGAR filing payloads
  │                                   with filing_timestamp set to now()
  └── test_mode_a_latency.py        — performance test suite (all @pytest.mark.performance):
                                       test_tweet_p95_under_30s
                                       test_gdelt_p95_under_90s
                                       test_edgar_p95_under_20_minutes
                                       test_event_record_timestamps_non_null
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `pyproject.toml` | Add `[tool.pytest.ini_options]` markers entry for `performance: "Mode A latency SLA assertions"` | Prevents pytest warning on unregistered mark |
| `.github/workflows/ci.yml` (or equivalent CI config) | Add a blocking `performance-gate` stage that runs `pytest -m performance --tb=short` after unit/integration stages pass | CI enforcement of p95 thresholds |

### Interfaces and Contracts

```python
# tests/performance/injectors/base.py
from typing import Protocol
from src.event_pipeline.pipeline_state import RawEventPayload

class EventInjector(Protocol):
    source_type: str  # matches RawEventSource enum value

    def build_payload(self, index: int) -> RawEventPayload: ...


# tests/performance/collectors/latency_collector.py
from dataclasses import dataclass

@dataclass
class LatencyCollector:
    executor: "PipelineExecutor"
    db_session: "AsyncSession"
    injector: EventInjector

    async def run_once(self, index: int) -> float:
        """
        Injects one test event, awaits pipeline completion, reads
        EventRecord.detected_at and AlertRecord.dispatched_at from the DB,
        and returns elapsed seconds as a float.
        Raises AssertionError if either timestamp is None.
        """
        ...


# tests/performance/collectors/performance_reporter.py
from dataclasses import dataclass

@dataclass
class LatencyReport:
    p50: float
    p95: float
    p99: float
    max: float
    sample_count: int

class PerformanceReporter:
    @staticmethod
    def compute(durations: list[float]) -> LatencyReport:
        """
        Accepts a non-empty list of elapsed-second floats.
        Computes percentile statistics using statistics.quantiles or numpy.
        Returns LatencyReport.
        """
        ...
```

## Implementation Tasks

### TASK-001: Test infrastructure — EventInjector base, concrete injectors, conftest fixtures
**Complexity**: M | **TDD**: true
**Files**:
- `tests/performance/conftest.py`
- `tests/performance/injectors/__init__.py`
- `tests/performance/injectors/base.py`
- `tests/performance/injectors/tweet_injector.py`
- `tests/performance/injectors/gdelt_injector.py`
- `tests/performance/injectors/edgar_injector.py`

Define the `EventInjector` Protocol as specified in the Interfaces section. Implement three
concrete injectors:

`TweetEventInjector`: builds `RawEventPayload(source=RawEventSource.X_FILTERED_STREAM, ...)`
with a realistic tweet-like `raw_payload` dict (text, user, timestamp fields). Sets
`detected_at = datetime.utcnow()` at construction time so the clock starts at injection, not
at executor entry. Each call to `build_payload(index)` produces a distinct payload (unique
text and ID) to prevent deduplication from collapsing the 100-event test run.

`GdeltEventInjector`: builds `RawEventPayload(source=RawEventSource.GDELT, ...)` with lat,
lon, category, and a varied `raw_payload` per index.

`EdgarEventInjector`: builds `RawEventPayload(source=RawEventSource.SEC_EDGAR, ...)` with a
`filing_timestamp` field set to `datetime.utcnow()` in the payload. Each filing has a unique
CIK and accession number.

`conftest.py` fixtures:
- `performance_db_session` — yields an `AsyncSession` connected to the test PostgreSQL DB
  (same DB used for integration tests; pgvector extension enabled).
- `isolated_redis` — yields a Redis client bound to a test-only key namespace
  (`perf:{test_run_id}:*`) to avoid cross-contamination with other test suites.
- `pipeline_executor_factory` — yields a factory function that constructs a
  `PipelineExecutor` with all 13 step instances wired, LLM providers replaced with
  deterministic mocks (classify returns fixed category/confidence), and the DB session and
  Redis client from the above fixtures injected. LLM mocks are calibrated to return in
  < 5 ms to isolate infrastructure latency rather than artificial LLM latency.

**Tests to write first (TDD)**:
- `test_tweet_injector_produces_distinct_payloads` — call `build_payload` 10 times; assert
  all raw_payload dicts have distinct content (no dedup collision).
- `test_gdelt_injector_source_type` — assert `injector.source_type == "GDELT"`.
- `test_edgar_injector_filing_timestamp_present` — assert `filing_timestamp` key present in
  each built payload's `raw_payload`.
- `test_conftest_db_session_fixture_connects` — assert DB session can execute a simple SELECT
  without error.
- `test_lm_mock_returns_in_under_5ms` — time the mock LLM call; assert < 5 ms.

**Acceptance criteria covered**: AC-001, AC-002, AC-003 (test infrastructure required for all three)

---

### TASK-002: LatencyCollector and PerformanceReporter
**Complexity**: M | **TDD**: true
**Files**:
- `tests/performance/collectors/__init__.py`
- `tests/performance/collectors/latency_collector.py`
- `tests/performance/collectors/performance_reporter.py`

Implement `LatencyCollector` as specified in Interfaces:

`run_once(index)` performs these steps in sequence:
1. Calls `self.injector.build_payload(index)` to produce the test `RawEventPayload`.
2. Persists a `RawEvent` row via the DB session (mirrors the Celery task entry point) so
   the executor can load it by ID.
3. Calls `await self.executor.run(initial_state)`.
4. Queries the DB for the resulting `EventRecord` and `AlertRecord` by `raw_event_id`.
5. Asserts `event_record.detected_at is not None` and `event_record.generated_at is not None`.
6. Asserts `alert_record.dispatched_at is not None` (for AUTO_SEND route; for HIL_QUEUE route
   uses `hil_queue.created_at` as the dispatched proxy timestamp).
7. Returns `(alert_record.dispatched_at - event_record.detected_at).total_seconds()`.

Implement `PerformanceReporter.compute(durations)`:
- Validates `len(durations) >= 1`.
- Computes p50, p95, p99, max using `statistics.quantiles` (stdlib; no numpy dependency in
  test-only code unless already in the project).
- Returns a `LatencyReport` dataclass.

**Tests to write first (TDD)**:
- `test_collector_run_once_returns_positive_float` — single pipeline run with mock executor;
  assert return value is a positive float.
- `test_collector_raises_if_detected_at_null` — mock EventRecord with `detected_at=None`;
  assert `AssertionError` raised.
- `test_collector_raises_if_dispatched_at_null` — mock AlertRecord with `dispatched_at=None`;
  assert `AssertionError` raised.
- `test_reporter_p95_of_known_sequence` — feed `[1.0] * 95 + [100.0] * 5` (100 values);
  assert `report.p95 == 100.0` and `report.p50 == 1.0`.
- `test_reporter_raises_on_empty_list` — assert `ValueError` on empty input.

**Acceptance criteria covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-003: Performance test suite — three SLA assertions and timestamp-presence assertion
**Complexity**: M | **TDD**: true
**Files**:
- `tests/performance/test_mode_a_latency.py`

Write four `@pytest.mark.performance` test functions. All four use the fixtures and
components from TASK-001 and TASK-002. All four run against the production
`PipelineExecutor` wired with deterministic LLM mocks — no reimplementation of pipeline
logic.

`test_tweet_p95_under_30s`:
- Constructs `LatencyCollector(executor=..., injector=TweetEventInjector())`.
- Calls `run_once(i)` in a loop for `i in range(100)`, collecting 100 elapsed floats.
- Calls `PerformanceReporter.compute(durations)`.
- Asserts `report.p95 < 30.0` with a descriptive failure message that includes the actual
  p95, p99, and max values.

`test_gdelt_p95_under_90s`:
- Same pattern with `GdeltEventInjector()`, 100 events.
- Asserts `report.p95 < 90.0`.

`test_edgar_p95_under_20_minutes`:
- Same pattern with `EdgarEventInjector()`, 20 events (per AC-003).
- Asserts `report.p95 < 1200.0` (20 minutes in seconds).

`test_event_record_timestamps_non_null`:
- Runs one pipeline invocation per source type (tweet, GDELT, EDGAR).
- For each, reads the resulting `EventRecord` from the DB.
- Asserts `event_record.detected_at is not None`.
- Asserts `event_record.generated_at is not None`.
- This test does not assert latency thresholds — it is a data-integrity assertion covering
  AC-004 independently of p95 calculations.

Each test function is decorated with `@pytest.mark.performance` and includes a docstring
citing the source AC.

**Tests to write first (TDD)**:
The four test functions listed above ARE the tests. They are written first. They will fail
until TASK-001 and TASK-002 implementations are complete (red). They pass once collectors
and injectors are wired (green).

**Acceptance criteria covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-004: pytest mark registration and CI gate
**Complexity**: S | **TDD**: false
**Files**:
- `pyproject.toml`
- `.github/workflows/ci.yml` (or `docker-compose.test.yml` if CI uses Compose-based test
  runner; adapt to whichever CI config is present)

Register the `performance` mark in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
markers = [
    "performance: Mode A latency SLA assertions (deselect with -m 'not performance')",
]
```

Add a `performance-gate` stage to the CI pipeline that:
1. Runs after `unit` and `integration` stages complete successfully.
2. Executes `pytest tests/performance/ -m performance --tb=short -v`.
3. Fails the build on any non-zero exit code.
4. The stage is a blocking gate — merge to main is not permitted if it fails.

The default test suite (`pytest` without `-m`) must not include performance tests; the
`not performance` filter must be applied to the default run to keep CI fast.

**Acceptance criteria covered**: AC-001, AC-002, AC-003 (CI gate enforces all three SLAs on every merge)

---

### TASK-005: Performance baseline documentation in test module docstring
**Complexity**: S | **TDD**: false
**Files**:
- `tests/performance/test_mode_a_latency.py` (update from TASK-003)

Add a module-level docstring to `test_mode_a_latency.py` that records:
- The SLA targets (tweet < 30 s, GDELT < 90 s, EDGAR < 20 min).
- The test event counts (100 / 100 / 20).
- The infrastructure assumptions: mocked LLM (< 5 ms), real PostgreSQL + Redis, isolated
  key namespace.
- The architectural reference: ARCHITECTURE.md §6 Latency Budget and §14 NFR Summary.
- A note that these tests measure infrastructure latency under mock-LLM conditions; a
  separate load test against the live system (with real Haiku 4.5 calls) is required before
  production sign-off.

This task exists to make the assumptions explicit and discoverable inside the codebase,
satisfying DEV-STANDARDS.md §9 (observability and logging norms applied to test artefacts).

**Acceptance criteria covered**: AC-001, AC-002, AC-003, AC-004 (baseline documentation
ensures the SLAs and the non-null assertion are traceable to ACs for future reviewers)

## Acceptance Criteria Coverage

| AC | Description | Covered by |
|----|-------------|-----------|
| AC-001 | 100 sequential tweet-class test events processed — p95 detected_at to dispatched_at < 30 seconds | TASK-001, TASK-002, TASK-003, TASK-004 |
| AC-002 | 100 GDELT geo-event test events — p95 detected_at to dispatched_at < 90 seconds | TASK-001, TASK-002, TASK-003, TASK-004 |
| AC-003 | 20 SEC EDGAR filing test events — p95 filing_timestamp to dispatched_at < 20 minutes | TASK-001, TASK-002, TASK-003, TASK-004 |
| AC-004 | Any pipeline run completes — both detected_at and generated_at present and non-null on EventRecord | TASK-002, TASK-003, TASK-005 |

AC coverage: 4/4 = **100%**

## Definition of Done

- [ ] All 5 tasks complete
- [ ] `tests/performance/` passes `pytest -m performance` with zero failures on the CI test environment
- [ ] `test_tweet_p95_under_30s` asserts p95 < 30 s with 100 events
- [ ] `test_gdelt_p95_under_90s` asserts p95 < 90 s with 100 events
- [ ] `test_edgar_p95_under_20_minutes` asserts p95 < 1 200 s with 20 events
- [ ] `test_event_record_timestamps_non_null` passes for all three source types
- [ ] `pytest` (default, no `-m` flag) does not include performance tests
- [ ] CI `performance-gate` stage is present and blocking
- [ ] `LatencyCollector` raises `AssertionError` on any null timestamp (not a silent pass)
- [ ] `PerformanceReporter` is a pure function — no DB or Redis access
- [ ] `EventInjector` subclasses produce distinct payloads per index (no dedup collisions)
- [ ] LLM mock latency < 5 ms per call (measured by `test_lm_mock_returns_in_under_5ms`)
- [ ] No TODO/FIXME in produced code
- [ ] TDD red-green-refactor cycle followed for all M-complexity tasks (TASK-001, TASK-002, TASK-003)
- [ ] dev-code-review run and all Critical/High findings resolved
- [ ] PLAN-F-001 executed (EventRecord, AlertRecord, PipelineExecutor importable) before any TASK in this plan begins

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | REQ-N-001 OQ-1: Tweet alert < 30 s — sub-targets per pipeline step not allocated | Resolved by design: this plan measures the end-to-end elapsed time and asserts at the p95 level. Per-step sub-targets are not enforced; if the p95 SLA is breached, Langfuse trace spans (written by TraceStep in PLAN-F-001) provide step-level breakdown for root-cause analysis. No new per-step assertions are added to avoid brittle tests that break under normal variance. |

## Risks and Notes

- **PLAN-F-001 hard prerequisite**: All five tasks in this plan depend on `PipelineExecutor`,
  `EventRecord`, `AlertRecord`, `RawEventPayload`, and `RawEventSource` being importable from
  `src/`. Do not start any task until PLAN-F-001 is at status `done` (or at minimum its
  TASK-001 and TASK-002 are complete and the models exist).

- **Mock vs real LLM latency**: The performance tests use deterministic LLM mocks (< 5 ms)
  to isolate infrastructure latency (Redis, PostgreSQL, Celery scheduling overhead). This
  gives a lower-bound latency measurement. Before production sign-off, a manual run with
  real Haiku 4.5 calls must be performed to verify the SLAs hold end-to-end. The Haiku 4.5
  p99 classify latency is typically 1–3 seconds per call; with two LLM calls per event
  (classify + confidence), the real-call budget for all other steps is approximately 24
  seconds for the tweet SLA.

- **Deduplication must be bypassed in performance tests**: the 100-event test loop submits
  events in rapid sequence. `TweetEventInjector.build_payload(index)` must produce a unique
  fingerprint per index (e.g. embed `index` in the payload text and ID). If deduplication
  triggers on any event, the `LatencyCollector` will receive a `DuplicateEvent` exception
  and the run count will be short. TASK-001 tests must verify distinctness.

- **AlertRecord dispatched_at for HIL_QUEUE route**: if the test executor's mock confidence
  is set below 0.7, events route to HIL_QUEUE and no `AlertRecord` with `dispatched_at` is
  written. `LatencyCollector` handles this by using `hil_queue.created_at` as the proxy
  timestamp. Mock confidence in performance tests must be set to >= 0.7 to produce
  `AUTO_SEND` routes and true `dispatched_at` values, unless the test specifically targets
  the HIL path.

- **Celery task execution in tests**: the performance tests call `PipelineExecutor.run()`
  directly — they do not go through the Celery task queue. This avoids Celery worker boot
  overhead and broker round-trip from skewing latency measurements. The Celery task entry
  point (`pipeline_task.py`) is not under test here; that is covered by PLAN-F-001
  TASK-013.

- **p95 with N=20 for EDGAR**: twenty events is a small sample for a stable p95 estimate.
  The EDGAR SLA of 20 minutes is generous enough that the p95 of 20 samples is still a
  meaningful signal (one outlier at the top). If flakiness is observed, the EDGAR sample
  count can be raised to 50 without changing the assertion threshold.

- **CI environment performance**: the `performance-gate` CI stage must run on a consistent
  instance type to avoid false failures. If CI runners vary in resource allocation, consider
  using a fixed `runs-on` label (e.g. a dedicated performance runner) or relaxing the p95
  threshold to 20 s / 60 s / 15 min for CI and reserving the tight SLA check for a
  scheduled nightly run.
