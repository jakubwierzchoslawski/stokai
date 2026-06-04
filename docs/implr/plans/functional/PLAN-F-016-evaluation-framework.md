---
plan_id: PLAN-F-016
slug: evaluation-framework
title: Three-Tier Evaluation Framework
linked_requirement: REQ-F-016
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-009, reason: "Tier 2 regression gate is the hard CI block enforced before any prompt promotion" }
  - { id: REQ-N-010, reason: "Tier 3 daily calibration is the measurement mechanism for confidence-accuracy correlation" }
dependencies:
  - { id: PLAN-F-015, reason: "Tier 3 calibration reads recommendation_outcome rows populated by the Layer 1 episodic memory outcome-fill job" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-016 — Three-Tier Evaluation Framework

## Linked Requirement
**REQ-F-016** — Three-Tier Evaluation Framework
Status: approved | Jira:

## Objective

Build the three-tier evaluation system that runs from MVP Phase 4 onward. Tier 1 wires an `evaluate_quality` LangGraph node (Opus 4.7 judge, async, ~5 s) as the second-to-last node in every Mode B workflow and stores per-dimension scores as Langfuse evaluation objects. Tier 2 delivers a CI-integrated golden dataset regression runner that hard-blocks any prompt PR showing >5% degradation on any metric, plus admin tooling to create golden dataset items from AI override decisions. Tier 3 delivers a daily Celery job that joins `ai_recommendation` rows with actual price data from `recommendation_outcome`, computes `CORR(confidence, actual_t1d × direction_sign)` per action signal, stores `calibration_result` rows, and surfaces a 30-day admin dashboard. An admin API and three evaluator prompt files complete the implementation.

## Architecture Context

This plan lives at the intersection of three architecture sections.

**Section 9 (Evaluation Framework):** Defines all three tiers, judge model (Opus 4.7), >5% gate, `CORR` metric, and the continuous improvement loop that flows Tier 3 findings back through Tier 2 regression into the Tier 1 confirmation cycle.

**Section 8 (Prompt Management):** Tier 2 is a gate within the promotion pipeline — a prompt PR cannot advance from `staging` label to `canary` without a passing golden dataset run. The `prompts/evaluators/` layout is established here.

**Section 7 (Mode B Workflows):** Architecture §7.1 establishes the cross-workflow invariant: `evaluate_quality` is always the second-to-last node. This plan implements that node.

**Section 5 (Backend Module Map):** All evaluation logic lives in the `ai` module (`src/ai/evaluation/`). The `api` module adds admin evaluation endpoints. The `storage` module supplies the `calibration_result` repository. Celery beat (already configured by PLAN-F-015) provides the daily cron.

**Section 10 (Data Model):** Three new tables are introduced: `evaluation_result` (Tier 1 trace), `golden_dataset_item` (Tier 2 fixture), and `calibration_result` (Tier 3 outcome). The `recommendation_outcome` table (owned by PLAN-F-015) is read-only from this plan's perspective — Tier 3 reads `actual_t1d`, `actual_t1w`, and fills no new columns in it.

**Section 11 (Admin Panel — AI Audit Console):** The calibration dashboard and golden dataset approval UI are part of the Admin AI Audit Console. This plan delivers the backend API contracts; frontend integration is PLAN-F-029's scope.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-009 | >5% degradation on any single metric hard-blocks PR merge; rollback ≤60 s | TASK-006 implements the per-metric threshold check in the CI runner; TASK-007 implements the `stokai prompts rollback` command integrated with Langfuse label update |
| REQ-N-010 | CORR(confidence, actual_t1d × direction_sign) ≥ 0.3 over rolling 30-day window; warning flag if below threshold | TASK-010 computes and stores the CORR metric daily; TASK-011 implements the warning flag and 30-day rolling window logic surfaced in the calibration dashboard |

## Component Design

### New Components

```
Module: ai/evaluation  (src/ai/evaluation/)
  ├── interfaces/
  │   ├── i_tier1_judge.py             — ITier1Judge (abstract): evaluate_output() → EvaluationResult
  │   ├── i_tier2_runner.py            — ITier2Runner (abstract): run_regression() → RegressionReport
  │   ├── i_tier3_calibration.py       — ITier3Calibration (abstract): run_calibration() → CalibrationPassResult
  │   ├── i_evaluation_repository.py   — IEvaluationRepository (abstract)
  │   ├── i_golden_dataset_repository.py — IGoldenDatasetRepository (abstract)
  │   └── i_calibration_repository.py  — ICalibrationRepository (abstract)
  ├── repositories/
  │   ├── evaluation_repository.py     — EvaluationRepository: insert/query evaluation_result
  │   ├── golden_dataset_repository.py — GoldenDatasetRepository: CRUD golden_dataset_item
  │   └── calibration_repository.py    — CalibrationRepository: insert/query calibration_result
  ├── services/
  │   ├── tier1_judge_service.py       — Tier1JudgeService: calls Opus 4.7, maps response to EvaluationResult
  │   ├── tier2_runner_service.py      — Tier2RunnerService: runs golden dataset, computes per-metric delta
  │   ├── tier3_calibration_service.py — Tier3CalibrationService: queries recommendation_outcome, computes CORR
  │   └── golden_dataset_service.py    — GoldenDatasetService: add candidate, approve item
  ├── nodes/
  │   └── evaluate_quality_node.py     — LangGraph DeterministicNode/AgentNode wrapper; always second-to-last
  ├── models/
  │   ├── evaluation_models.py         — ORM: EvaluationResult
  │   ├── golden_dataset_models.py     — ORM: GoldenDatasetItem
  │   └── calibration_models.py        — ORM: CalibrationResult
  ├── schemas/
  │   ├── evaluation_schemas.py        — Pydantic: EvaluationResultCreate, EvaluationResult
  │   ├── golden_dataset_schemas.py    — Pydantic: GoldenDatasetItemCreate, GoldenDatasetItem, GoldenDatasetCandidate
  │   └── calibration_schemas.py       — Pydantic: CalibrationResultCreate, CalibrationResult, CalibrationPassResult
  ├── tasks/
  │   └── calibration_tasks.py         — Celery tasks: run_tier3_calibration (daily cron)
  └── __init__.py

Module: api/evaluation  (src/api/evaluation/)
  ├── evaluation_router.py             — FastAPI router: Tier 1 result query, golden dataset CRUD, calibration dashboard
  └── evaluation_api_schemas.py        — Request/response Pydantic models

Prompt files:
  prompts/evaluators/recommendation_judge.md
  prompts/evaluators/factuality_judge.md
  prompts/evaluators/calibration_judge.md

Alembic migrations:
  alembic/versions/XXXX_evaluation_result_table.py
  alembic/versions/XXXX_golden_dataset_item_table.py
  alembic/versions/XXXX_calibration_result_table.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/workflows/morning_brief.py` | Insert `evaluate_quality` node as second-to-last node | Architecture §7.1 cross-workflow invariant |
| `src/ai/workflows/on_demand_analysis.py` | Same `evaluate_quality` injection | Architecture §7.1 cross-workflow invariant |
| `src/ai/workflows/watchlist_scan.py` | Same `evaluate_quality` injection | Architecture §7.1 cross-workflow invariant |
| `src/ai/workflows/earnings_risk_brief.py` | Same `evaluate_quality` injection | Architecture §7.1 cross-workflow invariant |
| `src/ai/workflows/event_deep_dive.py` | Same `evaluate_quality` injection | Architecture §7.1 cross-workflow invariant |
| `src/config/celery_app.py` | Register `run_tier3_calibration` daily beat schedule (02:00 UTC) | Tier 3 daily cron requirement |

### Interfaces and Contracts

```python
# src/ai/evaluation/interfaces/i_tier1_judge.py

class ITier1Judge(ABC):
    @abstractmethod
    async def evaluate_output(
        self,
        run_id: UUID,
        agent_role: str,
        prompt_version: str,
        agent_input: dict,
        agent_output: dict,
        tool_outputs: list[dict],
    ) -> EvaluationResult: ...

# src/ai/evaluation/interfaces/i_evaluation_repository.py

class IEvaluationRepository(ABC):
    @abstractmethod
    async def insert_result(self, result: EvaluationResultCreate) -> EvaluationResult: ...
    @abstractmethod
    async def get_results_for_run(self, run_id: UUID) -> list[EvaluationResult]: ...
    @abstractmethod
    async def list_recent(self, limit: int = 100) -> list[EvaluationResult]: ...

# src/ai/evaluation/interfaces/i_golden_dataset_repository.py

class IGoldenDatasetRepository(ABC):
    @abstractmethod
    async def create_item(self, item: GoldenDatasetItemCreate) -> GoldenDatasetItem: ...
    @abstractmethod
    async def activate_item(self, item_id: UUID, approved_by: UUID) -> GoldenDatasetItem: ...
    @abstractmethod
    async def list_active(self) -> list[GoldenDatasetItem]: ...
    @abstractmethod
    async def list_candidates(self) -> list[GoldenDatasetItem]: ...
    @abstractmethod
    async def deactivate_item(self, item_id: UUID) -> None: ...

# src/ai/evaluation/interfaces/i_tier2_runner.py

class ITier2Runner(ABC):
    @abstractmethod
    async def run_regression(
        self,
        prompt_version_candidate: str,
        prompt_version_production: str,
        agent_role: str,
    ) -> RegressionReport: ...
    # RegressionReport.passed: bool
    # RegressionReport.per_metric_delta: dict[str, float]  # metric_name -> pct change (negative=degradation)
    # RegressionReport.breached_metrics: list[str]         # metrics with delta < -0.05

# src/ai/evaluation/interfaces/i_calibration_repository.py

class ICalibrationRepository(ABC):
    @abstractmethod
    async def insert_result(self, result: CalibrationResultCreate) -> CalibrationResult: ...
    @abstractmethod
    async def list_last_n_days(self, days: int, action_signal: str | None = None) -> list[CalibrationResult]: ...
    @abstractmethod
    async def get_rolling_corr(self, days: int = 30) -> float | None: ...

# src/ai/evaluation/interfaces/i_tier3_calibration.py

class ITier3Calibration(ABC):
    @abstractmethod
    async def run_calibration(self, reference_date: date) -> CalibrationPassResult: ...
    # CalibrationPassResult.date: date
    # CalibrationPassResult.rows_processed: int
    # CalibrationPassResult.corr_overall: float | None
    # CalibrationPassResult.per_signal: dict[str, CalibrationResult]
    # CalibrationPassResult.below_threshold: bool
```

## Implementation Tasks

### TASK-001: DB migrations — evaluation_result, golden_dataset_item, calibration_result tables · M/TDD · alembic/versions/XXXX_evaluation_result_table.py, alembic/versions/XXXX_golden_dataset_item_table.py, alembic/versions/XXXX_calibration_result_table.py

Create three tables.

`evaluation_result`: `eval_id UUID PK DEFAULT gen_random_uuid()`, `run_id UUID NOT NULL`, `eval_type VARCHAR NOT NULL DEFAULT 'tier_1'`, `judge_model VARCHAR NOT NULL`, `scores JSONB NOT NULL`, `overall_quality FLOAT NOT NULL CHECK(overall_quality BETWEEN 0 AND 1)`, `prompt_version VARCHAR NOT NULL`, `evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Index on `run_id`.

`golden_dataset_item`: `item_id UUID PK DEFAULT gen_random_uuid()`, `input JSONB NOT NULL`, `expected_output JSONB NOT NULL`, `quality_metrics JSONB NOT NULL`, `source VARCHAR NOT NULL CHECK(source IN ('hand_authored', 'admin_override'))`, `active BOOL NOT NULL DEFAULT FALSE`, `approved_by UUID NULL`, `approved_at TIMESTAMPTZ NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Partial index on `active = TRUE`.

`calibration_result`: `result_id UUID PK DEFAULT gen_random_uuid()`, `date DATE NOT NULL`, `action_signal VARCHAR NOT NULL`, `total_recommendations INT NOT NULL`, `direction_correct_pct FLOAT NOT NULL`, `corr_confidence_actual FLOAT`, `mean_confidence FLOAT NOT NULL`, `mean_actual_t1d FLOAT`, `computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`. Unique constraint on `(date, action_signal)` to prevent duplicate daily rows.

**Tests to write first (TDD)**:
- Test all three migrations apply cleanly and tables exist with correct columns and constraints.
- Test `evaluation_result.overall_quality` CHECK rejects values outside [0, 1].
- Test `golden_dataset_item.source` CHECK rejects unknown values.
- Test inserting a duplicate `(date, action_signal)` pair into `calibration_result` raises a unique constraint violation.
- Test inserting a `golden_dataset_item` with `active=FALSE` and `approved_by=NULL` succeeds (candidate state).

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-002: SQLAlchemy ORM models and Pydantic schemas — all three evaluation tables · S/no-TDD · src/ai/evaluation/models/evaluation_models.py, src/ai/evaluation/models/golden_dataset_models.py, src/ai/evaluation/models/calibration_models.py, src/ai/evaluation/schemas/evaluation_schemas.py, src/ai/evaluation/schemas/golden_dataset_schemas.py, src/ai/evaluation/schemas/calibration_schemas.py

Define SQLAlchemy 2.0 `DeclarativeBase` mapped classes: `EvaluationResult`, `GoldenDatasetItem`, `CalibrationResult`. Use `Mapped[]` typed annotations throughout. `scores` and `quality_metrics` map to `JSONB`. `GoldenDatasetItem.is_candidate` is a computed property: `active is False and approved_at is None`. `GoldenDatasetItem.is_active` is a computed property: `active is True`.

Define Pydantic v2 `BaseModel` classes for each domain: `EvaluationResultCreate`, `EvaluationResult`, `GoldenDatasetItemCreate`, `GoldenDatasetItem`, `GoldenDatasetCandidate` (response DTO for the pending-approval list), `CalibrationResultCreate`, `CalibrationResult`, `CalibrationPassResult`, `RegressionReport`.

`RegressionReport.passed: bool` derives from `all(delta >= -0.05 for delta in per_metric_delta.values())`.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-003: Repository implementations — IEvaluationRepository, IGoldenDatasetRepository, ICalibrationRepository · M/TDD · src/ai/evaluation/interfaces/i_evaluation_repository.py, src/ai/evaluation/interfaces/i_golden_dataset_repository.py, src/ai/evaluation/interfaces/i_calibration_repository.py, src/ai/evaluation/repositories/evaluation_repository.py, src/ai/evaluation/repositories/golden_dataset_repository.py, src/ai/evaluation/repositories/calibration_repository.py

Implement all three repository interfaces using SQLAlchemy 2.0 async sessions.

`EvaluationRepository.insert_result`: plain `INSERT`; returns the created row. `get_results_for_run`: `WHERE run_id = :run_id ORDER BY evaluated_at DESC`. `list_recent`: `ORDER BY evaluated_at DESC LIMIT :limit`.

`GoldenDatasetRepository.create_item`: inserts with `active=False`. `activate_item`: sets `active=True`, `approved_by`, `approved_at=NOW()`. `list_active`: `WHERE active = TRUE`. `list_candidates`: `WHERE active = FALSE AND approved_at IS NULL`. `deactivate_item`: sets `active=False`.

`CalibrationRepository.insert_result`: `INSERT ... ON CONFLICT (date, action_signal) DO UPDATE` — upsert to support re-runs. `list_last_n_days`: `WHERE date >= NOW() - INTERVAL ':days days'`. `get_rolling_corr`: `SELECT AVG(corr_confidence_actual) FROM calibration_result WHERE date >= NOW() - INTERVAL ':days days'` — uses PostgreSQL `CORR()` aggregate via a subquery if row counts permit.

**Tests to write first (TDD)**:
- Test `EvaluationRepository.insert_result` persists a row and returns it with `eval_id` populated.
- Test `get_results_for_run` returns all results for a given `run_id` in descending order.
- Test `GoldenDatasetRepository.create_item` creates with `active=False`.
- Test `activate_item` sets `active=True` and `approved_at IS NOT NULL`; item appears in `list_active`.
- Test `list_candidates` does not return activated items.
- Test `CalibrationRepository.insert_result` upserts: a second insert for same `(date, action_signal)` updates existing row rather than duplicating.
- Test `list_last_n_days` returns only rows within the date range.

**AC covered**: AC-001, AC-003, AC-004, AC-005

---

### TASK-004: Evaluator prompt files · S/no-TDD · prompts/evaluators/recommendation_judge.md, prompts/evaluators/factuality_judge.md, prompts/evaluators/calibration_judge.md

Write the three evaluator prompt files used by Tier 1 Opus 4.7 judge invocations.

`recommendation_judge.md`: system prompt instructing the judge to score output on four dimensions — factual grounding (are all claims traceable to provided tool outputs?), confidence calibration (does stated confidence match evidence quality?), internal consistency (are no contradictory claims made?), tool use appropriateness (were the right tools called for the stated conclusion?). Each dimension scored 0.0–1.0. Output format: JSON object `{"factual_grounding": float, "confidence_calibration": float, "internal_consistency": float, "tool_use_appropriateness": float, "overall_quality": float, "reasoning": string}`.

`factuality_judge.md`: focused prompt for factual accuracy of named-entity claims (company names, ticker symbols, geopolitical facts). Outputs `{"factual_accuracy": float, "unsupported_claims": [string], "overall_quality": float, "reasoning": string}`.

`calibration_judge.md`: prompt assessing whether the confidence score stated in an `ai_recommendation` is consistent with the evidence presented (sample size, analogy count, data completeness). Outputs `{"calibration_score": float, "evidence_sufficiency": float, "overall_quality": float, "reasoning": string}`.

Each file follows the `prompts/` hybrid model: versioned in git, published to Langfuse on CI merge with the git SHA as the Langfuse version label.

**AC covered**: AC-001

---

### TASK-005: Tier1JudgeService and evaluate_quality LangGraph node · M/TDD · src/ai/evaluation/services/tier1_judge_service.py, src/ai/evaluation/interfaces/i_tier1_judge.py, src/ai/evaluation/nodes/evaluate_quality_node.py

Implement `Tier1JudgeService.evaluate_output()`:
1. Load the `recommendation_judge.md` prompt from Langfuse (label `production`) via the prompt loader established by the `ai` module.
2. Construct the judge payload: include `agent_input`, `agent_output`, and `tool_outputs` (bounded to 50 tool result summaries to avoid context blowup).
3. Invoke Opus 4.7 asynchronously with `max_output_tokens=500`.
4. Parse the JSON response into an `EvaluationResult` schema.
5. Call `IEvaluationRepository.insert_result` to persist.
6. Post the scores to Langfuse as evaluation scores linked to `run_id` via the Langfuse `score` API.
7. Return the `EvaluationResult`.

`evaluate_quality_node.py` wraps `Tier1JudgeService` as a LangGraph `DeterministicNode`-compatible callable `(WorkflowState) -> WorkflowState`. It sets `state.confidence_scores["tier1_eval"] = result.overall_quality`. It runs fire-and-forget relative to the main workflow path — the node awaits the Langfuse score write but does not block the downstream `Narrative Writer` node. If the judge call fails (timeout or parse error), the node logs a warning and continues — Tier 1 is observability, not a hard gate.

**Tests to write first (TDD)**:
- Test `evaluate_output` with a mock Langfuse prompt loader and a mock Anthropic client returning valid JSON: assert `EvaluationResult` fields are populated and `insert_result` is called once.
- Test that a malformed JSON response from the judge results in a warning log and a fallback `EvaluationResult` with `overall_quality=0.0` (graceful degradation, not an exception).
- Test that `tool_outputs` longer than 50 items is truncated to 50 before building the judge payload.
- Test `evaluate_quality_node` with a minimal `WorkflowState`: assert `state.confidence_scores["tier1_eval"]` is set after the node runs.
- Test that `evaluate_quality_node` catches a `Tier1JudgeService` exception and does not raise — the workflow state is returned unchanged except for a warning entry.

**AC covered**: AC-001

---

### TASK-006: Inject evaluate_quality node into all five Mode B workflows · M/TDD · src/ai/workflows/morning_brief.py, src/ai/workflows/on_demand_analysis.py, src/ai/workflows/watchlist_scan.py, src/ai/workflows/earnings_risk_brief.py, src/ai/workflows/event_deep_dive.py

For each of the five LangGraph workflow graphs, insert the `evaluate_quality_node` as the second-to-last node — immediately before `narrative_writer`. The graph topology must satisfy: `... → evaluate_quality → narrative_writer → [HIL branch or dispatch]`. No other position is permitted (Architecture §7.1).

This is a structural modification of each workflow graph definition: add the node registration and the edge from the last analytical node to `evaluate_quality`, and from `evaluate_quality` to `narrative_writer`. The `evaluate_quality` node receives the full `WorkflowState` including all `recommendations` and `analogies` populated by earlier nodes.

**Tests to write first (TDD)**:
- For each workflow, test that the LangGraph graph contains `evaluate_quality` as a registered node.
- For each workflow, test that the `evaluate_quality` node's successor is `narrative_writer` (graph topology assertion on the compiled graph's edge map).
- Test that running a minimal mock workflow execution passes `WorkflowState` through `evaluate_quality` and `narrative_writer` in the correct order (integration-level node ordering test using mocked services).

**AC covered**: AC-001

---

### TASK-007: Tier2RunnerService — golden dataset regression runner · M/TDD · src/ai/evaluation/services/tier2_runner_service.py, src/ai/evaluation/interfaces/i_tier2_runner.py

Implement `Tier2RunnerService.run_regression(prompt_version_candidate, prompt_version_production, agent_role)`:
1. Call `IGoldenDatasetRepository.list_active()` to fetch all active test cases.
2. If fewer than 20 active cases exist, return `RegressionReport.passed=False` with a `reason="insufficient_dataset"` field (blocks the PR to force dataset growth).
3. For each golden dataset item, invoke the target agent using both the candidate and production prompt versions, collecting `evaluation_result` scores for each.
4. Compute per-metric delta: `delta[metric] = (candidate_score - production_score) / production_score`.
5. Collect `breached_metrics` where `delta[metric] < -0.05`.
6. Set `RegressionReport.passed = len(breached_metrics) == 0`.
7. Persist the `RegressionReport` as a structured log entry (JSON appended to a run log file at `logs/tier2_regression/`; not a DB table — CI consumes this as an artifact).

The 5% threshold is per-metric, not aggregate. A 10% improvement on coherence does not offset a 6% degradation on action signal correctness. This enforces REQ-N-009 AC-002.

**Tests to write first (TDD)**:
- Test `run_regression` with a mocked dataset of 25 items and candidate scores identical to production: `passed=True`, `breached_metrics=[]`.
- Test that a candidate scoring 6% worse than production on `action_signal_correctness` produces `passed=False` and `breached_metrics=["action_signal_correctness"]`.
- Test that a candidate scoring 3% worse on one metric and 10% better on another still passes (no breach, since 3% < 5% threshold).
- Test that a dataset with fewer than 20 active items returns `passed=False` with `reason="insufficient_dataset"`.
- Test that the per-metric delta computation is correct: production score 0.80, candidate score 0.74 → delta = (0.74 - 0.80) / 0.80 = -0.075 → breach.

**AC covered**: AC-002, AC-005

---

### TASK-008: GoldenDatasetService — candidate creation and approval · M/TDD · src/ai/evaluation/services/golden_dataset_service.py

Implement `GoldenDatasetService`:

`create_candidate(input: dict, expected_output: dict, quality_metrics: dict, source: Literal["hand_authored", "admin_override"]) -> GoldenDatasetItem`:
- Inserts via `IGoldenDatasetRepository.create_item` with `active=False`.
- Returns the created item (candidate state).
- Called by the admin override flow when an admin marks an AI decision as wrong (AC-005 path).

`approve_candidate(item_id: UUID, approved_by: UUID) -> GoldenDatasetItem`:
- Calls `IGoldenDatasetRepository.activate_item`.
- Only admin role may call this — enforced at the API layer (TASK-009), not here.

`list_candidates() -> list[GoldenDatasetItem]`:
- Delegates to `IGoldenDatasetRepository.list_candidates`.

`list_active() -> list[GoldenDatasetItem]`:
- Delegates to `IGoldenDatasetRepository.list_active`.

**Tests to write first (TDD)**:
- Test `create_candidate` with `source="admin_override"` inserts a row with `active=False` and returns it.
- Test `create_candidate` with `source="hand_authored"` also inserts with `active=False` (candidates are never auto-activated).
- Test `approve_candidate` transitions item from `active=False` to `active=True`; item appears in `list_active`.
- Test `list_candidates` returns only non-activated items; does not return active items.
- Test that approving an already-active item is idempotent (no exception, returns current state).

**AC covered**: AC-005

---

### TASK-009: FastAPI evaluation router — evaluation results, golden dataset management, calibration dashboard · M/TDD · src/api/evaluation/evaluation_router.py, src/api/evaluation/evaluation_api_schemas.py

Implement all REST endpoints. Controllers parse, validate, delegate to services, and respond. No business logic in the router.

**Tier 1 endpoints:**
- `GET /api/v1/evaluation/results` — admin-only; paginated list of `EvaluationResult`; supports `run_id` filter.
- `GET /api/v1/evaluation/results/{run_id}` — admin-only; returns all evaluation results for a specific workflow run.

**Tier 2 (golden dataset) endpoints:**
- `GET /api/v1/evaluation/golden-dataset` — admin-only; returns all active golden dataset items.
- `GET /api/v1/evaluation/golden-dataset/candidates` — admin-only; returns items pending approval.
- `POST /api/v1/evaluation/golden-dataset` — admin-only; accepts `GoldenDatasetItemCreate`; creates a candidate; returns 201.
- `POST /api/v1/evaluation/golden-dataset/{item_id}/approve` — admin-only; activates a candidate; returns 200.
- `DELETE /api/v1/evaluation/golden-dataset/{item_id}` — admin-only; deactivates (soft-delete via `deactivate_item`); returns 204.

**Tier 3 (calibration) endpoints:**
- `GET /api/v1/evaluation/calibration` — admin-only; query params: `days` (default 30), `action_signal` (optional); returns `list[CalibrationResult]` for the dashboard chart.
- `GET /api/v1/evaluation/calibration/summary` — admin-only; returns rolling CORR, below-threshold flag, and per-signal accuracy breakdown.

All routes use `Depends(get_current_user)` and `Depends(get_evaluation_service)`. Admin-only routes assert `current_user.role == "admin"` and return 403 otherwise.

**Tests to write first (TDD)**:
- Test `GET /api/v1/evaluation/results` by a non-admin returns 403.
- Test `POST /api/v1/evaluation/golden-dataset` by an admin with valid payload returns 201 and item is in `list_candidates`.
- Test `POST /api/v1/evaluation/golden-dataset/{item_id}/approve` by an admin activates the item; it appears in `GET /api/v1/evaluation/golden-dataset`.
- Test `DELETE /api/v1/evaluation/golden-dataset/{item_id}` deactivates item; it no longer appears in the active list.
- Test `GET /api/v1/evaluation/calibration/summary` returns `below_threshold=True` when rolling CORR < 0.3.
- Test that all admin-only routes return 401 for unauthenticated requests.

**AC covered**: AC-004, AC-005

---

### TASK-010: Tier3CalibrationService and daily Celery task · M/TDD · src/ai/evaluation/services/tier3_calibration_service.py, src/ai/evaluation/interfaces/i_tier3_calibration.py, src/ai/evaluation/tasks/calibration_tasks.py

Implement `Tier3CalibrationService.run_calibration(reference_date: date)`:
1. Query `recommendation_outcome` (via `IEpisodicRepository` from PLAN-F-015) for rows where `filled_at IS NOT NULL` and the recommendation's `generated_at::date = reference_date`.
2. Join with `ai_recommendation` to get `confidence`, `action_signal`, `direction` fields.
3. Compute `direction_sign`: `+1` if `direction == 'bullish'`, `-1` if `direction == 'bearish'`, `0` if `direction == 'neutral'`.
4. For each `action_signal` group: compute `direction_correct_pct`, `mean_confidence`, `mean_actual_t1d`, and `corr_confidence_actual` using Python `statistics.correlation` (or `numpy.corrcoef` if sample ≥ 2).
5. Insert one `calibration_result` row per `action_signal` group via `ICalibrationRepository.insert_result` (upsert on `(date, action_signal)`).
6. Check overall rolling CORR via `ICalibrationRepository.get_rolling_corr(days=30)`.
7. Set `CalibrationPassResult.below_threshold = rolling_corr < 0.3` when sample ≥ 30, else `None`.
8. Return `CalibrationPassResult`.

If fewer than 5 recommendations are available for a given `action_signal` on `reference_date`, skip that group and log a debug-level message.

Register `run_tier3_calibration` as a Celery task in `calibration_tasks.py`. Add beat schedule to `src/config/celery_app.py`: daily at 02:00 UTC (`reference_date = yesterday`).

**Tests to write first (TDD)**:
- Test `run_calibration` with 10 synthetic `recommendation_outcome` rows where higher confidence correlates with correct direction: assert `corr_confidence_actual > 0`.
- Test `run_calibration` with 10 rows where confidence is uncorrelated with outcome: assert `corr_confidence_actual` is near 0.
- Test that an `action_signal` group with fewer than 5 rows is skipped and no `calibration_result` row is inserted for it.
- Test that running calibration twice for the same `reference_date` upserts rather than duplicating rows.
- Test `CalibrationPassResult.below_threshold = True` when `get_rolling_corr` returns 0.25.
- Test `CalibrationPassResult.below_threshold = None` when fewer than 30 total recommendations exist in the rolling window.

**AC covered**: AC-003

---

### TASK-011: Calibration warning flag and 30-day dashboard summary · M/TDD · src/ai/evaluation/services/tier3_calibration_service.py, src/api/evaluation/evaluation_router.py

Extend `Tier3CalibrationService` with `get_calibration_summary(days: int = 30) -> CalibrationSummary`:
1. Call `ICalibrationRepository.list_last_n_days(days=days)`.
2. Aggregate total `total_recommendations` across all rows.
3. Compute per-`action_signal` accuracy from the stored rows.
4. Retrieve rolling CORR via `ICalibrationRepository.get_rolling_corr(days=days)`.
5. Derive `below_threshold: bool = rolling_corr < 0.3 and total_recommendations >= 30`.
6. Build `CalibrationSummary(rolling_corr, below_threshold, per_signal_accuracy: dict[str, float], total_recommendations, assessment: str)`.
7. `assessment` is a human-readable string: `"Healthy"` if `below_threshold is False`, `"Warning: CORR below threshold — improvement loop recommended"` if `True`, `"Insufficient data"` if sample < 30.

Wire `get_calibration_summary` into the `GET /api/v1/evaluation/calibration/summary` endpoint added in TASK-009.

**Tests to write first (TDD)**:
- Test `get_calibration_summary` with 35 recommendations and rolling CORR 0.45: `below_threshold=False`, `assessment="Healthy"`.
- Test with rolling CORR 0.22 and 35 recommendations: `below_threshold=True`, `assessment` contains "Warning".
- Test with only 15 total recommendations: `below_threshold=False` (insufficient data), `assessment="Insufficient data"`.
- Test per-signal accuracy aggregation: 3 HOLD rows, 2 BUY_OPP rows; assert dict contains both keys with correct averaged values.

**AC covered**: AC-004

---

### TASK-012: Integration tests — end-to-end evaluation flows · M/TDD · tests/integration/evaluation/test_tier1_flow.py, tests/integration/evaluation/test_tier2_flow.py, tests/integration/evaluation/test_tier3_flow.py

Write integration tests against real PostgreSQL test instances.

`test_tier1_flow.py`: simulate a Mode B workflow producing a `WorkflowState`; call `evaluate_quality_node` with a mocked Anthropic client returning valid judge JSON; assert an `evaluation_result` row is inserted; assert `state.confidence_scores["tier1_eval"]` is set; assert the node does not raise when the judge call throws `TimeoutError`.

`test_tier2_flow.py`: seed 25 active golden dataset items; call `Tier2RunnerService.run_regression` with a candidate prompt that produces scores 8% worse on one metric; assert `RegressionReport.passed=False` and `breached_metrics` contains that metric; then run with an equally-scoring candidate and assert `passed=True`.

`test_tier3_flow.py`: insert 10 synthetic `recommendation_outcome` rows with `actual_t1d` filled and matching `ai_recommendation` rows with known confidence values; call `Tier3CalibrationService.run_calibration(yesterday)`; assert `calibration_result` rows exist in DB; call `get_calibration_summary(days=30)`; assert summary fields are correct.

**Tests to write first (TDD)**:
- All tests in this task are integration-level TDD artifacts; they drive correctness of the full evaluation stack.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: evaluate_quality node (Tier 1) runs as second-to-last in every Mode B workflow using Opus 4.7; result stored as Langfuse evaluation trace → TASK-004, TASK-005, TASK-006, TASK-012
- AC-002: Tier 2 golden dataset CI runner blocks PR merge when any metric degrades >5% → TASK-001, TASK-002, TASK-007, TASK-012
- AC-003: Tier 3 daily job computes CORR(confidence, actual_t1d × direction_sign) and stores calibration_result rows → TASK-001, TASK-002, TASK-003, TASK-010, TASK-012
- AC-004: Admin calibration dashboard displays per-signal accuracy, calibration curve, and 30-day CORR with 30-day history → TASK-003, TASK-009, TASK-011, TASK-012
- AC-005: Admin override of an AI decision adds the input/output pair as a golden dataset candidate; it becomes active only after admin approval → TASK-001, TASK-002, TASK-003, TASK-007, TASK-008, TASK-009, TASK-012

## Acceptance Notes

- The `evaluate_quality` Tier 1 node calls Anthropic Opus 4.7 asynchronously. In the CI test environment the Anthropic client must be mocked; integration tests (TASK-012) use the mock, not a live API call, to avoid cost and flakiness.
- The Tier 2 regression runner (TASK-007) is invoked by CI but is not wired into a specific CI YAML file in this plan — the CI configuration change is part of PLAN-F-014 (Prompt Management Pipeline). This plan delivers the runner binary and its test coverage; PLAN-F-014 wires it into GitHub Actions.
- The `prompts/evaluators/` directory and three prompt files (TASK-004) must exist before TASK-005 can run in production. In tests, the prompt loader is mocked.

## Risks and Notes

- **Tier 1 cost impact**: Opus 4.7 at $0.01–$0.03 per evaluation multiplied by all five workflows at production volume may approach the $100/month budget (D12). If daily output volume exceeds ~200 Mode B reports, the per-evaluation cost model should be reviewed. Consider caching or batching judge calls at high volume.
- **Corr computation with small samples**: `statistics.correlation` requires at least 2 data points; `numpy.corrcoef` returns NaN for constant arrays. The calibration service must guard both cases and return `corr_confidence_actual=None` when the sample is too small or the variance is zero.
- **evaluate_quality node ordering**: All five workflow files must maintain the `evaluate_quality → narrative_writer` ordering invariant. If any workflow is restructured after this plan is implemented, the topological ordering test in TASK-006 will catch the regression.
- **Golden dataset minimum size**: REQ-N-009 AC-004 requires ≥ 20 cases for a valid CI run. The initial 20+ cases must be hand-authored before Tier 2 is operationally useful. TASK-008 `create_candidate` is the ingestion path; initial seeding is an operational task outside this plan's scope.
- **PLAN-F-015 dependency at runtime**: Tier 3 reads `recommendation_outcome` rows via `IEpisodicRepository` from PLAN-F-015. If PLAN-F-015 has not been executed, the Tier 3 calibration job will find no rows and return a no-op `CalibrationPassResult`. This is safe — the job does not fail on empty data.
