---
plan_id: PLAN-F-003
slug: portfolio-scoring-engine
title: Portfolio & Company Scoring Engine
linked_requirement: REQ-F-003
type: functional
status: done
blocked_reason:
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-005, reason: "Tool output hard-capped at 50 rows; no unbounded score queries permitted" }
  - { id: REQ-N-003, reason: "Score recomputation must not trigger redundant external API calls; cache-first lookup enforced via provider abstraction" }
dependencies:
  - { id: PLAN-F-002, reason: "ProviderRegistry and typed Protocol interfaces supply all raw data inputs (price, fundamentals, earnings) consumed by the DSL evaluator" }
brainstorm_decisions:
  - decision: geo_weight formula
    options_considered:
      - "Point-in-time intensity lookup (single event, max intensity)"
      - "Weighted linear combination capped at configurable multiplier"
      - "Multiplicative cascade per active event"
    chosen: "Weighted linear combination: geo_weight = min(1.0 + sum(event.intensity * event.exposure_fraction for event in active_events_for_company), cap). Default cap=2.0 stored in MarketConfig."
    rationale: "OQ-1 resolved: linear combination is auditable, bounded, and configurable per market without code changes. A cap of 2.0 prevents runaway score inflation under event saturation. Formula stored as configurable multiplier cap in MarketConfig."
    decided_at: 2026-05-31T00:00:00Z
  - decision: Score history strategy
    options_considered:
      - "Point-in-time snapshot — store only latest score, snapshot on demand"
      - "Full append-only history — every recomputation writes a new row, never updates"
    chosen: "Full append-only history table (score_records). Every recomputation appends a new row. Historical mode queries by computed_at range."
    rationale: "OQ-2 resolved: append-only aligns with P-08 Immutable Episodic Memory and the architecture's data retention requirement (TTL-infinity for score history). Enables full time-machine without snapshots."
    decided_at: 2026-05-31T00:00:00Z
executed_at: 2026-06-01T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-05-31T00:00:00Z
updated_at: 2026-05-31T00:00:00Z
---

# PLAN-F-003 — Portfolio & Company Scoring Engine

## Linked Requirement
**REQ-F-003** — Portfolio & Company Scoring Engine
Status: approved | Jira: (blank)

## Objective
Build the `src/scoring/` module — the analytical core of StokAI. The module
implements: (1) an `inputs_hash` invalidation engine that recomputes scores for
exactly the companies whose upstream data has changed, without polling; (2) a
recursive AST interpreter that evaluates scoring DSL formulas with arithmetic,
logical, ranking, and time-series operators; (3) a `geo_weight` modifier that
scales each company's score by a weighted linear combination of active geopolitical
event intensities and exposure fractions, capped at a per-market configurable limit;
(4) a market-agnostic scoring pipeline that respects the `MarketConfig` registry,
requiring zero code changes when new markets are added; (5) an append-only
`score_records` persistence layer that stores full provenance (indicator version,
inputs hash, timestamps) for Historical time-machine queries; and (6) a read-only
Tool Library entry (`get_event_exposure_score`) exposing scored results as
Pydantic-typed objects, capped at 50 rows.

## Architecture Context
This plan introduces `src/scoring/` as a new first-class module in the FastAPI
monolith (ARCHITECTURE.md §4 Component Architecture, Decision D1). It occupies the
scoring layer referenced in the 13-step Mode A pipeline (step 7 — EXPOSURE SCORE,
ARCHITECTURE.md §6) and supplies data consumed by Mode B agents via the Tool
Library (ARCHITECTURE.md §8, tool `get_event_exposure_score`).

**Dependency chain (top → bottom, no upward imports):**

```
src/event_pipeline/score/     ← calls ScoringEngine (Mode A step 7)
src/workflows/tools/          ← calls ScoreTool read interface
src/admin/scoring/            ← calls DSL catalog management
        │
src/scoring/                  ← THIS MODULE
        │
src/providers/                ← PLAN-F-002 (raw data inputs via typed Protocols)
src/markets/                  ← MarketConfig registry
src/db/                       ← score_records table, indicator_versions table
src/cache/                    ← Redis L1 via CacheFirstMixin
```

Principle P-01 (Provider Abstraction) is upheld: the DSL evaluator never calls
provider APIs directly; it fetches data through the Tool Library read tools (which
route through the provider registry). Principle P-03 (Inputs-Hash Invalidation)
governs when recomputation is triggered. Principle P-08 (Immutable Episodic Memory)
governs how score_records are written.

**Layers introduced or extended:**

| Layer | Action |
|---|---|
| `src/scoring/` | New module (interfaces, DSL, geo_weight, pipeline, tools) |
| `src/db/models/` | New ORM models: `ScoreRecord`, `IndicatorVersion` |
| `src/db/migrations/` | New Alembic migration for `score_records`, `indicator_versions` tables |
| `src/workflows/tools/` | New tool: `get_event_exposure_score` |
| `src/markets/` | Extended: `MarketConfig` gains `geo_weight_cap` field |

## Brainstorm Decisions

### geo_weight Formula (OQ-1)
`geo_weight = min(1.0 + Σ(event.intensity * event.exposure_fraction), cap)`

- `cap` defaults to `2.0`, stored as `geo_weight_cap` in `MarketConfig` — configurable per market without code changes (P-05 Zero-Change Market Extension).
- `exposure_fraction` ∈ [0.0, 1.0] — fraction of the company's revenue/assets exposed to the event's geographic region (sourced from company's holdings data).
- Formula yields 1.0 when no active events affect the company; saturates at `cap` under high-intensity, high-exposure event stacking.
- Applied as a multiplier: `final_score = dsl_score × geo_weight`.

### Score History Strategy (OQ-2)
Full append-only `score_records` table. Every recomputation inserts a new row.
Queries for "current" score use `ORDER BY computed_at DESC LIMIT 1`. Historical
mode queries provide a `computed_at` range. No UPDATE ever touches this table.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-005 | Tool output max 50 rows | `get_event_exposure_score` hard-codes `LIMIT 50`; enforced at repository level, not only in the tool wrapper |
| REQ-N-003 | Cost control — no redundant external calls | DSL evaluator fetches inputs via Tool Library (cache-first, TTL-infinity); hash-gated recomputation ensures no wasteful re-evaluation of unchanged inputs |

## Component Design

### New Components

```
Module: src/scoring/
  ├── interfaces.py              — Protocol definitions (ScoringEngine, DslEvaluator,
  │                                GeoWeightCalculator, ScoreRepository, HashEngine)
  ├── hash_engine.py             — SHA-256 inputs_hash computation and mismatch detection
  ├── dsl/
  │   ├── __init__.py
  │   ├── ast_nodes.py           — Frozen dataclass AST node hierarchy (Expr, BinaryOp,
  │   │                            UnaryOp, FunctionCall, Literal, IdentifierRef)
  │   ├── parser.py              — Recursive-descent parser: DSL text → AST
  │   ├── evaluator.py           — Recursive AST interpreter (visits each node type)
  │   └── operators/
  │       ├── arithmetic.py      — +, -, *, /, ^  (ArithmeticOperatorRegistry)
  │       ├── logical.py         — AND, OR, IF
  │       ├── ranking.py         — RANK_SECTOR, PERCENTILE
  │       └── timeseries.py      — CHANGE, CAGR, CORR, ZSCORE
  ├── geo_weight.py              — GeoWeightCalculator: exposure map query + formula
  ├── pipeline.py                — ScoringPipeline: orchestrates hash-check → DSL eval
  │                                → geo_weight → persist
  ├── repository.py              — ScoreRepository: append-only writes; score reads
  │                                with tenant scoping and 50-row cap
  └── exceptions.py              — DslParseError, DslEvalError, HashMismatchNotice,
                                   InsufficientDataError

Module: src/workflows/tools/score_tool.py   (new tool in existing tools module)
  └── GetEventExposureScoreTool  — Pydantic I/O; delegates to ScoreRepository

Module: src/db/models/scoring.py            (new ORM models)
  ├── ScoreRecord                — ORM model for score_records table
  └── IndicatorVersion           — ORM model for indicator_versions table

Module: src/db/migrations/
  └── xxxx_add_scoring_tables.py — Alembic migration
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/markets/config.py` | Add `geo_weight_cap: float = 2.0` field to `MarketConfig` | Configurable cap per market for geo_weight formula (OQ-1) |
| `src/workflows/tools/__init__.py` | Register `GetEventExposureScoreTool` | Expose new tool to agent tool library |
| `src/event_pipeline/score/` | Wire `ScoringPipeline` into Mode A step 7 | Replace any stub with full implementation |

### Interfaces and Contracts

The executor must implement these interfaces exactly; callers depend on them.

```python
# src/scoring/interfaces.py

from typing import Protocol, Sequence
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class InputSnapshot(BaseModel):
    company_id: UUID
    indicator_id: UUID
    raw_inputs: dict[str, float | int | str]


class ScoreResult(BaseModel):
    score_id: UUID
    company_id: UUID
    indicator_id: UUID
    indicator_version_id: UUID
    score: float
    geo_weight_applied: float
    inputs_hash: str
    computed_at: datetime
    tenant_id: UUID


class ScoreQuery(BaseModel):
    tenant_id: UUID
    company_ids: list[UUID] | None = None
    indicator_id: UUID | None = None
    computed_at_from: datetime | None = None
    computed_at_to: datetime | None = None
    limit: int = 50          # hard ceiling enforced in repository


class HashEngine(Protocol):
    def compute(self, snapshot: InputSnapshot) -> str: ...
    def has_changed(self, snapshot: InputSnapshot, stored_hash: str) -> bool: ...


class DslEvaluator(Protocol):
    def evaluate(self, dsl_expression: str, context: dict[str, float]) -> float: ...


class GeoWeightCalculator(Protocol):
    def calculate(self, company_id: UUID, tenant_id: UUID) -> float: ...


class ScoreRepository(Protocol):
    def append(self, result: ScoreResult) -> None: ...
    def get_latest(self, query: ScoreQuery) -> Sequence[ScoreResult]: ...
    def get_stored_hash(self, company_id: UUID, indicator_id: UUID,
                        tenant_id: UUID) -> str | None: ...


class ScoringEngine(Protocol):
    def recompute_if_stale(
        self,
        snapshot: InputSnapshot,
        indicator_version_id: UUID,
        dsl_expression: str,
        tenant_id: UUID,
    ) -> ScoreResult | None:
        """Returns ScoreResult if recomputed, None if hash unchanged."""
        ...
```

```python
# src/workflows/tools/score_tool.py  — Tool Library contract

class GetEventExposureScoreInput(BaseModel):
    tenant_id: UUID
    company_ids: list[UUID] | None = None
    indicator_id: UUID | None = None
    computed_at_from: datetime | None = None
    computed_at_to: datetime | None = None
    limit: int = 50

class GetEventExposureScoreOutput(BaseModel):
    scores: list[ScoreResult]       # len(scores) <= 50 always
    truncated: bool                 # True if backend had more results
```

```python
# DSL AST node hierarchy — src/scoring/dsl/ast_nodes.py

from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class Literal_:
    value: float

@dataclass(frozen=True)
class IdentifierRef:
    name: str           # resolves to a key in the evaluation context dict

@dataclass(frozen=True)
class BinaryOp:
    op: Literal["+", "-", "*", "/", "^"]
    left: "Expr"
    right: "Expr"

@dataclass(frozen=True)
class FunctionCall:
    name: str           # RANK_SECTOR | PERCENTILE | CHANGE | CAGR | CORR | ZSCORE | IF | AND | OR
    args: tuple["Expr", ...]

Expr = Literal_ | IdentifierRef | BinaryOp | FunctionCall
```

## Implementation Tasks

Tasks are ordered by dependency: infrastructure first, DSL core second, pipeline
integration third, API/tool surface last. All tasks at complexity M or above carry
`TDD: true` per DEV-STANDARDS §6 and the `default_tdd_threshold: M` config.

---

### TASK-001: DB Models and Alembic Migration
**Complexity**: S | **TDD**: false
**Files**:
- `src/db/models/scoring.py`
- `src/db/migrations/xxxx_add_scoring_tables.py`

Create SQLAlchemy 2 ORM models for `score_records` and `indicator_versions`.

`score_records` columns: `score_id UUID PK`, `tenant_id UUID NOT NULL`,
`company_id UUID NOT NULL`, `indicator_id UUID NOT NULL`,
`indicator_version_id UUID NOT NULL`, `score FLOAT NOT NULL`,
`geo_weight_applied FLOAT NOT NULL DEFAULT 1.0`, `inputs_hash TEXT NOT NULL`,
`computed_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

`indicator_versions` columns: `id UUID PK`, `indicator_id UUID NOT NULL`,
`version_number INT NOT NULL`, `dsl_expression TEXT NOT NULL`,
`created_at TIMESTAMPTZ NOT NULL`, `created_by UUID`.

Both tables carry `tenant_id` (D3). `score_records` is a TimescaleDB hypertable
partitioned on `computed_at` (matches ARCHITECTURE.md §5 schema).

Write Alembic migration. Include index on `(tenant_id, company_id, indicator_id,
computed_at DESC)` for efficient latest-score lookups.

**Acceptance criteria covered**: AC-005 (provenance fields exist in DB)

---

### TASK-002: Extend MarketConfig with geo_weight_cap
**Complexity**: S | **TDD**: false
**Files**:
- `src/markets/config.py`

Add `geo_weight_cap: float = 2.0` field to the existing `MarketConfig` dataclass.
Default 2.0 is backward-compatible: existing market config entries that omit the
field inherit the default. Document the field in the inline docstring.

**Acceptance criteria covered**: AC-003, AC-004

---

### TASK-003: Scoring Module Interfaces and Exceptions
**Complexity**: S | **TDD**: false
**Files**:
- `src/scoring/__init__.py`
- `src/scoring/interfaces.py`
- `src/scoring/exceptions.py`

Declare the Protocol interfaces exactly as specified in the Interfaces and Contracts
section above (`HashEngine`, `DslEvaluator`, `GeoWeightCalculator`, `ScoreRepository`,
`ScoringEngine`). Declare Pydantic models `InputSnapshot`, `ScoreResult`, `ScoreQuery`.
Declare exceptions: `DslParseError(ValueError)`, `DslEvalError(RuntimeError)`,
`HashMismatchNotice`, `InsufficientDataError(RuntimeError)`.

No business logic in this task — interfaces only.

**Acceptance criteria covered**: enables all ACs (shared contract foundation)

---

### TASK-004: inputs_hash Engine
**Complexity**: M | **TDD**: true
**Files**:
- `src/scoring/hash_engine.py`
- `tests/unit/scoring/test_hash_engine.py`

Implement `ConcreteHashEngine` satisfying the `HashEngine` Protocol.

`compute(snapshot)`: serialise `snapshot.raw_inputs` as a stable JSON string
(keys sorted, floats rounded to 8 significant figures to avoid FP drift),
then return `hashlib.sha256(json_str.encode()).hexdigest()`.

`has_changed(snapshot, stored_hash)`: returns `compute(snapshot) != stored_hash`.

**Tests to write first (TDD)**:
- `test_same_inputs_produce_identical_hash` — two `InputSnapshot` objects with
  identical raw_inputs yield the same hex digest.
- `test_mutated_input_changes_hash` — changing one field in raw_inputs produces
  a different digest.
- `test_key_order_does_not_affect_hash` — raw_inputs dicts with same keys in
  different orders produce the same digest.
- `test_has_changed_returns_false_when_match` — `has_changed` returns False
  when stored hash equals fresh hash.
- `test_has_changed_returns_true_after_mutation` — `has_changed` returns True
  after any input mutation.
- `test_float_precision_stability` — inputs differing only in floating-point
  noise below 8 significant figures hash identically.

**Acceptance criteria covered**: AC-001

---

### TASK-005: DSL AST Nodes and Parser
**Complexity**: L | **TDD**: true
**Files**:
- `src/scoring/dsl/ast_nodes.py`
- `src/scoring/dsl/parser.py`
- `tests/unit/scoring/dsl/test_parser.py`

Implement frozen dataclass AST node hierarchy (`Literal_`, `IdentifierRef`,
`BinaryOp`, `FunctionCall`) as specified in the Interfaces section.

Implement a recursive-descent `DslParser` class:
- `parse(expression: str) -> Expr` — public entry point.
- Internal methods: `parse_expr`, `parse_term`, `parse_factor`, `parse_unary`,
  `parse_primary` following operator-precedence grammar (exponentiation highest,
  then mul/div, then add/sub, then function calls parsed left-to-right).
- Raises `DslParseError` with a human-readable message on invalid syntax.
- No external parser library dependency — pure Python recursive descent.

**Tests to write first (TDD)**:
- `test_parse_literal_integer` — `"42"` → `Literal_(value=42.0)`.
- `test_parse_arithmetic_precedence` — `"2 + 3 * 4"` → AST reflecting `2 + (3 * 4)`.
- `test_parse_power_operator` — `"x ^ 2"` → `BinaryOp(op="^", left=IdentifierRef("x"), right=Literal_(2.0))`.
- `test_parse_function_call_no_args_raises` — `"RANK_SECTOR()"` raises `DslParseError`.
- `test_parse_nested_function_call` — `"ZSCORE(CHANGE(price, 30), sector)"` produces
  a nested `FunctionCall` AST.
- `test_parse_if_ternary` — `"IF(x > 0, x, 0)"` produces the correct `FunctionCall` node.
- `test_parse_identifier` — `"revenue_growth"` → `IdentifierRef("revenue_growth")`.
- `test_parse_invalid_expression_raises_dsl_parse_error` — malformed input raises `DslParseError`.

**Acceptance criteria covered**: AC-002 (parser is prerequisite for evaluator)

---

### TASK-006: DSL Operator Implementations
**Complexity**: M | **TDD**: true
**Files**:
- `src/scoring/dsl/operators/arithmetic.py`
- `src/scoring/dsl/operators/logical.py`
- `src/scoring/dsl/operators/ranking.py`
- `src/scoring/dsl/operators/timeseries.py`
- `tests/unit/scoring/dsl/operators/test_arithmetic.py`
- `tests/unit/scoring/dsl/operators/test_logical.py`
- `tests/unit/scoring/dsl/operators/test_ranking.py`
- `tests/unit/scoring/dsl/operators/test_timeseries.py`

Implement each operator family as a callable registry entry. Each operator function
receives resolved argument values (already evaluated sub-expressions) as `float` or
`list[float]` depending on arity. Operators must not access the DB or any external
resource — they are pure functions of their arguments.

**Arithmetic** (`+`, `-`, `*`, `/`, `^`): standard operations; division by zero raises
`DslEvalError`.

**Logical** (`AND`, `OR`, `IF`):
- `AND(*args)` → `1.0` if all args non-zero else `0.0`.
- `OR(*args)` → `1.0` if any arg non-zero else `0.0`.
- `IF(condition, then_val, else_val)` → `then_val` if condition != 0.0 else `else_val`.

**Ranking** (`RANK_SECTOR(value, peer_values)`, `PERCENTILE(value, peer_values)`):
- `RANK_SECTOR` → rank of `value` among `peer_values` (1-based, ascending), as a float.
- `PERCENTILE` → percentile of `value` in `peer_values` distribution ∈ [0.0, 100.0].

**Time-series** (`CHANGE`, `CAGR`, `CORR`, `ZSCORE`):
- `CHANGE(series, periods)` → `(series[-1] - series[-periods]) / series[-periods]` (relative change).
- `CAGR(series, years)` → `(series[-1] / series[0]) ^ (1.0 / years) - 1.0`.
- `CORR(series_a, series_b)` → Pearson correlation coefficient ∈ [-1.0, 1.0].
- `ZSCORE(series)` → z-score of the last value: `(series[-1] - mean(series)) / std(series)`; raises `DslEvalError` if std == 0.

All raise `DslEvalError` on insufficient data (e.g. series shorter than required window).

**Tests to write first (TDD)** — representative:
- Each arithmetic operation with expected result.
- `test_division_by_zero_raises_dsl_eval_error`.
- `test_if_truthy_branch`, `test_if_falsy_branch`.
- `test_rank_sector_known_dataset` — value 3.0 among [1, 2, 3, 4, 5] → rank 3.
- `test_percentile_known_dataset` — value 50 in [0…100] → 50th percentile.
- `test_zscore_known_values` — series [2,4,4,4,5,5,7,9] last element z-score = 1.5.
- `test_zscore_zero_std_raises`.
- `test_change_correct_delta`, `test_cagr_known_values`, `test_corr_perfect_correlation`.

**Acceptance criteria covered**: AC-002

---

### TASK-007: DSL Evaluator (Recursive AST Interpreter)
**Complexity**: XL | **TDD**: true
**Files**:
- `src/scoring/dsl/evaluator.py`
- `tests/unit/scoring/dsl/test_evaluator.py`

Implement `ConcreteDslEvaluator` satisfying the `DslEvaluator` Protocol. This is
the highest-complexity component; treat it as a recursive AST interpreter.

`evaluate(dsl_expression: str, context: dict[str, float]) -> float`:
1. Parse `dsl_expression` via `DslParser.parse()` to obtain an `Expr` AST.
2. Recursively evaluate the AST via `_eval(node, context)`:
   - `Literal_` → return `node.value`.
   - `IdentifierRef` → look up `context[node.name]`; raise `DslEvalError` if missing.
   - `BinaryOp` → evaluate both operands recursively, then apply arithmetic operator from registry.
   - `FunctionCall` → evaluate all args recursively, then dispatch to the correct
     operator registry (arithmetic / logical / ranking / time-series) by function name.
3. Raises `DslParseError` on bad syntax (propagated from parser).
4. Raises `DslEvalError` on evaluation failure (missing context key, division by zero, etc.).
5. No mutable state — each `evaluate()` call is independent and thread-safe.

Design note: operator dispatch uses a registry dict `{name: callable}` populated at
module import time from the four operator modules. Adding a new operator requires
only a new entry in the registry — no changes to `evaluator.py` (OCP).

**Tests to write first (TDD)**:
- `test_evaluate_constant_expression` — `"42"` with empty context → `42.0`.
- `test_evaluate_identifier_lookup` — `"revenue_growth"` with context `{"revenue_growth": 0.15}` → `0.15`.
- `test_evaluate_arithmetic_expression` — `"price * pe_ratio"` with context → correct product.
- `test_evaluate_nested_operators` — `"ZSCORE(CHANGE(price_series, 30), ...)"` using a populated context produces expected float.
- `test_evaluate_rank_sector_in_expression` — DSL mixing RANK_SECTOR with arithmetic resolves correctly.
- `test_evaluate_unknown_identifier_raises_dsl_eval_error`.
- `test_evaluate_unknown_function_raises_dsl_eval_error`.
- `test_evaluate_matches_reference_implementation` — for a known DSL string (RANK_SECTOR + ZSCORE combination from AC-002), verify evaluator output matches a manually computed reference value with the same input dataset.
- `test_evaluate_is_thread_safe` — concurrent calls with different contexts produce independent correct results.

**Acceptance criteria covered**: AC-002

---

### TASK-008: GeoWeight Calculator
**Complexity**: M | **TDD**: true
**Files**:
- `src/scoring/geo_weight.py`
- `tests/unit/scoring/test_geo_weight.py`

Implement `ConcreteGeoWeightCalculator` satisfying the `GeoWeightCalculator` Protocol.

`calculate(company_id, tenant_id) -> float`:
1. Query active geopolitical events for the company's geographic region via the
   `get_recent_events` tool (injected dependency — never raw DB access).
2. For each active event, retrieve `event.intensity` (1–5) and
   `event.exposure_fraction` (0.0–1.0) from the event's company-exposure mapping.
3. Compute: `raw = 1.0 + sum(e.intensity * e.exposure_fraction for e in active_events)`.
4. Retrieve `geo_weight_cap` from `MarketConfig` for the company's market.
5. Return `min(raw, geo_weight_cap)`.
6. Returns `1.0` when there are no active events (no DB query side effects).

Constructor receives: `event_tool` (injected `get_recent_events` tool adapter),
`market_registry` (injected `MarketRegistry`). Never imports the tool directly
(Dependency Inversion).

**Tests to write first (TDD)**:
- `test_returns_1_when_no_active_events` — empty event list → `1.0`.
- `test_single_event_computes_correct_weight` — one event with intensity=3, exposure=0.5 → `1.0 + 3*0.5 = 2.5`, capped at 2.0 → `2.0`.
- `test_multiple_events_sum_correctly` — two events; verify additive formula.
- `test_cap_is_respected` — high-intensity stacked events never exceed `geo_weight_cap`.
- `test_cap_is_market_specific` — two companies in markets with different caps produce different geo_weights for the same event set.
- `test_exposure_fraction_zero_contributes_nothing` — event with exposure_fraction=0.0 does not raise raw above 1.0.

**Acceptance criteria covered**: AC-004

---

### TASK-009: ScoreRepository
**Complexity**: M | **TDD**: true
**Files**:
- `src/scoring/repository.py`
- `tests/integration/scoring/test_score_repository.py`

Implement `ConcreteScoreRepository` satisfying the `ScoreRepository` Protocol.
Uses SQLAlchemy 2 async session (injected).

`append(result: ScoreResult) -> None`:
- INSERT a new row into `score_records`. Never UPDATE. Never DELETE.
- Raises `RuntimeError` if insert fails due to constraint violation.

`get_latest(query: ScoreQuery) -> list[ScoreResult]`:
- SELECT with filters: `tenant_id` (always required), optional `company_ids`,
  optional `indicator_id`, optional `computed_at_from/to`.
- ORDER BY `computed_at DESC`.
- LIMIT `min(query.limit, 50)` — hard ceiling; never returns more than 50 rows.
- Returns `[]` if no results.

`get_stored_hash(company_id, indicator_id, tenant_id) -> str | None`:
- SELECT the `inputs_hash` from the most recent `score_records` row for the
  given company × indicator × tenant combination.
- Returns `None` if no prior record exists (first-time computation).

**Tests to write first (TDD)** (integration against a real test DB):
- `test_append_inserts_new_row` — after `append`, `get_latest` returns the record.
- `test_append_is_immutable` — calling `append` twice with same company/indicator creates two rows; no upsert.
- `test_get_latest_respects_50_row_cap` — insert 60 records; `get_latest` returns at most 50.
- `test_get_latest_is_tenant_scoped` — records from tenant A are not returned for tenant B.
- `test_get_stored_hash_returns_none_for_new_company` — no prior record → None.
- `test_get_stored_hash_returns_most_recent_hash` — after two appends, returns hash from latest row.

**Acceptance criteria covered**: AC-005, AC-006

---

### TASK-010: ScoringPipeline Orchestrator
**Complexity**: L | **TDD**: true
**Files**:
- `src/scoring/pipeline.py`
- `tests/unit/scoring/test_pipeline.py`
- `tests/integration/scoring/test_pipeline_integration.py`

Implement `ConcreteScoringPipeline` satisfying the `ScoringEngine` Protocol.

`recompute_if_stale(snapshot, indicator_version_id, dsl_expression, tenant_id)`:
1. Call `hash_engine.compute(snapshot)` → `new_hash`.
2. Call `repo.get_stored_hash(snapshot.company_id, snapshot.indicator_id, tenant_id)`.
3. If `new_hash == stored_hash` → return `None` (no-op; AC-001 invariant).
4. Build `context: dict[str, float]` from `snapshot.raw_inputs`.
5. Call `dsl_evaluator.evaluate(dsl_expression, context)` → `dsl_score`.
6. Call `geo_weight_calculator.calculate(snapshot.company_id, tenant_id)` → `geo_weight`.
7. Compute `final_score = dsl_score * geo_weight`.
8. Build `ScoreResult` with all provenance fields populated.
9. Call `repo.append(result)`.
10. Return `result`.

Constructor receives all four collaborators as injected dependencies
(`HashEngine`, `DslEvaluator`, `GeoWeightCalculator`, `ScoreRepository`).
No direct instantiation of collaborators inside the pipeline (DIP).

**Tests to write first (TDD)**:
- `test_no_recompute_when_hash_unchanged` — mock repo returns matching hash;
  verify `repo.append` is never called and result is `None`.
- `test_recomputes_when_hash_changes` — mock repo returns different hash;
  verify evaluator and appender are each called exactly once.
- `test_result_carries_correct_provenance` — returned `ScoreResult` has correct
  `inputs_hash`, `indicator_version_id`, `computed_at` (non-null), `tenant_id`.
- `test_geo_weight_applied_to_score` — mock evaluator returns 1.0, mock
  geo_weight_calculator returns 1.5; verify `result.score == 1.5` and
  `result.geo_weight_applied == 1.5`.
- `test_dsl_eval_error_propagates` — mock evaluator raises `DslEvalError`;
  pipeline propagates without catching.
- `test_pipeline_integration_end_to_end` (integration test) — provide a real
  DSL expression with RANK_SECTOR + ZSCORE, a real input snapshot, no prior
  record in test DB; assert a score record appears in the DB with full provenance.

**Acceptance criteria covered**: AC-001, AC-002, AC-004, AC-005

---

### TASK-011: Market-Scoped Scoring and MarketConfig Integration
**Complexity**: M | **TDD**: true
**Files**:
- `src/scoring/pipeline.py` (extend — no new file)
- `src/markets/config.py` (extend — TASK-002 prerequisite)
- `tests/unit/scoring/test_market_config_integration.py`
- `tests/integration/scoring/test_new_market_acceptance.py`

Extend `ConcreteScoringPipeline` to accept an `InputSnapshot` for any market
registered in `MarketRegistry`. The pipeline must not contain any market-specific
branching logic — market identity is used only to look up the `MarketConfig` for
the `geo_weight_cap` (already handled in `GeoWeightCalculator`) and to validate
that the market is `active`.

Add a `market_registry` parameter to the pipeline constructor. In `recompute_if_stale`,
before computing, resolve the company's market via `market_registry.get_market(company_id)`
and raise `ValueError` if the market is inactive.

Write a test market fixture (`MARKET_TEST_CONFIG`) and verify the full score pipeline
accepts it without any scoring, alert, AI, or map code changes.

**Tests to write first (TDD)**:
- `test_scoring_accepts_new_market_config_without_code_change` — add `MARKET_TEST_CONFIG`
  to the test registry; run the pipeline; assert a `ScoreResult` is returned.
- `test_inactive_market_raises_value_error` — market with `active=False` → pipeline
  raises `ValueError` before any computation.
- `test_different_markets_use_their_own_geo_weight_cap` — two companies in markets with
  different `geo_weight_cap` values produce different final scores given the same
  active events.

**Acceptance criteria covered**: AC-003

---

### TASK-012: Tool Library Integration — get_event_exposure_score
**Complexity**: M | **TDD**: true
**Files**:
- `src/workflows/tools/score_tool.py`
- `src/workflows/tools/__init__.py`
- `tests/unit/workflows/tools/test_score_tool.py`

Implement `GetEventExposureScoreTool` as a typed Tool Library entry.

Input: `GetEventExposureScoreInput` (as specified in Interfaces section).
Output: `GetEventExposureScoreOutput` (as specified).

The tool:
1. Validates `tenant_id` is present (rejects cross-tenant access).
2. Enforces `limit = min(input.limit, 50)` — never passes a limit > 50 to the repository.
3. Sets `output.truncated = True` when the backing query would have returned more rows
   (detected via a count-check or LIMIT+1 sentinel query).
4. Raises `ToolNotApplicable` if `tenant_id` does not match the calling agent's tenant context.
5. Raises `InsufficientData` if no score records exist for the query parameters.
6. Is a read-only tool — never mutates `score_records`.

Register in `src/workflows/tools/__init__.py` alongside existing tools.

**Tests to write first (TDD)**:
- `test_output_is_pydantic_typed` — tool output is an instance of `GetEventExposureScoreOutput`.
- `test_limit_hard_capped_at_50` — passing `limit=100` to the tool results in at most 50 rows.
- `test_truncated_flag_set_when_results_exceed_limit` — mock repo returns 51 results;
  `output.truncated == True` and `len(output.scores) == 50`.
- `test_cross_tenant_access_raises_tool_not_applicable` — `tenant_id` mismatch raises `ToolNotApplicable`.
- `test_empty_result_raises_insufficient_data`.
- `test_scores_list_contains_score_result_instances` — each item is a `ScoreResult`.

**Acceptance criteria covered**: AC-006

---

### TASK-013: Integration Test — End-to-End Hash Invalidation → Recomputation → Persistence
**Complexity**: M | **TDD**: true
**Files**:
- `tests/integration/scoring/test_hash_invalidation_e2e.py`

Write a focused integration test suite that exercises the full flow:

1. Seed a company with an indicator and an initial `InputSnapshot` → call pipeline →
   assert `ScoreResult` returned and persisted.
2. Call pipeline again with the **same** snapshot → assert `None` returned and no new DB row.
3. Mutate one field in `raw_inputs` → call pipeline again → assert a **new** `ScoreResult`
   returned, new row in DB with updated `inputs_hash`, unchanged rows from prior runs
   still present (append-only).
4. Verify the persisted `ScoreResult` contains `indicator_version_id`, `inputs_hash`,
   `computed_at` (AC-005).

Use a real test PostgreSQL instance (pytest fixture with `testcontainers` or
project-standard test DB container).

**Tests to write first (TDD)**: the four scenarios above are the tests.

**Acceptance criteria covered**: AC-001, AC-005

---

### TASK-014: Wire ScoringPipeline into Mode A Step 7
**Complexity**: S | **TDD**: false
**Files**:
- `src/event_pipeline/score/__init__.py` or existing step-7 module

Wire `ConcreteScoringPipeline` into the Mode A pipeline at step 7 (EXPOSURE SCORE).
The event pipeline calls `scoring_engine.recompute_if_stale(...)` for each
portfolio holding affected by the incoming event, using the current `InputSnapshot`
derived from the event's company data.

No new logic — this is wiring only. The event pipeline constructs the snapshot and
delegates fully to the scoring engine's public interface. If the engine returns `None`
(hash unchanged), the pipeline continues without appending a new score.

**Acceptance criteria covered**: AC-001, AC-004 (full Mode A flow with geo_weight)

---

## Acceptance Criteria Coverage

| AC | Description | Covered by |
|----|-------------|-----------|
| AC-001 | inputs_hash mismatch triggers recomputation of exactly affected scores; unchanged scores are skipped | TASK-004, TASK-010, TASK-013, TASK-014 |
| AC-002 | DSL indicator with RANK_SECTOR and ZSCORE evaluates correctly against a reference dataset | TASK-005, TASK-006, TASK-007, TASK-010 |
| AC-003 | New MarketConfig entry scores companies in that market with zero changes to scoring, alert, AI, or map code | TASK-002, TASK-011 |
| AC-004 | geo_weight modifier is recalculated and applied after a live event updates the exposure map | TASK-008, TASK-010, TASK-011, TASK-014 |
| AC-005 | Score record includes indicator_version_id, inputs_hash, and computed_at | TASK-001, TASK-009, TASK-010, TASK-013 |
| AC-006 | Tool Library read tool returns at most 50 rows, is Pydantic-typed, tenant-scoped | TASK-009, TASK-012 |

## Definition of Done

- [ ] All 14 tasks complete
- [ ] Unit tests passing — service/logic layer >= 80% line coverage
- [ ] Integration tests passing: hash invalidation flow, repository, pipeline end-to-end
- [ ] All 6 acceptance criteria verified by their respective test suites
- [ ] DSL evaluator tested against reference implementation for RANK_SECTOR + ZSCORE combination (AC-002)
- [ ] No TODO/FIXME in produced code
- [ ] `score_records` TimescaleDB hypertable migration verified on local Docker Compose stack
- [ ] `GetEventExposureScoreTool` registered and discoverable by agent tool resolution
- [ ] dev-code-review run and all Critical/High findings resolved
- [ ] PLAN-F-002 (provider abstraction) confirmed deployed in target environment before executing TASK-010+

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | What is the `geo_weight` modifier formula? | Resolved (OQ-1): `geo_weight = min(1.0 + Σ(event.intensity × event.exposure_fraction), cap)`. Cap defaults to 2.0, stored as `geo_weight_cap` in `MarketConfig`. Implemented in TASK-008. |
| 2 | Is score history a snapshot approach or full append-only table? | Resolved (OQ-2): Full append-only `score_records` table. Every recomputation appends a new row. Historical mode queries by `computed_at` range. Implemented in TASK-001, TASK-009. |

## Risks and Notes

- **DSL Evaluator complexity**: The recursive AST interpreter (TASK-007) is the highest-risk
  component. It must handle operator precedence correctly under all nesting depths. TDD is
  mandatory — write tests for all operator combinations before implementation. The reference
  implementation test in `test_evaluate_matches_reference_implementation` is the critical
  regression anchor.

- **Float stability in hashing**: `inputs_hash` computation must round floats to 8 significant
  figures to prevent spurious recomputations from floating-point drift in price feeds. This is
  tested explicitly in TASK-004.

- **TimescaleDB hypertable creation**: `score_records` must be converted to a TimescaleDB
  hypertable via `SELECT create_hypertable('score_records', 'computed_at')` in the Alembic
  migration. This requires the TimescaleDB extension to be loaded. The migration must fail
  gracefully if the extension is absent (raise a clear error, not a silent no-op).

- **PLAN-F-002 hard dependency**: `ConcreteScoringPipeline` (TASK-010) and `GeoWeightCalculator`
  (TASK-008) both consume provider data through the Tool Library. PLAN-F-002 must be deployed
  before integration testing of these tasks begins. Development of TASK-001 through TASK-009
  can proceed in parallel since those tasks use mock dependencies.

- **Thread safety of DSL evaluator**: Each `evaluate()` call must be stateless. If the operator
  registry is a module-level dict it is read-only after import, which is thread-safe. Verify
  no mutable shared state in operator implementations.

- **geo_weight and cache freshness**: `GeoWeightCalculator` queries active events via the
  `get_recent_events` tool. That tool is cache-first (P-02). For geo_weight to reflect a
  newly ingested Mode A event within the same session, the event pipeline (step 7) must
  invalidate or bypass the geo-events cache entry after writing the new event. Confirm with
  the Mode A pipeline owner; document the cache invalidation contract in TASK-014.

- **REQ-N-003 cost control**: The hash-gated recomputation (TASK-004, TASK-010) is the primary
  cost-control mechanism for this module — it prevents redundant DSL evaluation and provider
  fetches. Monitor recomputation rate in staging; if too many false-positives occur, investigate
  float rounding in `hash_engine.py`.
