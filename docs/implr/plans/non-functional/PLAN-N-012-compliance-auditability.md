---
plan_id: PLAN-N-012
slug: compliance-auditability
title: AI Compliance and Auditability
linked_requirement: REQ-N-012
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-015, reason: "Layer 1 episodic tables (agent_invocation, tool_call) and IEpisodicRepository are the storage substrate for reasoning chain audit" }
  - { id: PLAN-F-029, reason: "Admin AI Audit Console provides the replay step-through UI; this plan verifies and enforces the data quality and completeness feeding it" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-04T00:00:00Z
---

# PLAN-N-012 — AI Compliance and Auditability

## Linked Requirement
**REQ-N-012** — AI Compliance and Auditability
Status: approved | Jira:

## Objective

Implement the cross-cutting compliance and auditability guardrails required by REQ-N-012. This plan does not build new storage tables (those are owned by PLAN-F-015) or new admin UI panels (owned by PLAN-F-029); instead it enforces four specific obligations that cut across every module:

1. **Episodic completeness enforcement** — a Celery-scheduled integrity check that detects agent invocations in `workflow_run` rows whose `agent_invocation` count is zero, alerting operators to any gap in the 100%-coverage target within 5 seconds of invocation completion.
2. **Disclaimer injection middleware** — a FastAPI response middleware that intercepts every recommendation-bearing API response and, when `sample_size < 5`, injects the mandatory disclaimer text inline. A single serialization-layer hook guarantees all display surfaces (alert, side panel, brief, email) receive the disclaimer without per-screen implementation.
3. **Ex-post accuracy visibility** — the `recommendation_outcome` Celery fill task (owned by PLAN-F-015) already populates `actual_t1d` and `actual_t1w`; this plan adds the public-facing API endpoint and frontend component that surfaces the track record on the Company Detail screen.
4. **Derived-data-only API enforcement** — a test suite that asserts no endpoint in the FastAPI application returns raw OHLCV fields (`open`, `high`, `low`, `close`, `volume`) from the `price_bar` table, ensuring that only derived representations (`score`, `score_delta`, `percentile_rank`, `sparkline_data`) reach end users.

Together these four tasks bring the system into full compliance with AC-001 through AC-004 from REQ-N-012.

## Architecture Context

This plan operates across three architecture sections.

**Section 12 (Cross-Cutting Concerns):** The disclaimer injection is deliberately placed at the serialization (API response) layer, not per-screen, per Architecture §12 guidance: "Disclaimer injection must happen at the serialization layer (API response layer), not per-screen, to guarantee all display surfaces are covered." A FastAPI middleware or response model post-processor is the correct integration point.

**Section 10 (Data Model):** The `ai_recommendation` table carries `sample_size`, `actual_t1d`, `actual_t1w`, and `accuracy` columns. The `agent_invocation` table (Layer 1 episodic memory) stores every agent execution. The `price_bar` table stores OHLCV internally; the API layer must never return its raw fields. This plan adds a narrow compliance query endpoint over `ai_recommendation` and `recommendation_outcome` but introduces no new schema changes.

**Section 7.4 (Four-Layer Memory — Layer 1):** Append-only enforcement of `agent_invocation` and `tool_call` rows is implemented by PLAN-F-015. This plan adds a periodic integrity check service that queries these tables to verify coverage: for every `workflow_run` row in a completed state, at least one `agent_invocation` row must exist.

**Section 5 (Backend Module Map):** New code lives in:
- `src/api/middleware/disclaimer_middleware.py` — FastAPI middleware for disclaimer injection.
- `src/compliance/` — new lightweight module: `compliance_check_service.py`, `compliance_schemas.py`, a Celery task `compliance_tasks.py`, and a read-only router `compliance_router.py`.
- `tests/compliance/` — derived-data-only assertion suite.

The `api` module is the only consumer of `disclaimer_middleware`; the `compliance` module depends only on `storage` (IEpisodicRepository). No circular dependency is introduced.

**Section 11 (Frontend Architecture):** The recommendation track record component lives in the existing Company Detail screen (`src/frontend/company/CompanyDetailPage.tsx`). A new `RecommendationTrackRecord.tsx` component is added to the `company` feature folder; it fetches from the new compliance API endpoint.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-012 | 100% of agent invocations produce agent_invocation rows within 5 s | Integrity check task (TASK-001) detects and alerts on any missed rows; measurement window is last 90 days |
| REQ-N-012 | 100% of recommendations with sample_size < 5 display disclaimer | Disclaimer middleware (TASK-002) enforces this at the API layer for all endpoints; email dispatch path receives the disclaimer from the alert content field |
| REQ-N-012 | Derived data only — no raw OHLCV served to users | TASK-004 assertion suite runs in CI; any endpoint returning raw OHLCV fields fails the build |

## Component Design

### New Components

```
Module: compliance  (src/compliance/)
  ├── __init__.py
  ├── compliance_check_service.py   — ComplianceCheckService: episodic coverage queries
  ├── compliance_schemas.py         — Pydantic DTOs: CoverageReport, TrackRecordEntry,
  │                                    DisclaimerAuditResult
  ├── compliance_tasks.py           — Celery task: run_episodic_coverage_check (hourly)
  └── compliance_router.py          — FastAPI router: track record endpoint (authenticated)

Module: api/middleware  (src/api/middleware/)
  ├── __init__.py
  └── disclaimer_middleware.py      — DisclaimerMiddleware (Starlette BaseHTTPMiddleware):
                                       intercepts JSON responses; injects disclaimer when
                                       sample_size < 5 in any recommendation object

Frontend: src/frontend/company/
  └── RecommendationTrackRecord.tsx — Track record component for Company Detail screen;
                                       fetches /api/v1/compliance/track-record/{company_id}

Tests:
  tests/compliance/
  ├── test_episodic_coverage.py     — Unit + integration tests for ComplianceCheckService
  ├── test_disclaimer_middleware.py — Unit tests for DisclaimerMiddleware
  ├── test_track_record_api.py      — Integration tests for the track record endpoint
  └── test_derived_data_only.py     — Static assertion suite: no raw OHLCV in any endpoint
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/main.py` (or `src/api/app.py`) | Register `DisclaimerMiddleware` on the FastAPI app; include `compliance_router` | Wire new middleware and compliance router into the application |
| `src/config/celery_app.py` | Add `run_episodic_coverage_check` to the Celery beat schedule (hourly) | Periodic compliance integrity check |
| `src/config/settings.py` | Add `DISCLAIMER_SAMPLE_SIZE_THRESHOLD` (default 5), `DISCLAIMER_TEXT` (default "Based on fewer than 5 historical cases — treat with caution"), `COMPLIANCE_CHECK_LOOKBACK_DAYS` (default 90) | No hardcoded thresholds or text |
| `src/frontend/company/CompanyDetailPage.tsx` | Add `<RecommendationTrackRecord companyId={companyId} />` below the recommendation section | Surface ex-post accuracy on Company Detail screen |

### Interfaces and Contracts

```python
# src/compliance/compliance_schemas.py

class CoverageGap(BaseModel):
    workflow_run_id: UUID
    workflow_type: str
    started_at: datetime
    completed_at: datetime | None
    agent_invocation_count: int  # always 0 in a gap row

class CoverageReport(BaseModel):
    checked_at: datetime
    lookback_days: int
    total_completed_runs: int
    runs_with_zero_invocations: int
    coverage_pct: float          # (total - gaps) / total * 100
    gaps: list[CoverageGap]      # empty when coverage_pct == 100.0

class TrackRecordEntry(BaseModel):
    rec_id: UUID
    company_ticker: str
    action_signal: str           # HOLD | WATCH | BUY_OPP | REDUCE_RISK | HEDGE | CONTRARIAN
    confidence: float
    sample_size: int
    generated_at: datetime
    actual_t1d: float | None
    actual_t1w: float | None
    accuracy: float | None
    disclaimer_required: bool    # True when sample_size < DISCLAIMER_SAMPLE_SIZE_THRESHOLD

class TrackRecordResponse(BaseModel):
    company_id: UUID
    company_ticker: str
    entries: list[TrackRecordEntry]
    total: int
    direction_correct_t1d_pct: float | None  # None when no actuals yet
    direction_correct_t1w_pct: float | None

class DisclaimerAuditResult(BaseModel):
    """Returned by internal audit endpoint; not user-facing."""
    audited_at: datetime
    sample_checked: int
    disclaimer_present_count: int
    disclaimer_missing_count: int
    missing_rec_ids: list[UUID]


# src/compliance/compliance_check_service.py

class IComplianceCheckService(ABC):
    @abstractmethod
    async def run_coverage_check(self, lookback_days: int) -> CoverageReport: ...
    @abstractmethod
    async def get_company_track_record(
        self, company_id: UUID, limit: int = 50
    ) -> TrackRecordResponse: ...


# src/api/middleware/disclaimer_middleware.py

DISCLAIMER_FIELD = "disclaimer"

class DisclaimerMiddleware(BaseHTTPMiddleware):
    """
    Intercepts all JSON responses from the API.
    For any JSON object or array element that contains a 'sample_size' key with a value
    below the configured threshold, injects:
      "disclaimer": "<DISCLAIMER_TEXT>"
    at the same level as 'sample_size'.
    Operates recursively on nested objects and arrays.
    Only modifies Content-Type: application/json responses.
    Passes all other responses through unchanged.
    """
    def __init__(self, app, threshold: int, disclaimer_text: str): ...
    async def dispatch(self, request: Request, call_next) -> Response: ...
    def _inject_disclaimer(self, data: Any, threshold: int, text: str) -> Any: ...
```

## Implementation Tasks

### TASK-001: ComplianceCheckService — episodic coverage check and Celery task · M/TDD · src/compliance/compliance_check_service.py, src/compliance/compliance_schemas.py, src/compliance/compliance_tasks.py, src/config/celery_app.py

Implement `ComplianceCheckService.run_coverage_check(lookback_days: int) -> CoverageReport`.

The query logic:
1. Fetch all `workflow_run` rows with `status IN ('done', 'failed')` and `completed_at >= NOW() - INTERVAL ':days days'` via `IEpisodicRepository`.
2. For each run, check whether at least one `agent_invocation` row exists referencing that `workflow_id`.
3. Collect all runs with zero invocations as `CoverageGap` records.
4. Compute `coverage_pct = (total - gap_count) / total * 100` (100.0 when total is zero — vacuously compliant).
5. Return a `CoverageReport`.

The service takes `IEpisodicRepository` as a constructor-injected dependency (from PLAN-F-015). It does not depend on any other module.

Register `run_episodic_coverage_check` as a Celery task in `compliance_tasks.py`. The task calls `ComplianceCheckService.run_coverage_check(COMPLIANCE_CHECK_LOOKBACK_DAYS)`, logs the result at `INFO` level, and logs `WARNING` if `coverage_pct < 100.0`, including all gap `workflow_run_id` values. Add the beat schedule entry in `celery_app.py`: every hour at minute 0.

Note: this task is read-only and idempotent. Running it twice in an hour produces the same report (the underlying episodic tables are append-only, so no side effects occur).

**Tests to write first (TDD)**:
- Test `run_coverage_check` with 5 completed workflow runs, all having at least one agent_invocation: returns `coverage_pct=100.0` and `gaps=[]`.
- Test `run_coverage_check` with 5 completed runs, 2 having zero invocations: returns `coverage_pct=60.0` and `gaps` with exactly 2 entries whose `agent_invocation_count=0`.
- Test `run_coverage_check` with zero completed runs in the lookback window: returns `coverage_pct=100.0` (vacuously compliant), `total_completed_runs=0`, `gaps=[]`.
- Test that `workflow_run` rows with `status='in_progress'` are excluded from the coverage check.
- Test that `workflow_run` rows older than `lookback_days` are excluded.
- Test the Celery task logs a `WARNING` when any gaps are found (mock the logger).
- Test the Celery task logs `INFO` when coverage is 100%.

**AC covered**: AC-001

---

### TASK-002: DisclaimerMiddleware — sample_size-gated disclaimer injection · M/TDD · src/api/middleware/__init__.py, src/api/middleware/disclaimer_middleware.py, src/api/main.py (or app.py), src/config/settings.py

Implement `DisclaimerMiddleware` as a `starlette.middleware.base.BaseHTTPMiddleware` subclass.

Dispatch logic:
1. Call `call_next(request)` to get the upstream response.
2. If `response.headers.get("content-type", "").startswith("application/json")` is False, return the response unchanged.
3. Accumulate the response body bytes, decode as UTF-8, parse as JSON.
4. Call `_inject_disclaimer(data, threshold, text)` recursively:
   - If `data` is a `dict` and `"sample_size"` is a key with an integer value less than `threshold`: add `"disclaimer": text` to the dict (only if not already present). Then recurse into all values.
   - If `data` is a `dict` without `"sample_size"`: recurse into all values.
   - If `data` is a `list`: recurse into each element.
   - Otherwise: return unchanged.
5. Re-serialize the (possibly modified) data to JSON and return a new `Response` with the same status code and headers, replacing the body.

The threshold and disclaimer text are read from `settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD` (default 5) and `settings.DISCLAIMER_TEXT` (default "Based on fewer than 5 historical cases — treat with caution"). Both are injected at construction time; no global state access inside `_inject_disclaimer`.

Register the middleware in `src/api/main.py`:
```python
app.add_middleware(
    DisclaimerMiddleware,
    threshold=settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD,
    disclaimer_text=settings.DISCLAIMER_TEXT,
)
```

Add the two new settings to `src/config/settings.py` with their defaults.

**Tests to write first (TDD)**:
- Test `_inject_disclaimer` with a flat dict containing `sample_size=3` (below threshold 5): the dict gains `"disclaimer": "<text>"` key.
- Test `_inject_disclaimer` with `sample_size=5` (equal to threshold): no disclaimer added (threshold is strict less-than).
- Test `_inject_disclaimer` with `sample_size=6` (above threshold): no disclaimer added.
- Test `_inject_disclaimer` with a dict not containing `sample_size`: returned unchanged.
- Test `_inject_disclaimer` with a nested structure — `{"recommendation": {"sample_size": 2, "action": "HOLD"}, "meta": {}}`: disclaimer is injected inside the nested `recommendation` dict only.
- Test `_inject_disclaimer` with a list of recommendation dicts, two with `sample_size=1` and one with `sample_size=10`: only the first two gain the disclaimer.
- Test `_inject_disclaimer` does not add the disclaimer key when it is already present (idempotent).
- Test the middleware (via ASGI test client) with a mock endpoint returning `{"sample_size": 2, "action": "HOLD"}`: response body contains `"disclaimer"` key.
- Test the middleware with a non-JSON response (e.g. `text/html`): response passes through unchanged.
- Test the middleware with a JSON response containing no `sample_size` key: response passes through unchanged.
- Test the middleware with a JSON response where `sample_size=10`: response passes through unchanged.

**AC covered**: AC-003

---

### TASK-003: Compliance router — company recommendation track record endpoint · M/TDD · src/compliance/compliance_router.py, src/api/main.py (or app.py)

Implement `ComplianceCheckService.get_company_track_record(company_id: UUID, limit: int = 50) -> TrackRecordResponse`.

Query logic:
1. Query `ai_recommendation` rows where `company_id = :company_id` ordered by `generated_at DESC` with a limit. Use `IRecommendationRepository` (a new narrow read-only repository interface defined in this task, backed by the `ai_recommendation` table that is populated by the Mode B workflow plans).
2. For each row, join with `recommendation_outcome` (if a row exists) to obtain `actual_t1d`, `actual_t1w`.
3. Set `disclaimer_required = recommendation.sample_size < DISCLAIMER_SAMPLE_SIZE_THRESHOLD`.
4. Compute summary aggregates: `direction_correct_t1d_pct` = percentage of entries where `actual_t1d * direction_sign > 0` (only over entries where `actual_t1d IS NOT NULL`); `None` if no actuals yet. Same for `_t1w`.
5. Map to `TrackRecordResponse`.

Define the read-only repository interface:
```python
class IRecommendationRepository(ABC):
    @abstractmethod
    async def list_by_company(
        self, company_id: UUID, limit: int
    ) -> list[RecommendationWithOutcome]: ...
```

Expose the endpoint in `compliance_router.py`:
- `GET /api/v1/compliance/track-record/{company_id}` — authenticated (any role); query param `limit` (default 50, max 200); returns `TrackRecordResponse`.

The router uses `Depends(get_current_user)` — no admin-only restriction; all authenticated users can view the track record from the Company Detail screen.

Register the router in `src/api/main.py` with prefix `/api/v1/compliance`.

**Tests to write first (TDD)**:
- Test `get_company_track_record` with 3 recommendations, all `actual_t1d` filled and directionally correct: `direction_correct_t1d_pct = 100.0`.
- Test `get_company_track_record` with 2 recommendations, none with `actual_t1d`: `direction_correct_t1d_pct = None`.
- Test `get_company_track_record` with mixed: 1 correct, 1 incorrect, 1 no actual: `direction_correct_t1d_pct = 50.0` (computed over the 2 with actuals).
- Test that a recommendation with `sample_size=3` has `disclaimer_required=True` in the response.
- Test that a recommendation with `sample_size=7` has `disclaimer_required=False` in the response.
- Test `GET /api/v1/compliance/track-record/{company_id}` by an unauthenticated request returns 401.
- Test `GET /api/v1/compliance/track-record/{company_id}` by an authenticated `end_user` returns 200.
- Test `GET /api/v1/compliance/track-record/{company_id}` with `limit=5` returns at most 5 entries.
- Test response for a `company_id` with no recommendations returns `entries=[]`, `total=0`, accuracy fields `None`.

**AC covered**: AC-001, AC-003

---

### TASK-004: Derived-data-only assertion suite · M/TDD · tests/compliance/test_derived_data_only.py

Implement a static and integration assertion suite that verifies no FastAPI endpoint returns raw OHLCV fields to end users.

**Static analysis assertions** (run as a standard pytest test, not a separate linting step):
- Walk all Pydantic response model classes registered on the FastAPI app's OpenAPI schema.
- For each response model, assert that none of the following field names are present at the top level or in any nested model: `open`, `high`, `low`, `close`, `volume` (the five OHLCV columns from `price_bar`).
- Exclude internal/admin-only models that are explicitly annotated with `__compliance_exempt__ = True` (for any legitimate internal use where raw data may be returned to admin users in a future feature; no such model exists at MVP).

**Integration assertions** (against the running test application):
- Enumerate all GET routes in the FastAPI app that return JSON.
- For each route that can be called with a predictable set of parameters (seeded test data), call it with an authenticated `end_user` token and assert the response body does not contain any of the five OHLCV field names at any nesting depth.
- Routes that require path parameters (e.g. `{company_id}`) are called with seeded test entity IDs.
- Routes that are admin-only are tested with an admin token and checked for OHLCV fields with the same assertion — admin users must also not receive raw prices in API responses.

The test module must be structured to fail clearly with a list of non-compliant endpoints and field names when a violation is detected, not merely as an unspecific assertion failure.

**Tests to write first (TDD)**:
- Test the static walker correctly identifies a Pydantic model containing a `close` field as non-compliant.
- Test the static walker correctly passes a Pydantic model containing only `score`, `score_delta`, `percentile_rank`, `sparkline_data`.
- Test the static walker correctly detects a `close` field nested two levels deep in a Pydantic model hierarchy.
- Test the OHLCV field detector on a mock JSON response body containing `{"data": {"open": 150.0}}` returns `["open"]` as violations.
- Test the OHLCV field detector on `{"data": {"score": 72.5, "sparkline_data": [1,2,3]}}` returns no violations.
- Test the OHLCV field detector on a deeply nested JSON body `{"meta": {"price_info": {"high": 155.0}}}` returns `["high"]`.
- Test that the full static assertion suite passes against the current OpenAPI schema (this test will fail if any future endpoint inadvertently exposes raw OHLCV fields — this is the intended regression gate).

**AC covered**: AC-004

---

### TASK-005: Frontend — RecommendationTrackRecord component · M/TDD · src/frontend/company/RecommendationTrackRecord.tsx, src/frontend/company/hooks/useRecommendationTrackRecord.ts, src/frontend/company/CompanyDetailPage.tsx

Implement `RecommendationTrackRecord` as a React 18 component that displays the recommendation history and ex-post accuracy for a given company.

Component layout:
- A collapsible section titled "AI Recommendation Track Record" placed below the current recommendation panel in `CompanyDetailPage`.
- A summary row: "Direction correct (T+1d): X%  |  Direction correct (T+1w): Y%" — shown as "— " when no actuals are available yet.
- A table of `TrackRecordEntry` rows with columns: Date, Signal (action_signal), Confidence (color-coded), Sample Size, T+1d Actual (filled/empty), T+1w Actual (filled/empty), Disclaimer (icon + tooltip when `disclaimer_required=true`).
- When `disclaimer_required=true` on a row, a warning icon is displayed in the Disclaimer column. Hovering or focusing the icon shows the full disclaimer text in a tooltip. The disclaimer text is visible without any user interaction via the `title` attribute on the icon element (fulfilling AC-003's "without requiring user interaction to reveal it" constraint for keyboard/screen reader accessibility).
- Empty state: "No recommendations recorded yet for this company."
- Loading state: skeleton rows.
- Error state: "Could not load track record. Retry."

`useRecommendationTrackRecord(companyId: string, limit = 50)` uses TanStack Query to fetch `GET /api/v1/compliance/track-record/{company_id}?limit={limit}`. Cache key: `["track-record", companyId]`. Stale time: 5 minutes.

Integrate into `CompanyDetailPage.tsx` by adding `<RecommendationTrackRecord companyId={companyId} />` below the existing recommendation section.

**Tests to write first (TDD)**:
- Test `RecommendationTrackRecord` renders the summary row with correct T+1d percentage when actuals are present.
- Test `RecommendationTrackRecord` renders "— " for T+1d and T+1w when `direction_correct_t1d_pct` and `direction_correct_t1w_pct` are `null`.
- Test `RecommendationTrackRecord` renders a table row for each `TrackRecordEntry`.
- Test that a row with `disclaimer_required=true` renders the warning icon with the disclaimer text accessible via `title` attribute.
- Test that a row with `disclaimer_required=false` does not render a warning icon.
- Test `RecommendationTrackRecord` renders the empty state message when `entries=[]`.
- Test `RecommendationTrackRecord` renders skeleton rows during loading.
- Test `useRecommendationTrackRecord` fetches the correct URL including `company_id` path segment and `limit` query param.
- Test `useRecommendationTrackRecord` with a mocked API error sets `isError=true`.

**AC covered**: AC-001, AC-003

---

### TASK-006: Integration tests — end-to-end compliance flows · M/TDD · tests/compliance/test_episodic_coverage.py, tests/compliance/test_disclaimer_middleware.py, tests/compliance/test_track_record_api.py

Write integration tests that exercise the full compliance stack against a real PostgreSQL test instance.

`test_episodic_coverage.py` (integration):
- Seed 10 `workflow_run` rows with `status='done'`; seed `agent_invocation` rows for 8 of them.
- Call `ComplianceCheckService.run_coverage_check(lookback_days=90)`.
- Assert `coverage_pct = 80.0`, `runs_with_zero_invocations = 2`, `gaps` contains exactly the 2 workflow IDs with no invocations.
- Seed 2 more `agent_invocation` rows for the 2 gap runs.
- Call `run_coverage_check` again.
- Assert `coverage_pct = 100.0`, `gaps = []`.

`test_disclaimer_middleware.py` (integration via ASGI test client):
- Mount the full FastAPI app (with DisclaimerMiddleware registered) in the test client.
- Seed and expose a test endpoint that returns `{"sample_size": 3, "action_signal": "HOLD"}`.
- Assert the response body contains `"disclaimer": "Based on fewer than 5 historical cases — treat with caution"`.
- Assert a test endpoint returning `{"sample_size": 10, "action_signal": "HOLD"}` does NOT contain `"disclaimer"`.
- Assert a test endpoint returning `{"recommendations": [{"sample_size": 2}, {"sample_size": 8}]}` injects disclaimer only into the first nested object.

`test_track_record_api.py` (integration):
- Seed 5 `ai_recommendation` rows for a company with varying `sample_size` and `confidence`.
- Seed `recommendation_outcome` rows for 3 of them with `actual_t1d` filled.
- Authenticate as `end_user`.
- `GET /api/v1/compliance/track-record/{company_id}` — assert 5 entries, `total=5`, `direction_correct_t1d_pct` is computed over the 3 with actuals.
- Assert entries with `sample_size < 5` have `disclaimer_required=True`.
- Assert unauthenticated request returns 401.

**Tests to write first (TDD)**:
- All tests in this task are themselves the TDD artifacts; they drive correctness of the integration across layers.

**AC covered**: AC-001, AC-003, AC-004

## Acceptance Criteria Coverage

- AC-001: Given any agent invocation in any workflow, an agent_invocation row is present in PostgreSQL within 5 seconds of the invocation completing, with all required fields → TASK-001, TASK-003, TASK-006 (coverage check detects any gap; layer 1 tables owned by PLAN-F-015)
- AC-002: Given an admin selects any AI decision in the audit console and clicks "Replay", all tool calls and intermediate outputs are displayed in chronological step-through order → TASK-001 (coverage check ensures the data is complete; replay UI owned by PLAN-F-029; this plan verifies data quality feeding that UI)
- AC-003: Given any display surface shows a recommendation with sample_size < 5, the disclaimer text is present and visible without requiring user interaction → TASK-002, TASK-003, TASK-005, TASK-006
- AC-004: Given a search of the application codebase and database for raw OHLCV price data served to end users, only derived representations are found → TASK-004

## Acceptance Notes

- AC-002 replay functionality is implemented by PLAN-F-029 (Admin AI Audit Console TASK-005 and TASK-006). This plan's contribution to AC-002 is the coverage integrity check in TASK-001, which ensures that the data the replay UI reads is 100% complete. The plan is marked as covering AC-002 because, without this plan, there is no mechanism to detect and alert on coverage gaps.
- The disclaimer injection by `DisclaimerMiddleware` (TASK-002) covers the API layer (alert JSON, side panel API, brief API). The email dispatch path in `src/alerts/` composes alert content from the `alert.content` field, which already contains the disclaimer when the content was serialized through the API layer. If the email composer reads directly from the DB (bypassing the middleware), it must apply the same threshold check inline. This dual-path risk is documented in Risks and Notes.
- TASK-004's derived-data-only suite is a regression gate — it will correctly flag violations from future PRs. It should be added to the CI test run as a separate test stage labeled `compliance`.

## Risks and Notes

- **Email path disclaimer bypass**: The `DisclaimerMiddleware` intercepts HTTP responses. If the email dispatch path (SendGrid) constructs alert content by reading `ai_recommendation.rationale` directly from the database (bypassing the FastAPI response layer), the disclaimer will not be injected automatically. TASK-002 must document this and the email alert template in `src/alerts/` must include an explicit `if recommendation.sample_size < threshold: inject disclaimer` check. This dual-path risk should be surfaced to the dev-executor during TASK-002 implementation.
- **Middleware performance**: Body buffering in `DisclaimerMiddleware` reads the full response into memory before re-streaming. For large responses (e.g. bulk screener results), this adds latency and memory pressure. The middleware should short-circuit early (before buffering) if the request path does not match any recommendation-bearing endpoint pattern (e.g. only apply to paths containing `/recommendation`, `/alert`, `/brief`, or `/analysis`). This path-prefix guard can be added as a configurable setting `DISCLAIMER_MIDDLEWARE_PATH_PREFIXES`.
- **IRecommendationRepository scope**: TASK-003 defines a narrow `IRecommendationRepository` reading from the `ai_recommendation` table. The `ai_recommendation` table is populated by PLAN-F-006 (Morning Brief), PLAN-F-007 (On-Demand), PLAN-F-008 (Watchlist Scan), PLAN-F-009 (Earnings Brief), and PLAN-F-010 (Event Deep-Dive). Until those plans are executed, the track record endpoint will return empty lists, which is expected behavior. Integration tests seed rows directly.
- **OHLCV field name collision**: The field names `open`, `high`, `low`, `close`, `volume` are common English words. The TASK-004 static walker must check field names only on response models registered in the OpenAPI schema, not on all Pydantic models in the codebase (internal models and DB ORM models legitimately use these names). Scope the check to `app.openapi()["components"]["schemas"]` to avoid false positives.
- **Coverage check `workflow_run` status filtering**: The episodic coverage check in TASK-001 only interrogates completed runs (`status IN ('done', 'failed')`). In-progress runs may not yet have all invocations written. The 5-second AC-001 target is enforced at the application level (PLAN-F-015 writes the invocation row immediately after the agent returns); this plan's check operates on a post-hoc hourly basis and is the audit mechanism, not the enforcement mechanism.
- **`direction_sign` computation in track record**: The track record `direction_correct` computation requires knowing the directional intent of each `action_signal` (e.g. `BUY_OPP` and `HEDGE` have opposite directional expectations). Define a `SIGNAL_DIRECTION_MAP: dict[str, int]` in `compliance_schemas.py` as `{"BUY_OPP": 1, "CONTRARIAN": 1, "HOLD": 0, "WATCH": 0, "REDUCE_RISK": -1, "HEDGE": -1}`. `HOLD` and `WATCH` have direction 0 and are excluded from the percentage calculation (correct for neither direction).
