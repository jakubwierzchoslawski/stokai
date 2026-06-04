---
plan_id: PLAN-N-003
slug: mode-a-cost
title: Mode A Per-Event Cost Ceiling
linked_requirement: REQ-N-003
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-001, reason: "CostAccumulator and CostCeilingExceededError are defined in the pipeline; this plan extends them with pricing tables and writes cost to the alert row" }
  - { id: PLAN-F-011, reason: "ExecutionLimiter enforces per-agent cost_ceiling_usd from YAML; this plan adds the cost-exceeded routing path and tests for that contract" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-003 — Mode A Per-Event Cost Ceiling

## Linked Requirement
**REQ-N-003** — Mode A Per-Event Cost Ceiling
Status: approved | Jira: —

## Objective
Implement the full cost-measurement and hard-stop enforcement mechanism for Mode A pipeline
runs. The four LLM / API calls within a single pipeline run (Haiku 4.5 classify, Haiku 4.5
extract, Sonnet 4.6 alert text, OpenAI text-embedding-3-small embed) are priced using a
`LLMPricingTable` utility, accumulated by the existing `CostAccumulator` from PLAN-F-001, and
checked against a $0.05 hard ceiling after each call. When the ceiling is exceeded, the
pipeline raises `CostCeilingExceededError` and halts before the next step executes. On every
completed run (successful or halted), the `total_cost_usd` from `PipelineResult` is written to
a new `cost_usd` column on the `alert` row (or the silent-log entry) so that the admin cost
monitor can surface it. Integration tests assert the $0.05 hard ceiling and the cost-field
write. The per-agent enforcement path defined in PLAN-F-011 (`ExecutionLimiter`) is tested from
this plan's perspective by verifying that a simulated ceiling breach from a Mode B agent YAML
propagates correctly as a `LimitExceededError`.

## Architecture Context
This plan touches Layer 4 (Processing) and Layer 3 (Storage) of the six-layer model
(ARCHITECTURE.md §4).

- **Layer 4 — Processing (`src/events/`)**: Extends `CostAccumulator` (PLAN-F-001,
  `src/events/cost_accumulator.py`) with a `LLMPricingTable` helper that converts raw token
  counts to USD for each model. Steps 2, 3, 6, and 8 of the pipeline already call
  `ctx.cost_accumulator.add(cost_usd)` and `check_ceiling(0.05)` per PLAN-F-001's design;
  this plan ensures the pricing computation feeding those calls is accurate and tested.

- **Layer 3 — Storage (`src/storage/`)**: The `alert` table (ARCHITECTURE.md §10 Portfolio and
  Alerts) does not yet carry a `cost_usd` column. A database migration adds it. The
  `AlertRepository.insert_alert` method is extended to write the value. The `workflow_run`
  table already has `cost_usd` (written by `return_pipeline_result` in step 12 of PLAN-F-001).

- **Cost governance** (ARCHITECTURE.md §12.6): The $0.05 per-event ceiling is the Mode A
  tier of the three-level budget enforcement hierarchy (per-agent → per-workflow → per-user/day).
  This plan implements the per-workflow (per-pipeline-run) enforcement tier for Mode A. The
  per-agent tier for Mode B is implemented in PLAN-F-011 (`ExecutionLimiter`); this plan only
  verifies the observable contract from the pipeline's point of view.

- **Observability** (ARCHITECTURE.md §12.4): `cost_usd` is already a field on every Langfuse
  span (recorded by `LangfuseTracer.end_span`). This plan does not change the Langfuse
  integration; it ensures the value fed into each span is accurate via the pricing table.

Module ownership:
- `src/events/` — `LLMPricingTable`, pricing constants, pricing tests, integration test
- `src/storage/` — DB migration for `alert.cost_usd`; `AlertRepository` extension
- `tests/unit/events/` — unit tests for pricing table and accumulator ceiling behaviour
- `tests/integration/events/` — cost-ceiling integration test for the pipeline
- `tests/unit/ai/` — contract test for `ExecutionLimiter` ceiling breach from PLAN-F-011

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-003 (self) | Hard stop at $0.05 per Mode A run; mean < $0.03 over 1,000 runs; cost_usd on alert row | All tasks in this plan exist to satisfy these three sub-targets |

## Component Design

### New Components
```
Module: events (src/events/)
  └── pricing.py
        LLMPricingTable  — maps (model_id, input_tokens, output_tokens) → cost_usd
        MODEL_PRICES     — dict of per-model pricing constants (USD per 1k tokens)

Module: storage (src/storage/)
  └── migrations/
        NNNN_add_cost_usd_to_alert.py  — Alembic migration; adds NUMERIC(10,6) cost_usd
                                          DEFAULT NULL to the alert table

tests/
  unit/events/
    test_llm_pricing_table.py          — unit tests for LLMPricingTable
    test_cost_accumulator_ceiling.py   — unit tests for accumulator ceiling behaviour
  unit/ai/
    test_execution_limiter_cost.py     — contract tests for PLAN-F-011 ExecutionLimiter
                                         (cost_ceiling_usd path only)
  integration/events/
    test_pipeline_cost_ceiling.py      — integration tests asserting AC-001, AC-002, AC-003
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/events/cost_accumulator.py` | Import and use `LLMPricingTable` to compute `cost_usd` from token counts; no change to the `add`/`check_ceiling` public API | Centralise pricing so all four LLM steps use the same calculation |
| `src/storage/implementations/alert_repository.py` | Extend `insert_alert` to accept and write `cost_usd: float \| None` | Persist per-run cost on the alert row (AC-003) |
| `src/events/steps/classify_event.py` | Call `LLMPricingTable.compute("claude-haiku-4-5", input_tokens, output_tokens)` instead of a hard-coded constant; pass result to `cost_accumulator.add()` | Accurate pricing for step 2 |
| `src/events/steps/extract_tickers.py` | Same pricing-table pattern for Haiku 4.5 | Accurate pricing for step 3 |
| `src/events/steps/embed_event.py` | Call `LLMPricingTable.compute("text-embedding-3-small", input_tokens, 0)` | Accurate pricing for step 6 |
| `src/events/steps/generate_alert_text.py` | Call `LLMPricingTable.compute("claude-sonnet-4-6", input_tokens, output_tokens)` | Accurate pricing for step 8 |
| `src/events/steps/dispatch_or_log_silent.py` | Pass `ctx.cost_accumulator.total` into `alert_repo.insert_alert(...)` as `cost_usd` | Writes total run cost to the alert row (AC-003) |

### Interfaces and Contracts

```python
# src/events/pricing.py

MODEL_PRICES: dict[str, dict[str, float]] = {
    # Prices in USD per 1,000 tokens (input / output)
    "claude-haiku-4-5":       {"input": 0.00025, "output": 0.00125},
    "claude-sonnet-4-6":      {"input": 0.003,   "output": 0.015},
    "text-embedding-3-small": {"input": 0.00002,  "output": 0.0},   # OpenAI embedding
}

class LLMPricingTable:
    """Convert token counts to USD cost for supported models.

    Raises:
        ValueError: if model_id is not in MODEL_PRICES.
    """

    @staticmethod
    def compute(model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Return cost in USD. Both token counts must be non-negative integers."""
        ...

    @staticmethod
    def supported_models() -> list[str]:
        """Return the list of model_ids with known pricing."""
        ...


# src/events/cost_accumulator.py  (public API unchanged; internal change only)

class CostAccumulator:
    """Track accumulated USD cost for a single pipeline run."""

    def __init__(self) -> None:
        self._total: float = 0.0

    @property
    def total(self) -> float:
        """Current accumulated cost in USD."""
        ...

    def add(self, cost_usd: float) -> None:
        """Add cost_usd to the running total. cost_usd must be >= 0."""
        ...

    def check_ceiling(self, ceiling: float) -> None:
        """Raise CostCeilingExceededError if total > ceiling."""
        ...

    def add_from_tokens(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Convenience: compute cost via LLMPricingTable, add, and return computed cost."""
        ...
```

The `add_from_tokens` method is a new convenience helper that the four LLM steps call instead
of managing the pricing-table call themselves. Steps import `CostAccumulator` only; they do not
import `LLMPricingTable` directly (Interface Segregation).

```python
# src/storage/implementations/alert_repository.py  (signature extension)

class AlertRepository:
    async def insert_alert(
        self,
        alert_data: dict,
        cost_usd: float | None = None,   # NEW — added by this plan
    ) -> UUID: ...

    async def insert_silent_log(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
        cost_usd: float | None = None,   # NEW — added by this plan
    ) -> None: ...
```

## Implementation Tasks

### TASK-001: LLMPricingTable and MODEL_PRICES · M/TDD · src/events/pricing.py, tests/unit/events/test_llm_pricing_table.py

Implement `LLMPricingTable` in `src/events/pricing.py`. Define `MODEL_PRICES` dict with pricing
entries for `claude-haiku-4-5`, `claude-sonnet-4-6`, and `text-embedding-3-small` as specified
in the Interfaces and Contracts section. `LLMPricingTable.compute(model_id, input_tokens,
output_tokens)` multiplies token counts by their per-1k rates and returns the sum as a float.
`supported_models()` returns the keys of `MODEL_PRICES`. Raise `ValueError` for an unknown
`model_id`. The constants are designed around the token budgets from ARCHITECTURE.md §6:
classify (2k in / 200 out via Haiku), extract (1k in / 100 out via Haiku), embed (500 in via
OpenAI), alert text (3k in / 200 out via Sonnet). The maximum possible per-run cost using these
token budgets must be documented in a docstring comment and must be below $0.05.

**Tests to write first (TDD)**:
- `test_compute_haiku_classify_budget` — 2000 input + 200 output at Haiku rates returns the
  expected USD value (< $0.001)
- `test_compute_sonnet_alert_budget` — 3000 input + 200 output at Sonnet rates returns the
  expected USD value (< $0.05)
- `test_compute_embedding_no_output_tokens` — output_tokens=0 does not raise and returns a
  non-negative float
- `test_compute_unknown_model_raises_value_error` — unknown model_id raises `ValueError`
- `test_compute_negative_tokens_raises_value_error` — negative input_tokens raises `ValueError`
- `test_supported_models_returns_all_three` — all three model IDs are present in the returned
  list
- `test_max_budget_scenario_below_ceiling` — compute sum of (classify + extract + embed +
  alert) at max token budgets; assert total < 0.05

**AC covered**: AC-001, AC-002

---

### TASK-002: CostAccumulator — add_from_tokens convenience method · M/TDD · src/events/cost_accumulator.py, tests/unit/events/test_cost_accumulator_ceiling.py

Extend `CostAccumulator` (defined in PLAN-F-001's TASK-001) with the `add_from_tokens` method
that delegates to `LLMPricingTable.compute` then calls `self.add()`. The `total` property,
`add()`, and `check_ceiling()` behaviours are already implemented; this task verifies them via
new tests and adds the convenience method. `add_from_tokens` returns the computed cost so the
caller can pass it to `LangfuseTracer.end_span`. `check_ceiling` must raise
`CostCeilingExceededError` from `src/events/exceptions.py` when `total > ceiling`; the
exception must carry `accumulated_usd` and `ceiling_usd` attributes. No change is made to the
public API of `add` or `check_ceiling`.

**Tests to write first (TDD)**:
- `test_add_from_tokens_returns_computed_cost` — returned float equals `LLMPricingTable.compute`
  for the same arguments
- `test_add_from_tokens_increments_total` — after call, `accumulator.total` increases by the
  returned amount
- `test_check_ceiling_raises_when_exceeded` — after adding $0.04 and then $0.02, calling
  `check_ceiling(0.05)` raises `CostCeilingExceededError`
- `test_check_ceiling_passes_at_exact_limit` — `total == ceiling` does NOT raise (ceiling is
  exclusive upper bound: `total > ceiling`)
- `test_check_ceiling_not_raised_below_limit` — `total = 0.04`, `ceiling = 0.05` — no raise
- `test_cost_ceiling_exceeded_error_carries_attributes` — exception has `accumulated_usd` and
  `ceiling_usd` float attributes set correctly
- `test_add_from_tokens_unknown_model_propagates_value_error` — `ValueError` from pricing table
  propagates unchanged; accumulator total is not modified

**AC covered**: AC-002

---

### TASK-003: LLM step wiring — pricing-table calls in all four steps · S/no-TDD · src/events/steps/classify_event.py, src/events/steps/extract_tickers.py, src/events/steps/embed_event.py, src/events/steps/generate_alert_text.py

Replace any hard-coded cost constants in the four LLM steps with calls to
`ctx.cost_accumulator.add_from_tokens(model_id, input_tokens, output_tokens)`. The `model_id`
strings are: `"claude-haiku-4-5"` (steps 2 and 3), `"text-embedding-3-small"` (step 6),
`"claude-sonnet-4-6"` (step 8). The returned cost float is forwarded to
`tracer.end_span(..., cost_usd=cost)`. Each step still calls
`ctx.cost_accumulator.check_ceiling(0.05)` after `add_from_tokens`. No behaviour change is
introduced beyond the pricing accuracy fix; existing PLAN-F-001 tests must continue to pass.

**AC covered**: AC-001, AC-002

---

### TASK-004: alert.cost_usd — DB migration and repository extension · S/no-TDD · src/storage/migrations/NNNN_add_cost_usd_to_alert.py, src/storage/implementations/alert_repository.py

Write an Alembic migration that adds `cost_usd NUMERIC(10,6) DEFAULT NULL` to the `alert`
table. NULL is acceptable for historical rows created before this migration is applied. Extend
`AlertRepository.insert_alert` to accept and write `cost_usd: float | None = None`. Extend
`AlertRepository.insert_silent_log` with the same parameter (for completeness; the admin cost
monitor can query either type). Update `dispatch_or_log_silent` (step 10) to pass
`ctx.cost_accumulator.total` as `cost_usd` in both the dispatch and silent-log code paths.
The migration must be reversible (downgrade drops the column).

**AC covered**: AC-003

---

### TASK-005: ExecutionLimiter cost-ceiling contract test · M/TDD · tests/unit/ai/test_execution_limiter_cost.py

Write tests that exercise the cost-ceiling path of `ExecutionLimiter` from PLAN-F-011
(`src/ai/limits/execution_limiter.py`) from the perspective of a Mode B agent invocation
exceeding its `cost_ceiling_usd`. This task does not modify `ExecutionLimiter`; it adds
missing coverage to confirm the contract that PLAN-N-003 depends on. The tests verify:

- Given an `AgentDefinition` with `cost_ceiling_usd=0.10`, when the limiter's cost accumulation
  reaches $0.10 + epsilon, it raises `LimitExceededError` with `limit_type=LimitType.COST_CEILING`
- The `LimitExceededError` carries `limit_value=0.10` and `actual_value > 0.10`
- When cost is below the ceiling, `ExecutionLimiter` does not raise
- When cost exactly equals the ceiling, it does NOT raise (mirrors Mode A semantics: ceiling is
  exclusive upper bound)

**Tests to write first (TDD)**:
- `test_cost_ceiling_exceeded_raises_limit_exceeded_error`
- `test_cost_ceiling_not_raised_at_exact_ceiling`
- `test_cost_ceiling_not_raised_below_ceiling`
- `test_limit_exceeded_error_has_correct_limit_type`
- `test_limit_exceeded_error_carries_actual_value`

**AC covered**: AC-002

---

### TASK-006: Pipeline cost-ceiling integration tests · M/TDD · tests/integration/events/test_pipeline_cost_ceiling.py

Write three integration tests that exercise the full pipeline against mocked LLM clients and a
real test database (same setup as PLAN-F-001 TASK-025). All tests share a pytest fixture that
constructs a `PipelineExecutor` with a `MockLLMClient` and `MockEmbeddingClient` whose token
counts are configurable per invocation.

**Test 1 — happy-path cost recording**: Configure mock clients to return token counts that
produce a total cost of ~$0.02 (well under ceiling). Assert that after `executor.run(raw_event)`
completes: `PipelineResult.total_cost_usd` is approximately $0.02 (within floating-point
tolerance); the `alert` row in the DB has `cost_usd` set to the same value; `cost_usd ≤ 0.05`.

**Test 2 — hard stop at $0.05**: Configure mock clients so that the first three LLM calls
accumulate $0.04, and the fourth call (`generate_alert_text`) would push total to $0.06. Assert
that: `executor.run()` raises `PipelineError` (wrapping `CostCeilingExceededError`) before step
8 completes; the geo_event and event_exposure rows ARE persisted (steps 1–5 ran); the step-8
Langfuse span is NOT closed with a cost (the ceiling was hit mid-step); no alert row exists (the
ceiling was hit before dispatch).

**Test 3 — cost below mean target**: Run 10 consecutive pipeline executions with realistic
token counts (classify: 1800 in / 150 out Haiku, extract: 800 in / 80 out Haiku, embed: 400 in
OpenAI, alert: 2500 in / 160 out Sonnet). Assert that the mean `PipelineResult.total_cost_usd`
across 10 runs is less than $0.03, satisfying the REQ-N-003 mean target.

**Tests to write first (TDD)**:
- `test_happy_path_cost_recorded_on_alert_row` (Test 1)
- `test_cost_ceiling_halts_pipeline_before_step_8` (Test 2)
- `test_mean_cost_below_0_03_over_ten_runs` (Test 3)

**AC covered**: AC-001, AC-002, AC-003

---

## Acceptance Criteria Coverage

- AC-001: Given 1,000 consecutive pipeline runs, the mean cost per run is < $0.03 and the
  maximum cost per run does not exceed $0.05 → TASK-001, TASK-002, TASK-003, TASK-006
- AC-002: Given an agent's per-invocation cost would exceed its cost_ceiling_usd from the YAML,
  the agent execution terminates immediately and returns a cost-exceeded error rather than
  completing the call → TASK-002, TASK-005, TASK-006
- AC-003: Given every completed pipeline run, the cost_usd field on the alert row accurately
  records the total LLM and API cost for that run → TASK-004, TASK-006

## Risks and Notes

- **Pricing constants drift**: LLM provider pricing can change without notice. `MODEL_PRICES`
  in `src/events/pricing.py` must be reviewed each time Anthropic or OpenAI publishes new
  pricing. The per-model pricing test (`test_compute_haiku_classify_budget`,
  `test_compute_sonnet_alert_budget`) will fail if constants diverge from reality by > 10%,
  surfacing the need for a review.
- **Ceiling is enforced after the call**: `check_ceiling` is called after `add_from_tokens`
  completes, which means the over-budget LLM step has already made the API call. The next step
  is blocked, but the cost of the triggering step is already incurred. This is acceptable (see
  PLAN-F-001 risks) and is preserved in this plan.
- **alert.cost_usd is NULL for silent-log paths**: When no alert rule matches, `insert_silent_log`
  is called. The `cost_usd` is still written on the silent-log entry so the admin cost monitor
  can account for non-alerting pipeline runs. Ensure the cost monitor query covers both the
  `alert` table and the silent-log table (or the `workflow_run` table which always has `cost_usd`).
- **PLAN-F-001 dependency on public API**: TASK-002 and TASK-003 modify files that PLAN-F-001
  defines. The executor (task-executor) must treat this plan as a targeted extension of PLAN-F-001
  output, not a rewrite. Confirm that PLAN-F-001 TASK-001 has been executed before running
  TASK-002 of this plan.
- **PLAN-F-011 dependency for TASK-005**: `ExecutionLimiter` must be implemented (PLAN-F-011
  TASK-006) before TASK-005 tests can run. If PLAN-F-011 is not yet executed, TASK-005 will
  fail at import time.
- **Mean cost assertion in TASK-006 Test 3**: The token counts used in that test are chosen to
  be representative, not worst-case. The test is a regression guard, not a statistical proof.
  AC-001's 1,000-run statistical requirement is verified by the Langfuse cost-per-trace
  dashboard in production, not by the automated test suite.
