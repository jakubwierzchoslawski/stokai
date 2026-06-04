---
plan_id: PLAN-N-010
slug: ai-accuracy-calibration
title: AI Recommendation Accuracy Calibration
linked_requirement: REQ-N-010
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-016, reason: "Tier 3 calibration infrastructure (calibration_result table, Tier3CalibrationService, CalibrationRepository, daily Celery task, dashboard API) is built by PLAN-F-016; this plan adds threshold enforcement, configurable thresholds, weekly review recording, and outcome-fill closure" }
  - { id: PLAN-F-015, reason: "recommendation_outcome rows with actual_t1d/actual_t1w populated by the Layer 1 outcome-fill task are the raw data source for every calibration computation" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-010 — AI Recommendation Accuracy Calibration

## Linked Requirement
**REQ-N-010** — AI Recommendation Accuracy Calibration
Status: approved | Jira:

## Objective

Verify and enforce that the Tier 3 daily ex-post calibration machinery delivered by PLAN-F-016 meets the measurable reliability target defined in REQ-N-010: `CORR(confidence, actual_t1d × direction_sign) ≥ 0.3` over a rolling 30-day window with at least 30 recommendations. This plan adds the configurable CORR threshold setting, a weekly review recording table and API, an outcome-fill closure test (AC-004), and the NFR-level integration and contract tests that prove the threshold gate, warning flag, and dashboard operate correctly end-to-end. It does not re-implement any component already specified in PLAN-F-016; instead it layers enforcement, configuration, and observability on top of that functional foundation.

## Architecture Context

**Section 9 (Evaluation Framework):** Defines the Tier 3 metric (`CORR(confidence, actual_t1d × direction_sign) ≥ 0.3`), the rolling 30-day window, the admin dashboard, and the weekly human review loop. PLAN-F-016 builds the computation engine; this plan enforces and records the human-review side of the loop.

**Section 10 (Data Model):** `ai_recommendation.actual_t1d` and `ai_recommendation.actual_t1w` are filled from `price_bar` data by the PLAN-F-015 outcome-fill task. `calibration_result` rows (written by PLAN-F-016 TASK-010) are the input to every threshold check in this plan.

**Section 5 (Backend Module Map):** The configurable threshold lives in `src/config/settings.py` (the `ai` module consumes it). A new `calibration_review` table and service live in `src/ai/evaluation/` alongside the existing evaluation module from PLAN-F-016. The admin endpoint for recording weekly reviews is added to `src/api/evaluation/evaluation_router.py`.

**Section 11 (Admin Panel — AI Audit Console):** The calibration dashboard (built by PLAN-F-016) is extended with a "Record Weekly Review" action that writes a `CalibrationReview` row and clears the warning flag from the dashboard summary.

**Section 12.1 (Authentication):** All new admin endpoints require `role == "admin"` and `Authorization: Bearer` JWT.

**Section 12.4 (Observability):** Threshold breaches and weekly review submissions are logged as structured JSON at INFO level with `request_id` propagation.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-010 | CORR ≥ 0.3 over rolling 30-day window with ≥ 30 recommendations | TASK-001 makes this threshold configurable; TASK-003 records human weekly reviews; TASK-005 verifies the threshold gate in integration tests |

## Component Design

### New Components

```
Module: ai/evaluation  (src/ai/evaluation/)  — extends PLAN-F-016 components
  ├── models/
  │   └── calibration_review_models.py    — ORM: CalibrationReview
  ├── schemas/
  │   └── calibration_review_schemas.py   — Pydantic: CalibrationReviewCreate, CalibrationReview
  ├── interfaces/
  │   └── i_calibration_review_repository.py — ICalibrationReviewRepository (abstract)
  ├── repositories/
  │   └── calibration_review_repository.py   — CalibrationReviewRepository (SQLAlchemy 2.0 async)
  └── services/
      └── calibration_review_service.py      — CalibrationReviewService

Alembic migration:
  alembic/versions/XXXX_calibration_review_table.py
  alembic/versions/XXXX_calibration_threshold_setting.py  — adds CALIBRATION_CORR_THRESHOLD to settings
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/config/settings.py` | Add `CALIBRATION_CORR_THRESHOLD: float = 0.3` and `CALIBRATION_MIN_SAMPLE: int = 30` | Makes threshold configurable per AC-002; no hardcoded values |
| `src/ai/evaluation/services/tier3_calibration_service.py` | Read threshold from settings rather than literal `0.3`; expose `CalibrationPassResult.threshold_used` field | Enables environment-level threshold override and traceability |
| `src/api/evaluation/evaluation_router.py` | Add `POST /api/v1/evaluation/calibration/reviews` and `GET /api/v1/evaluation/calibration/reviews` endpoints | Weekly review recording and retrieval (AC-003) |
| `src/api/evaluation/evaluation_api_schemas.py` | Add `CalibrationReviewRequest` and `CalibrationReviewResponse` Pydantic models | Request/response DTOs for review endpoints |

### Interfaces and Contracts

```python
# src/ai/evaluation/interfaces/i_calibration_review_repository.py

class ICalibrationReviewRepository(ABC):
    @abstractmethod
    async def insert_review(self, review: CalibrationReviewCreate) -> CalibrationReview: ...
    @abstractmethod
    async def list_recent(self, limit: int = 10) -> list[CalibrationReview]: ...
    @abstractmethod
    async def get_last_review(self) -> CalibrationReview | None: ...

# src/ai/evaluation/services/calibration_review_service.py

class CalibrationReviewService:
    def __init__(
        self,
        review_repo: ICalibrationReviewRepository,
        calibration_repo: ICalibrationRepository,  # from PLAN-F-016
    ) -> None: ...

    async def record_review(
        self,
        reviewed_by: UUID,
        corr_at_review: float | None,
        below_threshold: bool,
        action_taken: str,
        notes: str | None,
    ) -> CalibrationReview: ...

    async def list_reviews(self, limit: int = 10) -> list[CalibrationReview]: ...

# Extended CalibrationPassResult (src/ai/evaluation/schemas/calibration_schemas.py)
# Add field to existing schema from PLAN-F-016:
#   threshold_used: float        — value of CALIBRATION_CORR_THRESHOLD used in this run
#   min_sample_used: int         — value of CALIBRATION_MIN_SAMPLE used in this run

# New Pydantic models (src/api/evaluation/evaluation_api_schemas.py):
class CalibrationReviewRequest(BaseModel):
    action_taken: str            # "no_action" | "improvement_loop_triggered" | "model_flag"
    notes: str | None = None

class CalibrationReviewResponse(BaseModel):
    review_id: UUID
    reviewed_by: UUID
    reviewed_at: datetime
    corr_at_review: float | None
    below_threshold: bool
    action_taken: str
    notes: str | None
```

## Implementation Tasks

### TASK-001: Configurable calibration threshold settings · S/no-TDD · src/config/settings.py

Add `CALIBRATION_CORR_THRESHOLD: float = 0.3` and `CALIBRATION_MIN_SAMPLE: int = 30` to the application settings class (Pydantic `BaseSettings`). Both values are read from environment variables (`CALIBRATION_CORR_THRESHOLD`, `CALIBRATION_MIN_SAMPLE`) with the documented defaults. Startup validation asserts `0.0 < CALIBRATION_CORR_THRESHOLD < 1.0` and `CALIBRATION_MIN_SAMPLE >= 1` — startup fails fast if values are out of range.

Modify `Tier3CalibrationService.run_calibration()` (from PLAN-F-016) to read `settings.CALIBRATION_CORR_THRESHOLD` and `settings.CALIBRATION_MIN_SAMPLE` instead of literal values. Expose `threshold_used` and `min_sample_used` on `CalibrationPassResult` so every calibration result is self-documenting.

**AC covered**: AC-002

---

### TASK-002: calibration_review table, ORM model, and repository · M/TDD · alembic/versions/XXXX_calibration_review_table.py, src/ai/evaluation/models/calibration_review_models.py, src/ai/evaluation/schemas/calibration_review_schemas.py, src/ai/evaluation/interfaces/i_calibration_review_repository.py, src/ai/evaluation/repositories/calibration_review_repository.py

Create the `calibration_review` table:

```
calibration_review (
  review_id         UUID PK DEFAULT gen_random_uuid(),
  reviewed_by       UUID NOT NULL,                      -- FK to user.user_id
  reviewed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  corr_at_review    FLOAT NULL,                         -- rolling CORR value at time of review
  below_threshold   BOOL NOT NULL,
  action_taken      VARCHAR NOT NULL
      CHECK (action_taken IN ('no_action', 'improvement_loop_triggered', 'model_flag')),
  notes             TEXT NULL
)
```

Index on `reviewed_at DESC`.

Define SQLAlchemy 2.0 `DeclarativeBase` mapped class `CalibrationReview` with `Mapped[]` typed annotations.

Define Pydantic v2 models: `CalibrationReviewCreate` (fields: `reviewed_by`, `corr_at_review`, `below_threshold`, `action_taken`, `notes`) and `CalibrationReview` (all fields including `review_id` and `reviewed_at`).

Implement `CalibrationReviewRepository` against `ICalibrationReviewRepository`:
- `insert_review`: plain `INSERT`; returns the created row.
- `list_recent`: `ORDER BY reviewed_at DESC LIMIT :limit`.
- `get_last_review`: `ORDER BY reviewed_at DESC LIMIT 1`.

**Tests to write first (TDD)**:
- Test the Alembic migration applies cleanly; `calibration_review` table exists with all columns and the `action_taken` CHECK constraint.
- Test that `action_taken` CHECK rejects a value outside the allowed set.
- Test `CalibrationReviewRepository.insert_review` persists a row and returns it with `review_id` and `reviewed_at` populated.
- Test `list_recent` returns rows in descending `reviewed_at` order, bounded by `limit`.
- Test `get_last_review` returns `None` on empty table; returns the most-recent row when rows exist.
- Test that a second `insert_review` does not affect the first row (independent inserts; no upsert).

**AC covered**: AC-003

---

### TASK-003: CalibrationReviewService and admin API endpoints · M/TDD · src/ai/evaluation/services/calibration_review_service.py, src/api/evaluation/evaluation_router.py, src/api/evaluation/evaluation_api_schemas.py

Implement `CalibrationReviewService`:

`record_review(reviewed_by, corr_at_review, below_threshold, action_taken, notes)`:
1. Validates `action_taken` is one of `('no_action', 'improvement_loop_triggered', 'model_flag')`; raises `ValueError` if not.
2. Calls `ICalibrationReviewRepository.insert_review` with all fields.
3. Logs a structured INFO entry: `{"event": "calibration_review_recorded", "reviewed_by": str(reviewed_by), "corr_at_review": corr_at_review, "below_threshold": below_threshold, "action_taken": action_taken}`.
4. Returns the created `CalibrationReview`.

`list_reviews(limit)`: delegates to `ICalibrationReviewRepository.list_recent`.

Add two admin-only endpoints to the existing `evaluation_router.py` (from PLAN-F-016):

- `POST /api/v1/evaluation/calibration/reviews` — admin-only; accepts `CalibrationReviewRequest`; fetches current rolling CORR from `ICalibrationRepository.get_rolling_corr(days=30)` and `below_threshold` from `Tier3CalibrationService.get_calibration_summary()`; calls `CalibrationReviewService.record_review`; returns 201 with `CalibrationReviewResponse`.

- `GET /api/v1/evaluation/calibration/reviews` — admin-only; returns paginated list of `CalibrationReviewResponse`; default limit 10.

Both endpoints use `Depends(get_current_user)` and assert `current_user.role == "admin"` — return 403 otherwise.

**Tests to write first (TDD)**:
- Test `CalibrationReviewService.record_review` with `action_taken="no_action"` inserts a review row and returns it.
- Test `record_review` with an invalid `action_taken` value raises `ValueError` before touching the repository.
- Test `record_review` logs the structured INFO entry (capture logger output in test).
- Test `POST /api/v1/evaluation/calibration/reviews` by a non-admin returns 403.
- Test `POST /api/v1/evaluation/calibration/reviews` by an unauthenticated request returns 401.
- Test `POST /api/v1/evaluation/calibration/reviews` by an admin with `action_taken="improvement_loop_triggered"` returns 201 and a `CalibrationReviewResponse` with `review_id` populated.
- Test `GET /api/v1/evaluation/calibration/reviews` by an admin returns a list of previously recorded reviews in descending order.
- Test the endpoint correctly reads and embeds current `corr_at_review` from `CalibrationRepository.get_rolling_corr` — mock the repository to return `0.22`.

**AC covered**: AC-003

---

### TASK-004: Outcome-fill closure test — actual_t1d populated the following trading day · M/TDD · tests/integration/calibration/test_outcome_fill_closure.py

Write an integration test that verifies the feedback loop described in AC-004: after an `ai_recommendation` row is created, the `run_outcome_fill` Celery task from PLAN-F-015 populates `actual_t1d` the following trading day, and subsequently the daily `run_tier3_calibration` Celery task from PLAN-F-016 reads that row and produces a `calibration_result` row.

Test steps:
1. Insert an `ai_recommendation` row with `actual_t1d=NULL` and `confidence=0.8`, `action_signal='BUY_OPP'`, `direction='bullish'`.
2. Insert a `recommendation_outcome` row linked to the recommendation with `actual_t1d=NULL`.
3. Insert a `price_bar` row for the company representing T+1d with a positive closing price change.
4. Call `EpisodicRepository.fill_outcome_actuals` directly (simulating the T+1d outcome-fill task from PLAN-F-015) with the computed `actual_t1d` value.
5. Assert `recommendation_outcome.actual_t1d` is now populated and `filled_at IS NOT NULL`.
6. Call `Tier3CalibrationService.run_calibration(reference_date=yesterday)` (from PLAN-F-016).
7. Assert a `calibration_result` row exists for `reference_date` and `action_signal='BUY_OPP'`.
8. Assert `calibration_result.corr_confidence_actual` is not NULL.

This test does not mock the repository layer — it runs against a real PostgreSQL test instance to confirm the full data flow.

**Tests to write first (TDD)**:
- The entire task is the TDD artifact: the integration test is written first and drives that the outcome-fill → calibration pipeline is wired correctly end-to-end.

**AC covered**: AC-004

---

### TASK-005: NFR threshold enforcement integration tests · M/TDD · tests/integration/calibration/test_calibration_threshold.py

Write integration tests that verify the threshold gate and warning flag mechanics specified in REQ-N-010.

Test cases:
1. **Threshold met — no warning:** Seed 30 `calibration_result` rows spanning 30 days with `corr_confidence_actual=0.45` for each. Call `Tier3CalibrationService.get_calibration_summary(days=30)`. Assert `below_threshold=False`, `assessment="Healthy"`, `rolling_corr >= 0.3`.

2. **Threshold breached — warning flag set:** Seed 30 `calibration_result` rows with `corr_confidence_actual=0.15` for each. Call `get_calibration_summary(days=30)`. Assert `below_threshold=True`, `assessment` contains "Warning", `rolling_corr < 0.3`. Call `GET /api/v1/evaluation/calibration/summary` as admin via HTTP test client. Assert response body has `"below_threshold": true`.

3. **Insufficient sample — no threshold decision:** Seed only 10 `calibration_result` rows with a total of 20 recommendations. Call `get_calibration_summary(days=30)`. Assert `below_threshold=False` (insufficient data path), `assessment="Insufficient data"`.

4. **Configurable threshold respected:** Override `CALIBRATION_CORR_THRESHOLD=0.5` in settings. Seed rows with `corr_confidence_actual=0.35` (above 0.3 but below 0.5). Assert `below_threshold=True` — the override threshold is applied.

5. **Warning flag visible via HTTP dashboard endpoint:** Call `GET /api/v1/evaluation/calibration/summary` when `below_threshold=True`; assert the JSON response contains `"below_threshold": true` and the `assessment` string contains "Warning".

**Tests to write first (TDD)**:
- All test cases in this task are the TDD artifact; they are written first to define the expected behaviour of the threshold gate before verifying the PLAN-F-016 implementation satisfies the REQ-N-010 measurable target.

**AC covered**: AC-001, AC-002

---

### TASK-006: Dashboard contract test — calibration chart, per-signal breakdown, health assessment · S/no-TDD · tests/contract/calibration/test_calibration_dashboard_contract.py

Write contract tests (HTTP-level, using `TestClient`) that verify the admin calibration dashboard API response schema matches what REQ-N-010 AC-003 requires: 30-day rolling CORR chart data, per-action-signal accuracy breakdown, and human-readable calibration health assessment.

Test cases:
1. `GET /api/v1/evaluation/calibration?days=30` returns a list of `CalibrationResult` objects each containing `date`, `action_signal`, `corr_confidence_actual`, `direction_correct_pct`, `mean_confidence`; assert all required fields are present.
2. `GET /api/v1/evaluation/calibration/summary` returns a JSON object with keys: `rolling_corr`, `below_threshold`, `per_signal_accuracy`, `total_recommendations`, `assessment`; assert types are correct.
3. `assessment` is one of `"Healthy"`, `"Warning: CORR below threshold — improvement loop recommended"`, or `"Insufficient data"` — assert the returned string matches one of these exactly.
4. Assert non-admin requests to both endpoints return 403.

**AC covered**: AC-003

## Acceptance Criteria Coverage

- AC-001: Daily Tier 3 calibration job runs and produces calibration_result row for previous day with CORR(confidence, actual_t1d × direction_sign) → TASK-005 (NFR integration tests verify the daily job produces compliant rows; PLAN-F-016 TASK-010 builds the job itself)
- AC-002: Given 30 days of calibration results with ≥ 30 recommendations, CORR ≥ 0.3; if CORR falls below 0.3, admin calibration dashboard displays warning flag triggering improvement loop → TASK-001, TASK-005
- AC-003: Admin calibration dashboard displays 30-day rolling CORR chart, per-action-signal accuracy breakdown, and human-readable calibration health assessment → TASK-002, TASK-003, TASK-006
- AC-004: New ai_recommendation row created → actual_t1d field populated the following trading day via calibration job, closing feedback loop → TASK-004

## Acceptance Notes

- AC-001 and AC-002 are partially satisfied by PLAN-F-016 TASK-010 and TASK-011 which build the daily job and warning flag mechanics. This plan's TASK-005 provides the NFR verification test layer that confirms the threshold target (`CORR ≥ 0.3`) is met in an integrated environment.
- The `run_tier3_calibration` Celery task beat schedule (02:00 UTC daily) is registered in PLAN-F-016. This plan does not register a second beat entry; it tests the existing schedule.
- For AC-004, the outcome-fill task itself (`run_outcome_fill`) is implemented by PLAN-F-015 TASK-013. TASK-004 in this plan writes the integration test that proves the full feedback loop (recommendation created → outcome filled → calibration reads it) closes correctly.
- Weekly review recording (TASK-002, TASK-003) is new functionality not covered by PLAN-F-016; it implements the "results reviewed weekly; review recorded in admin calibration dashboard" clause of REQ-N-010.

## Risks and Notes

- **Dependency on PLAN-F-016 execution:** This plan's integration and contract tests import `Tier3CalibrationService`, `CalibrationRepository`, and the evaluation router from PLAN-F-016. If PLAN-F-016 has not been executed, tests will fail at import. The plans-index Wave 2 ordering (PLAN-N-010 in Wave 2 after PLAN-F-016 in Wave 1) enforces correct execution sequence.
- **CORR computation with small samples:** `statistics.correlation` raises `StatisticsError` for samples of size 1 and returns `NaN` for zero-variance arrays. The `Tier3CalibrationService` from PLAN-F-016 guards these cases, but TASK-005 tests must seed data with sufficient variance to produce a meaningful CORR value. Use synthetic data where higher-confidence recommendations align with positive `actual_t1d` (direction correct) to produce `corr > 0`.
- **Configurable threshold environment variable:** `CALIBRATION_CORR_THRESHOLD` must be documented in `.env.example`. The TASK-001 settings change must include the entry in `.env.example` and the startup validation. Failure to set a valid float results in fast-fail on startup.
- **per_signal_accuracy dict key naming:** The `per_signal_accuracy` dict returned by `get_calibration_summary` uses `action_signal` values as keys (`HOLD`, `WATCH`, `BUY_OPP`, `REDUCE_RISK`, `HEDGE`, `CONTRARIAN`). TASK-006 contract tests must assert on at least two distinct keys when test data covers multiple signals.
- **Weekly review recording is advisory, not automated:** The `calibration_review` table records the human operator's acknowledgment and chosen action. It does not automatically trigger the improvement loop — triggering is a separate manual workflow. The `action_taken="improvement_loop_triggered"` value signals that a human made that decision, but the loop itself is governed by PLAN-F-016 and the prompt management pipeline.
