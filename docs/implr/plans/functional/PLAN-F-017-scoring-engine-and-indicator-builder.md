---
plan_id: PLAN-F-017
slug: scoring-engine-and-indicator-builder
title: Scoring Engine and Indicator Builder
linked_requirement: REQ-F-017
type: functional
status: done
blocked_reason:
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-011, reason: "Computed scores use event-driven invalidation (no TTL); company_score rows written only on value change per D4" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-017 — Scoring Engine and Indicator Builder

## Linked Requirement
**REQ-F-017** — Scoring Engine and Indicator Builder
Status: approved | Jira:

## Objective

Build the analytical backbone that translates raw company fundamentals and geopolitical event exposure into normalized, geo-adjusted scores (0–100) visible on the Intelligence Map. This plan delivers: a standalone DSL parser and runtime evaluator for custom scoring formulas; a three-mode normalization pipeline (percentile, z-score, min-max); a geo-modifier that applies event-intensity × revenue-exposure to base scores; three built-in scoring profiles (Value Investor, Growth Hunter, Macro Aware) with user-extensible custom profiles; indicator versioning with DSL diff and rollback; an event-driven score invalidation and re-score trigger that targets only affected companies; and a React visual DSL editor with a live 5-company preview. All company_score writes follow the event-driven snapshot pattern (D4): a row is written only when the computed score differs from the current stored value, and TimescaleDB enforces a 2-year retention policy.

## Architecture Context

This plan operates entirely within Layer 4 (Processing) and Layer 5 (Serving) of the six-layer model, consuming Layer 3 (Storage) through the repository pattern.

The `scoring` backend module (ARCHITECTURE.md §5) is the sole home for all scoring business logic. It may depend on `storage` only; no other module imports are permitted. The `api` module exposes scoring endpoints to the frontend; the `events` module triggers score invalidation after `persist_event_record` (Mode A step 5) by publishing to the invalidation queue.

Key data entities (ARCHITECTURE.md §10): `indicator` table (formula storage, versioning), `company_score` TimescaleDB hypertable (event-driven snapshots, D4), and `ScoringProfile` (profile_id, name, indicators with weights, version).

The DSL parser must be a self-contained sub-module with zero business-logic dependencies — it produces an AST that the evaluator then walks. The evaluator receives company fundamentals through an injected `FundamentalsProvider` interface (Principle 1), never calling the DB or external APIs directly.

Frontend: The visual DSL editor lives under `src/frontend/components/indicator-builder/` and communicates with the backend via REST (`/api/v1/indicators`). TanStack Query manages server state (ARCHITECTURE.md §11).

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-011 | Computed scores: no TTL; event-driven invalidation | TASK-009 implements invalidation listener; TASK-010 implements the snapshot-write guard that skips DB write when score value is unchanged |
| REQ-N-004 | Morning Brief must complete within its 5-min / $2.00 budget | Score recomputation in `recompute_scores` node (Workflow 1) must be async-parallel per company and complete within the workflow budget; TASK-010 ensures batch re-score is bounded |

## Component Design

### New Components

```
Module: scoring  (src/scoring/)
  ├── dsl/
  │   ├── __init__.py
  │   ├── tokenizer.py          — Lexer: converts formula string → token stream
  │   ├── parser.py             — Recursive-descent parser: token stream → AST
  │   ├── ast_nodes.py          — Dataclasses for every AST node type
  │   └── validator.py          — Semantic validator: checks parameter names against catalog
  ├── evaluator/
  │   ├── __init__.py
  │   ├── interfaces.py         — IFundamentalsProvider, IParameterCatalog (protocols)
  │   ├── ast_evaluator.py      — AST walker that evaluates a formula against company data
  │   └── operator_registry.py  — Registered arithmetic/logical/ranking/time-series operators
  ├── normalization/
  │   ├── __init__.py
  │   ├── base.py               — Abstract NormalizationStrategy protocol
  │   ├── percentile.py         — Rank within peer group
  │   ├── z_score.py            — Standard score vs benchmark
  │   └── min_max.py            — Linear scale 0–100 within configured range
  ├── geo_modifier.py           — geo_revenue JSONB × event intensity → magnitude_adjustment
  ├── benchmark_engine.py       — Peer set / benchmark group management, feeds normalization
  ├── scoring_service.py        — Orchestrates: evaluate → normalize → geo-modify → snapshot
  ├── profile_service.py        — Scoring profile CRUD, weight aggregation, built-in profiles
  ├── indicator_service.py      — Indicator CRUD, version management, diff, rollback
  ├── invalidation_consumer.py  — Celery task: receives event_id, finds affected companies, enqueues re-score
  ├── repositories/
  │   ├── __init__.py
  │   ├── interfaces.py         — IIndicatorRepository, ICompanyScoreRepository, IScoringProfileRepository, IParameterCatalogRepository
  │   ├── indicator_repo.py     — SQLAlchemy async implementation for indicator + versions
  │   ├── company_score_repo.py — SQLAlchemy async implementation for company_score (TimescaleDB)
  │   ├── scoring_profile_repo.py
  │   └── parameter_catalog_repo.py
  └── schemas/
      ├── indicator.py          — Pydantic request/response DTOs
      ├── company_score.py
      └── scoring_profile.py

Module: api (src/api/v1/scoring/)
  ├── indicators.py             — Router: CRUD + validate + preview endpoints
  ├── scoring_profiles.py       — Router: profile CRUD, activate
  └── scores.py                 — Router: company score query, history

Module: frontend (src/frontend/)
  └── components/
      └── indicator-builder/
          ├── IndicatorBuilder.tsx        — Page container
          ├── ParameterPalette.tsx        — Left panel: browsable DSL parameter catalog
          ├── FormulaCanvas.tsx           — Center: textarea + real-time syntax validation
          ├── LivePreviewPanel.tsx        — Right panel: 5-sample company score preview
          ├── VersionHistoryDrawer.tsx    — Version list + DSL diff + rollback button
          └── hooks/
              ├── useFormulaValidation.ts — Debounced validation call to POST /validate
              └── useLivePreview.ts       — Debounced preview call to POST /preview
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/events/pipeline_executor.py` (or equivalent Mode A step 5 file) | After `persist_event_record` completes, publish `score_invalidation` message to Celery queue with `event_id` | Trigger event-driven score invalidation (AC-002) |
| `src/api/v1/__init__.py` | Register scoring and indicator routers | Expose scoring endpoints |
| `src/config/celery_app.py` | Register `invalidation_consumer` task | Wire Celery task |
| `src/frontend/App.tsx` or router config | Add `/indicator-builder` route | Mount DSL editor page |

### Interfaces and Contracts

```python
# src/scoring/evaluator/interfaces.py

from typing import Protocol
from uuid import UUID

class IFundamentalsProvider(Protocol):
    async def get_company_fundamentals(
        self, company_id: UUID, parameters: list[str]
    ) -> dict[str, float | None]: ...

class IParameterCatalog(Protocol):
    async def get_enabled_parameters(self, tenant_id: UUID) -> list[str]: ...
    async def get_parameter_definition(
        self, name: str, tenant_id: UUID
    ) -> dict | None: ...

# src/scoring/repositories/interfaces.py

from typing import Protocol
from uuid import UUID
from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.schemas.scoring_profile import ScoringProfileRecord

class IIndicatorRepository(Protocol):
    async def get_by_id(self, indicator_id: UUID, tenant_id: UUID) -> IndicatorRecord | None: ...
    async def list_by_tenant(self, tenant_id: UUID) -> list[IndicatorRecord]: ...
    async def save(self, record: IndicatorRecord) -> IndicatorRecord: ...
    async def get_version(self, indicator_id: UUID, version: int) -> IndicatorVersionRecord | None: ...
    async def list_versions(self, indicator_id: UUID) -> list[IndicatorVersionRecord]: ...

class ICompanyScoreRepository(Protocol):
    async def get_current(
        self, company_id: UUID, indicator_id: UUID
    ) -> CompanyScoreRecord | None: ...
    async def upsert_if_changed(self, record: CompanyScoreRecord) -> bool: ...
        # Returns True if a new row was written, False if score unchanged.
    async def get_history(
        self, company_id: UUID, indicator_id: UUID, limit: int = 90
    ) -> list[CompanyScoreRecord]: ...

class IScoringProfileRepository(Protocol):
    async def get_by_id(self, profile_id: UUID, tenant_id: UUID) -> ScoringProfileRecord | None: ...
    async def list_by_tenant(self, tenant_id: UUID) -> list[ScoringProfileRecord]: ...
    async def save(self, record: ScoringProfileRecord) -> ScoringProfileRecord: ...
```

## Implementation Tasks

### TASK-001: DSL tokenizer and AST node definitions · S/no-TDD · src/scoring/dsl/tokenizer.py,src/scoring/dsl/ast_nodes.py,src/scoring/dsl/__init__.py

Implement the lexer that converts a raw DSL formula string into an ordered token stream. Define all AST node dataclasses that the parser will produce.

**Token types to support:** number literals, string literals, identifiers (parameter names and function names), arithmetic operators (`+`, `-`, `*`, `/`, `^`), comparison operators (`>`, `<`, `>=`, `<=`, `==`, `!=`), logical operators (`AND`, `OR`, `NOT`), parentheses, commas, `[` `]` for time-series indexing, and EOF.

**AST node types:** `NumberLiteral`, `IdentifierNode`, `BinaryOp`, `UnaryOp`, `FunctionCall`, `TimeSeriesIndex`, `ConditionalExpr`. Each is a frozen `dataclass` carrying only the information the evaluator needs (no source-location data in v1).

The tokenizer raises `DslTokenizeError` (a subclass of `DslError`) on any unrecognized character. It is a pure function: `tokenize(formula: str) -> list[Token]`.

**AC covered**: AC-001 (prerequisite — tokenizer feeds parser)

---

### TASK-002: DSL recursive-descent parser · M/TDD · src/scoring/dsl/parser.py,tests/unit/scoring/dsl/test_parser.py

**Tests to write first (TDD):**
- Parses `revenue * 0.5 + net_income` into a BinaryOp tree with correct precedence
- Parses `IF(pe_ratio < 15, 1, 0)` into a ConditionalExpr node
- Parses `price[-1] / price[-5]` into TimeSeriesIndex nodes
- Parses `RANK(roe, peer_group="SP500")` into a FunctionCall node with keyword arg
- Raises `DslParseError` on unbalanced parentheses
- Raises `DslParseError` on two consecutive operators without an operand

Implement a hand-written recursive-descent parser: `parse(tokens: list[Token]) -> AstNode`. Operator precedence (lowest to highest): `OR`, `AND`, `NOT`, comparison, additive (`+`, `-`), multiplicative (`*`, `/`), exponentiation (`^`), unary minus, function calls and indexing.

The parser has no knowledge of parameter names — semantic validation is a separate step. It returns the root AST node on success and raises `DslParseError` on syntax error. Pure function, no I/O.

**AC covered**: AC-001

---

### TASK-003: DSL semantic validator · S/no-TDD · src/scoring/dsl/validator.py,tests/unit/scoring/dsl/test_validator.py

Walk the AST produced by the parser and verify that every `IdentifierNode` refers to a parameter or function name that exists in the catalog. Accepts an `IParameterCatalog` (injected). Returns a `ValidationResult` dataclass with a `valid: bool` and `errors: list[str]`.

The validator does not evaluate values — it only checks names. Built-in function names (`IF`, `RANK`, `ZSCORE`, `PERCENTILE`, `MIN`, `MAX`, `ABS`, `LOG`) are always valid without catalog lookup.

Used at two points: (1) the `POST /api/v1/indicators/validate` endpoint (synchronous, returns errors to the frontend canvas); (2) before saving a new indicator version.

**AC covered**: AC-001, AC-004

---

### TASK-004: AST evaluator with injected providers · M/TDD · src/scoring/evaluator/ast_evaluator.py,src/scoring/evaluator/operator_registry.py,src/scoring/evaluator/interfaces.py,tests/unit/scoring/evaluator/test_ast_evaluator.py

**Tests to write first (TDD):**
- Evaluates `revenue * 0.5` given `{"revenue": 1000.0}` → `500.0`
- Evaluates `IF(pe_ratio < 15, 1.0, 0.0)` given `{"pe_ratio": 12.0}` → `1.0`
- Evaluates `RANK(roe, peer_group="SP500")` via stub `IFundamentalsProvider` → float
- Evaluates `price[-1] / price[-5]` via stub provider returning time-series list → float
- Raises `DslEvalError` when a required parameter is `None` (missing data) and formula does not guard it with IF
- Returns `None` for the whole formula when any leaf returns `None` and `null_propagates=True`

Implement `AstEvaluator` class. Constructor receives `IFundamentalsProvider` and `IParameterCatalog`. Method: `async def evaluate(self, ast: AstNode, company_id: UUID, tenant_id: UUID) -> float | None`.

`OperatorRegistry` maps operator token strings and function names to typed callables. Time-series indexing (`price[-1]`) calls `provider.get_time_series(parameter, lookback_periods)`.

**AC covered**: AC-001, AC-005

---

### TASK-005: Normalization strategies (percentile, z-score, min-max) · M/TDD · src/scoring/normalization/base.py,src/scoring/normalization/percentile.py,src/scoring/normalization/z_score.py,src/scoring/normalization/min_max.py,tests/unit/scoring/normalization/test_normalization.py

**Tests to write first (TDD):**
- `PercentileNormalizer.normalize(value=75.0, peer_values=[50.0, 60.0, 70.0, 80.0, 90.0])` → 0.4 (40th percentile, index 1 of 5 values below)
- `ZScoreNormalizer.normalize(value=110.0, mean=100.0, std=10.0)` clipped to [0, 100] → 60.0 (z=1.0 → scaled)
- `MinMaxNormalizer.normalize(value=150.0, min_val=100.0, max_val=200.0)` → 50.0
- `direction=lower_better` inverts the normalized score: 0 becomes 100, 100 becomes 0
- All strategies return exactly 0.0 for values below min / at 0th percentile
- All strategies return exactly 100.0 for values above max / at 100th percentile

Define `NormalizationStrategy` as a `Protocol` with `def normalize(self, value: float, **kwargs: float) -> float`. Each concrete class takes its mode-specific parameters in its constructor (loaded from `indicator.normalization` JSONB). Direction inversion is applied as a post-step in a wrapper, not inside each strategy.

**AC covered**: AC-001

---

### TASK-006: Geo-modifier computation · M/TDD · src/scoring/geo_modifier.py,tests/unit/scoring/test_geo_modifier.py

**Tests to write first (TDD):**
- `GeoModifier.apply(base_score=80.0, geo_weight=0.0)` → `80.0` (no adjustment when weight is zero)
- `GeoModifier.apply(base_score=80.0, geo_weight=0.3, geo_revenue={"US": 0.6, "CN": 0.4}, event_regions=["CN"], event_intensity=4)` → value between 0 and 100, lower than 80 if event is negative (direction-aware)
- `GeoModifier.apply(...)` clamps result to [0, 100]
- Given `event_regions` not overlapping `geo_revenue` keys → `geo_adjusted == base_score` (zero exposure)

`GeoModifier` is a pure function class with no I/O dependencies. Signature:

```python
class GeoModifier:
    def apply(
        self,
        base_score: float,
        geo_weight: float,
        geo_revenue: dict[str, float],  # country_code → revenue_fraction (sums to ≤1)
        event_regions: list[str],
        event_intensity: int,           # 1–5
        event_sentiment: float,         # −1.0 to +1.0
    ) -> float:
        ...
```

Formula: `exposure_fraction = sum(geo_revenue.get(r, 0) for r in event_regions)`; `magnitude = exposure_fraction * event_intensity / 5 * event_sentiment * geo_weight`; `geo_adjusted = clamp(base_score * (1 + magnitude), 0, 100)`. The `company_score` row records both `score` (normalized, before geo) and `geo_adjusted`.

**AC covered**: AC-005

---

### TASK-007: Benchmark engine and peer set management · M/TDD · src/scoring/benchmark_engine.py,tests/unit/scoring/test_benchmark_engine.py

**Tests to write first (TDD):**
- `BenchmarkEngine.get_peer_values(indicator_id, peer_group="SP500", tenant_id)` returns list of floats from DB query via injected repository
- `BenchmarkEngine.compute_benchmark_stats(peer_values)` returns `BenchmarkStats(mean, std, min, max, p25, p50, p75, p90, p99)`
- Empty peer list raises `InsufficientPeerDataError`
- Peer list with one element raises `InsufficientPeerDataError`

`BenchmarkEngine` accepts `ICompanyScoreRepository` (to fetch peer raw_values) and `IIndicatorRepository`. It feeds the normalization strategies: percentile normalization needs the sorted peer values list; z-score normalization needs mean and std; min-max uses configured range from `indicator.normalization` JSONB.

**AC covered**: AC-001

---

### TASK-008: Indicator repository and versioning · M/TDD · src/scoring/repositories/indicator_repo.py,src/scoring/repositories/interfaces.py,src/scoring/schemas/indicator.py,tests/integration/scoring/test_indicator_repo.py

**Tests to write first (TDD):**
- Saving an indicator with no existing record creates version=1
- Saving the same indicator_id again with changed `formula_dsl` increments version to 2; both versions are queryable
- `get_version(indicator_id, version=1)` returns the original DSL string unchanged
- `list_versions(indicator_id)` returns both records in ascending version order
- Deleting a tenant's indicator does not delete the version history rows

`IndicatorVersionRecord` mirrors the `indicator` table columns plus a `diff_tokens: list[str]` computed field (populated at read time by comparing adjacent DSL token lists). The `diff_tokens` field enables the frontend diff view without additional API calls.

On every `save()` call: (1) read current max version for `indicator_id`; (2) insert a new row with `version = max_version + 1`; (3) the current version is the row with the highest `version` integer.

Uses SQLAlchemy 2.0 async session from the `storage` module's session factory. All queries include `tenant_id` in WHERE clause.

**AC covered**: AC-004

---

### TASK-009: Event-driven score invalidation consumer · M/TDD · src/scoring/invalidation_consumer.py,tests/unit/scoring/test_invalidation_consumer.py

**Tests to write first (TDD):**
- Given an `event_id` with `event_exposure` rows for companies [A, B], the consumer enqueues re-score tasks for A and B only — not company C
- Given `event_exposure` with zero rows for an event, no re-score tasks are enqueued
- Consumer is idempotent: processing the same `event_id` twice does not enqueue duplicate tasks (deduplicated by Celery task unique key)
- Consumer reads `geo_regions` from `geo_event` and passes them to the re-score task payload

`InvalidationConsumer` is a Celery task (`@app.task(name="scoring.invalidate_and_rescore")`). It accepts `event_id: str`. Steps: (1) fetch `event_exposure` rows for the event; (2) fetch `geo_event.geo_regions` and `intensity`; (3) for each affected `company_id`, enqueue a `scoring.rescore_company` task with `(company_id, indicator_ids_for_tenant, geo_event_context)`.

After `persist_event_record` (Mode A step 5), the pipeline calls `invalidation_consumer.delay(event_id=str(event.event_id))`.

**AC covered**: AC-002

---

### TASK-010: Company score repository and snapshot-write guard · M/TDD · src/scoring/repositories/company_score_repo.py,src/scoring/schemas/company_score.py,tests/integration/scoring/test_company_score_repo.py

**Tests to write first (TDD):**
- `upsert_if_changed` writes a new row when no existing row is present; returns `True`
- `upsert_if_changed` writes a new row when `score` differs by more than `SCORE_CHANGE_EPSILON` (default 0.001); returns `True`
- `upsert_if_changed` does NOT write a row when score is within epsilon of current; returns `False`
- `get_history(company_id, indicator_id, limit=5)` returns rows in descending `computed_at` order
- `inputs_hash` is stored and retrieved correctly (SHA-256 hex string of the raw_value + normalization params)

The `inputs_hash` (SHA-256 of a canonical JSON of raw inputs) allows callers to detect whether the underlying data changed even if the score rounds to the same value.

`CompanyScoreRecord` Pydantic schema maps 1:1 to `company_score` table columns: `company_id`, `indicator_id`, `score`, `raw_value`, `percentile`, `geo_adjusted`, `inputs_hash`, `computed_at`.

The TimescaleDB hypertable partitioning is on `computed_at`. The repository uses SQLAlchemy `INSERT ... ON CONFLICT DO NOTHING` with a check query first (read-then-write pattern to avoid unnecessary inserts).

**AC covered**: AC-002, AC-005

---

### TASK-011: Scoring service orchestrator · L/TDD · src/scoring/scoring_service.py,tests/unit/scoring/test_scoring_service.py

**Tests to write first (TDD):**
- `ScoringService.score_company(company_id, indicator_id, geo_event_context=None)` calls evaluator → normalizer → geo-modifier in that order and produces a `CompanyScoreRecord`
- When `geo_event_context` is None, `geo_adjusted == score` (no geo effect)
- When evaluator returns `None` (missing data), the service skips normalization and returns `None`; no DB write occurs
- `ScoringService.batch_rescore(company_ids, indicator_id, geo_event_context)` calls `score_company` for each and respects `upsert_if_changed` — verifiable via mock repository
- Benchmark stats are fetched once per batch (not per company)

`ScoringService` constructor receives: `AstEvaluator`, `BenchmarkEngine`, `GeoModifier`, `ICompanyScoreRepository`, `IIndicatorRepository`. It orchestrates the full scoring pipeline per company:

1. Load indicator (DSL + normalization params + geo_weight)
2. Parse DSL → AST (cached per indicator version)
3. Evaluate AST → `raw_value`
4. Fetch peer values from `BenchmarkEngine`
5. Select normalization strategy from `normalization` JSONB
6. Normalize `raw_value` → `score` (0–100), apply direction inversion
7. If `indicator.geo_weight > 0` and `geo_event_context` provided, apply `GeoModifier` → `geo_adjusted`
8. Compute `inputs_hash`
9. Call `ICompanyScoreRepository.upsert_if_changed`

**AC covered**: AC-001, AC-002, AC-005

---

### TASK-012: Indicator service — CRUD, versioning, diff, rollback · M/TDD · src/scoring/indicator_service.py,tests/unit/scoring/test_indicator_service.py

**Tests to write first (TDD):**
- `create_indicator(payload, tenant_id)` validates DSL via `DslValidator` before saving; returns `IndicatorRecord` with `version=1`
- `update_indicator(indicator_id, payload, tenant_id)` saves new version; `list_versions` returns 2 entries
- `get_diff(indicator_id, v1=1, v2=2)` returns `DiffResult(added_tokens, removed_tokens, unchanged_tokens)`
- `rollback(indicator_id, target_version=1, tenant_id)` creates a new version whose `formula_dsl` is identical to version 1's DSL
- `create_indicator` raises `DslValidationError` with error list when formula fails semantic validation

`IndicatorService` holds no HTTP concern — it is pure business logic. It wraps `IIndicatorRepository` and `DslValidator`. The diff algorithm tokenizes both DSL strings and applies a simple LCS-based diff (built-in `difflib.SequenceMatcher`) to find added and removed tokens.

**AC covered**: AC-001, AC-004

---

### TASK-013: Scoring profile service and built-in profiles · M/TDD · src/scoring/profile_service.py,src/scoring/repositories/scoring_profile_repo.py,src/scoring/schemas/scoring_profile.py,tests/unit/scoring/test_profile_service.py

**Tests to write first (TDD):**
- `ProfileService.get_profile(profile_id, tenant_id)` returns `ScoringProfileRecord` with `indicators` list
- `ProfileService.compute_composite_score(company_id, profile_id, tenant_id)` aggregates weighted `company_score` rows for each indicator in the profile; weights must sum to 1.0 (normalized if not exact)
- Switching profile for a tenant does not recompute scores — it reads existing `company_score` rows and aggregates
- Built-in profiles (VALUE_INVESTOR, GROWTH_HUNTER, MACRO_AWARE) are seeded on startup if absent for the tenant

Built-in profile indicator compositions are hard-coded as constants (parameter IDs resolved at seed time). `ScoringProfileRecord`: `profile_id`, `tenant_id`, `name`, `indicators: list[ProfileIndicatorWeight]`, `is_builtin: bool`, `version: int`.

**AC covered**: AC-003

---

### TASK-014: REST API — indicators and scoring profiles · M/TDD · src/api/v1/scoring/indicators.py,src/api/v1/scoring/scoring_profiles.py,src/api/v1/scoring/scores.py,tests/integration/api/scoring/test_indicators_api.py,tests/integration/api/scoring/test_profiles_api.py

**Tests to write first (TDD):**
- `POST /api/v1/indicators/validate` with a valid DSL → 200 `{valid: true, errors: []}`
- `POST /api/v1/indicators/validate` with invalid DSL → 200 `{valid: false, errors: ["Unknown parameter: foo"]}`
- `POST /api/v1/indicators` creates indicator version 1 → 201 with indicator_id
- `PUT /api/v1/indicators/{id}` with changed formula → 200 with `version=2`
- `GET /api/v1/indicators/{id}/versions` returns version list
- `POST /api/v1/indicators/{id}/rollback` with `target_version=1` → creates version 3 identical to v1
- `GET /api/v1/scoring-profiles` lists all profiles for tenant
- `POST /api/v1/indicators/preview` returns preview scores for 5 sample companies within 2 seconds (enforced by integration test timeout assertion)
- All endpoints return 401 without valid JWT; admin-only mutation endpoints return 403 for `end_user` role

Endpoints:
- `POST /api/v1/indicators/validate` — DSL syntax + semantic check, no DB write
- `POST /api/v1/indicators/preview` — evaluates formula against 5 fixed sample companies, returns `{company_id, raw_value, score}[]`
- `POST /api/v1/indicators` — create
- `PUT /api/v1/indicators/{id}` — update (creates new version)
- `GET /api/v1/indicators/{id}/versions` — version list with diff_tokens
- `POST /api/v1/indicators/{id}/rollback` — rollback to target version
- `GET /api/v1/scoring-profiles` — list
- `POST /api/v1/scoring-profiles` — create custom
- `DELETE /api/v1/scoring-profiles/{id}` — delete (built-ins protected)
- `GET /api/v1/scores/company/{id}` — current scores per indicator
- `GET /api/v1/scores/company/{id}/history` — score history for one indicator

**AC covered**: AC-001, AC-003, AC-004, AC-006

---

### TASK-015: DB migrations — indicator, company_score, scoring_profile, parameter_catalog tables · S/no-TDD · src/db/migrations/versions/017_scoring_engine.py

Write an Alembic migration that creates or alters the following tables:

- `indicator` — all columns from the data model; `(indicator_id, version)` unique constraint; index on `(tenant_id, indicator_id)`
- `indicator_version` — stores historical DSL snapshots mirroring `indicator` columns; FK to `indicator_id`; the current live version is the row with `max(version)` per `indicator_id` in the `indicator` table
- `company_score` — TimescaleDB hypertable (via `SELECT create_hypertable('company_score', 'computed_at')` after table creation); PK `(company_id, indicator_id, computed_at)`; retention policy: `SELECT add_retention_policy('company_score', INTERVAL '2 years')`
- `scoring_profile` — `profile_id`, `tenant_id`, `name`, `indicators JSONB`, `is_builtin BOOL DEFAULT false`, `version INT DEFAULT 1`, `created_at`; index on `tenant_id`
- `dsl_parameter` — `parameter_id`, `tenant_id`, `name`, `description`, `source_field`, `enabled BOOL DEFAULT true`, `created_at`; unique `(tenant_id, name)`

All tables include `tenant_id` column (multi-tenancy, Principle 3).

**AC covered**: AC-001, AC-004 (schema prerequisite)

---

### TASK-016: DSL parameter catalog — admin backend · S/no-TDD · src/scoring/repositories/parameter_catalog_repo.py,src/api/v1/scoring/parameter_catalog.py

Implement:
- `ParameterCatalogRepository` satisfying `IParameterCatalogRepository`: `list_enabled`, `add`, `enable`, `disable`
- REST endpoints under `/api/v1/admin/scoring/parameters` (admin role only):
  - `GET /` — list all parameters (enabled and disabled)
  - `POST /` — add new parameter
  - `PATCH /{name}/enable` — enable
  - `PATCH /{name}/disable` — disable

The catalog is the source of truth for the DSL semantic validator. On startup, seed a default set of standard fundamental parameters (revenue, net_income, pe_ratio, roe, debt_to_equity, price, eps) if the tenant catalog is empty.

**AC covered**: AC-001 (parameter catalog feeds validator which is part of AC-001 flow)

---

### TASK-017: Frontend — visual DSL editor · L/TDD · src/frontend/components/indicator-builder/IndicatorBuilder.tsx,src/frontend/components/indicator-builder/ParameterPalette.tsx,src/frontend/components/indicator-builder/FormulaCanvas.tsx,src/frontend/components/indicator-builder/LivePreviewPanel.tsx,src/frontend/components/indicator-builder/VersionHistoryDrawer.tsx,src/frontend/components/indicator-builder/hooks/useFormulaValidation.ts,src/frontend/components/indicator-builder/hooks/useLivePreview.ts

**Tests to write first (TDD):**
- `useFormulaValidation` calls `/validate` with 300ms debounce; does not call on empty string
- `useLivePreview` calls `/preview` with 500ms debounce and returns 5 company preview rows
- `FormulaCanvas` renders error annotations when `validationResult.errors` is non-empty
- `LivePreviewPanel` renders a loading spinner while the preview is in-flight and scores once data arrives
- `VersionHistoryDrawer` renders diff view showing green (added) and red (removed) DSL tokens

Three-panel layout:
- **Left — ParameterPalette**: Loads from `GET /api/v1/admin/scoring/parameters`. Each parameter is a draggable chip that can be dropped into FormulaCanvas. Groups by category (fundamentals, macro, geo).
- **Center — FormulaCanvas**: Textarea with inline validation error highlighting. Save button creates/updates the indicator. Syntax errors shown as inline red text below the canvas. Uses `useFormulaValidation` hook with 300ms debounce.
- **Right — LivePreviewPanel**: Shows a table with 5 fixed sample companies (seeded in the test dataset), their `raw_value`, `score`, and `geo_adjusted`. Updates within 500ms of formula stabilization (debounced). Uses `useLivePreview` hook.

Version history: drawer opened from the "History" button. Shows list of versions with `created_at` timestamp. Selecting two versions shows a side-by-side diff. Rollback button sends `POST /api/v1/indicators/{id}/rollback`.

Uses TanStack Query for server state. TypeScript strict mode. No `any` types.

**AC covered**: AC-004, AC-006

---

### TASK-018: Frontend — scoring profile switcher · S/no-TDD · src/frontend/components/scoring/ScoringProfileSelector.tsx,src/frontend/components/scoring/hooks/useActiveProfile.ts

Implement a dropdown/tab component that lists available scoring profiles (fetched from `GET /api/v1/scoring-profiles`). Selecting a profile:

1. Updates a React context (`ActiveProfileContext`) with the new `profile_id`
2. Invalidates all company score queries (TanStack Query `queryClient.invalidateQueries`)
3. Map coloring updates as company score data refreshes

The selector is mounted in the top navigation bar, visible from the Intelligence Map. Built-in profile names displayed as pill badges. Custom profiles listed below.

`useActiveProfile` hook: stores the selected `profile_id` in `localStorage` and restores it on page load.

**AC covered**: AC-003

---

### TASK-019: End-to-end integration test — full scoring flow · M/TDD · tests/integration/scoring/test_scoring_e2e.py

**Tests to write first (TDD):**
- Full pipeline: create indicator with DSL formula → evaluate against test company in DB → normalized score is between 0 and 100
- Geo-modifier integration: indicator with `geo_weight=0.5` + geo event context → `geo_adjusted != score`
- Invalidation flow: insert `event_exposure` row → trigger invalidation consumer → verify `company_score` row is updated (new `computed_at` timestamp)
- Version roundtrip: create → update → rollback → verify current DSL matches v1 DSL
- Profile composite score: create profile with 2 indicators (weights 0.6, 0.4) → compute composite → result is weighted average of individual scores

Uses a real test database (PostgreSQL with TimescaleDB). Fixtures create sample companies, fundamentals data, and geo_events. Tests are isolated via transactions rolled back after each test.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: DSL formula parsed, validated, evaluated → raw_value + normalized score (0–100) → TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-007, TASK-011, TASK-012, TASK-014, TASK-019
- AC-002: Geo event fires → only affected companies invalidated and re-scored → TASK-009, TASK-010, TASK-011, TASK-019
- AC-003: Profile switched → all map company scores update → TASK-013, TASK-014, TASK-018, TASK-019
- AC-004: Saving indicator with changed formula → new version, diff view → TASK-008, TASK-012, TASK-014, TASK-017, TASK-019
- AC-005: DSL formula with geo-modifier → raw_value + geo_adjusted stored → TASK-006, TASK-010, TASK-011, TASK-019
- AC-006: DSL editor live preview → 5 sample companies within 2 seconds → TASK-014, TASK-017

## Risks and Notes

- TimescaleDB hypertable creation must happen after the `company_score` table is created in the same migration transaction. If the TimescaleDB extension is not enabled in the PostgreSQL image, `create_hypertable` silently fails — add an assertion in the migration to verify extension presence.
- The DSL `RANK` and `PERCENTILE` operators require fetching all peer company raw_values in one query before scoring any single company. For a 200-company universe, this is a single SELECT returning at most 200 rows — acceptable. For larger universes, consider adding a `LIMIT` safety cap in `BenchmarkEngine`.
- `inputs_hash` (TASK-010) must use a deterministic canonical JSON serialization (sorted keys, fixed float precision) to prevent spurious hash mismatches from JSON key ordering.
- The 2-second live preview SLA (AC-006) requires the backend `/preview` endpoint to evaluate 5 companies in parallel using `asyncio.gather`, not sequentially.
- The geo-modifier formula uses `event_sentiment` (−1.0 to +1.0) from `geo_event`. Ensure that score direction (`higher_better` vs `lower_better`) is applied before the geo-modifier, not after, so that the geo-modifier always amplifies in the correct semantic direction.
- Rollback (TASK-012) creates a new version rather than overwriting the current formula. This preserves the full audit trail: version 1 → version 2 (edit) → version 3 (rollback to v1). Never mutate existing version rows.
- The built-in scoring profiles (TASK-013) reference indicator IDs that are tenant-specific. The seed process must resolve indicator names to IDs at seed time, not hard-code UUIDs.
</content>
</invoke>