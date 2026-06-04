---
plan_id: PLAN-F-023
slug: company-detail-and-on-demand
title: Company Detail Screen and On-Demand Analysis Trigger
linked_requirement: REQ-F-023
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-007, reason: "on-demand-analysis-workflow: POST /api/v1/companies/{company_id}/analysis endpoint and WorkflowNotifier must exist before the Analyze Now button can trigger and receive results" }
  - { id: PLAN-F-017, reason: "scoring-engine-and-indicator-builder: ICompanyScoreRepository.get_history and IScoringProfileRepository must exist; score breakdown data served by scoring service" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-04T00:00:00Z
---

# PLAN-F-023 — Company Detail Screen and On-Demand Analysis Trigger

## Linked Requirement
**REQ-F-023** — Company Detail Screen and On-Demand Analysis Trigger
Status: approved | Jira:

## Objective

Build the Company Detail screen — the deepest drill-down view in StokAI — that aggregates
and displays price history (interactive OHLCV chart), company fundamentals, all custom
scores with per-indicator breakdown, active geo-events, AI analysis history, and a
recommendation track record panel. A single "Analyze Now" button on the screen triggers
the existing on-demand analysis workflow (PLAN-F-007) via `POST /api/v1/companies/{company_id}/analysis`,
shows a loading state, and appends the returned report to the AI analysis history panel
when the WebSocket notification arrives. The backend delivers all screen data through a
single aggregated FastAPI endpoint (`GET /api/v1/companies/{company_id}/detail`) plus the
existing score and recommendation endpoints; all queries are scoped to `tenant_id`.

## Architecture Context

This plan touches Layer 5 (Serving — API) and Layer 6 (Presentation — Frontend).

**Backend (Architecture §5 — api module):**
A new FastAPI router `company_detail_router.py` adds one read-only aggregated endpoint.
It composes data from four existing repositories: `CompanyRepository` (company entity),
`PriceBarRepository` (OHLCV TimescaleDB hypertable), `AiRecommendationRepository`
(introduced in PLAN-F-007 TASK-010), and `EventExposureRepository` (active geo_events
joined through `event_exposure`). Score breakdown data comes from `ICompanyScoreRepository`
and `IIndicatorRepository` (both introduced in PLAN-F-017). All repository queries include
`tenant_id` for multi-tenancy enforcement (Architecture §12.3).

**Frontend (Architecture §11):**
A new React page at route `/company/:companyId` uses TanStack Query for parallel data
fetching. Charts use Recharts or visx as mandated by Architecture §11. The "Analyze Now"
button calls the existing workflow trigger endpoint from PLAN-F-007 and subscribes to the
WebSocket channel for the returned `workflow_id`. No new WebSocket infrastructure is
introduced — the plan reuses `WorkflowNotifier` from PLAN-F-007.

**Data model (Architecture §10):**
The plan reads but does not mutate: `company`, `price_bar` (TimescaleDB hypertable),
`geo_event`, `event_exposure`, `indicator`, `company_score`, `ai_recommendation`.
`actual_t1d` and `actual_t1w` fields on `ai_recommendation` (filled by the ex-post
calibration job described in Architecture §9) drive the recommendation track record panel.

## Component Design

### New Components

```
Backend — Module: api (src/api/v1/)
  ├── company_detail_router.py      — GET /api/v1/companies/{company_id}/detail
  └── schemas/
      └── company_detail.py         — CompanyDetailResponse, FundamentalsPanel,
                                       ScoreBreakdownItem, ActiveEventSummary,
                                       AnalysisHistoryItem, TrackRecordItem
                                       (Pydantic response DTOs, no business logic)

Backend — Module: storage (src/storage/repositories/)
  └── price_bar_repository.py       — IPriceBarRepository protocol + implementation
                                       (get_ohlcv_history by company_id + time range)

Frontend — src/frontend/pages/
  └── CompanyDetail/
      ├── CompanyDetailPage.tsx          — Route container; orchestrates parallel queries
      ├── PriceChartPanel.tsx            — Interactive OHLCV chart (Recharts ComposedChart);
      │                                    event markers (vertical reference lines);
      │                                    score-change markers; configurable time range
      ├── FundamentalsPanel.tsx          — P/E, EPS, Revenue, Debt/Equity display tiles
      ├── ScoreBreakdownPanel.tsx        — Per-indicator score card with formula summary,
      │                                    weight, sub-score contribution, 30-day sparkline
      ├── ActiveEventsPanel.tsx          — List of active geo_events; each links to map
      │                                    popup via shared MapContext
      ├── AnalysisHistoryPanel.tsx       — Scrollable list of past ai_recommendations;
      │                                    real-time append via WebSocket
      ├── TrackRecordPanel.tsx           — Past signals with actual_t1d outcomes;
      │                                    directional accuracy summary line
      ├── AnalyzeNowButton.tsx           — "Analyze Now" button; manages loading/disabled
      │                                    state; subscribes to workflow WebSocket channel
      └── hooks/
          ├── useCompanyDetail.ts        — TanStack Query: parallel fetch of all panels
          ├── useAnalyzeNow.ts           — POST trigger + WebSocket subscription management
          └── useScoreHistory.ts         — Fetches 30-day sparkline data per indicator

Tests:
tests/unit/api/
  └── test_company_detail_router.py

tests/unit/storage/
  └── test_price_bar_repository.py

tests/integration/api/
  └── test_company_detail_endpoint.py

tests/unit/frontend/CompanyDetail/
  ├── test_AnalyzeNowButton.tsx
  ├── test_ScoreBreakdownPanel.tsx
  ├── test_TrackRecordPanel.tsx
  └── test_useAnalyzeNow.ts
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/v1/__init__.py` | Register `company_detail_router` | Expose the new aggregated endpoint |
| `src/storage/repositories/__init__.py` | Export `IPriceBarRepository`, `PriceBarRepository` | Make repository available for injection |
| `src/frontend/App.tsx` (or router config) | Add `/company/:companyId` route pointing to `CompanyDetailPage` | Mount the new page |

### Interfaces and Contracts

```python
# src/storage/repositories/price_bar_repository.py

from typing import Protocol
from uuid import UUID
from datetime import datetime

class PriceBar(BaseModel):
    company_id: UUID
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    interval: str   # "1d" | "1h" | "15m"

class IPriceBarRepository(Protocol):
    async def get_ohlcv_history(
        self,
        company_id: UUID,
        tenant_id: UUID,
        interval: str,
        from_ts: datetime,
        to_ts: datetime,
        limit: int = 500,
    ) -> list[PriceBar]: ...
```

```python
# src/api/v1/schemas/company_detail.py

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class FundamentalsPanel(BaseModel):
    pe_ratio: float | None
    eps: float | None
    revenue: float | None
    debt_to_equity: float | None
    source: str                    # "fmp" | "edgar" | "cross_validated"
    as_of: datetime

class ScoreBreakdownItem(BaseModel):
    indicator_id: UUID
    indicator_name: str
    formula_summary: str           # first 120 chars of DSL formula
    weight: float                  # within the active scoring profile
    raw_value: float | None
    score: float                   # 0–100
    geo_adjusted: float | None
    sub_score_contribution: float  # weight * score / 100
    sparkline: list[float]         # last 30 daily score values

class ActiveEventSummary(BaseModel):
    event_id: UUID
    title: str
    occurred_at: datetime
    intensity: int
    category: list[str]
    exposure_magnitude: float      # from event_exposure.magnitude

class AnalysisHistoryItem(BaseModel):
    rec_id: UUID
    generated_at: datetime
    workflow_type: str             # "on_demand" | "morning_brief" | "event_deep_dive"
    action_signal: str             # HOLD | WATCH | BUY_OPP | REDUCE_RISK | HEDGE | CONTRARIAN
    confidence: float
    rationale_summary: str         # first 200 chars of rationale

class TrackRecordItem(BaseModel):
    rec_id: UUID
    generated_at: datetime
    action_signal: str
    direction: str                 # "bullish" | "bearish" | "neutral"
    confidence: float
    actual_t1d: float | None       # % price change T+1d; None if not yet filled
    actual_t1w: float | None
    correct_t1d: bool | None       # direction correct vs actual_t1d sign
    correct_t1w: bool | None

class CompanyDetailResponse(BaseModel):
    company_id: UUID
    ticker: str
    name: str
    sector: str
    market_cap: float | None
    fundamentals: FundamentalsPanel
    scores: list[ScoreBreakdownItem]
    active_events: list[ActiveEventSummary]
    analysis_history: list[AnalysisHistoryItem]
    track_record: list[TrackRecordItem]
    directional_accuracy_t1d: float | None  # % correct of filled records
```

```python
# src/api/v1/company_detail_router.py  (key signature)

from fastapi import APIRouter, Depends
from uuid import UUID

router = APIRouter(prefix="/api/v1/companies", tags=["company-detail"])

@router.get("/{company_id}/detail", response_model=CompanyDetailResponse)
async def get_company_detail(
    company_id: UUID,
    profile_id: UUID | None = None,   # query param; defaults to user's default profile
    price_interval: str = "1d",       # "1d" | "1h"
    price_from_days: int = 90,        # look-back window in days
    current_user: User = Depends(get_current_user),
) -> CompanyDetailResponse:
    """
    Aggregated Company Detail endpoint. Runs 5 data fetches in parallel via asyncio.gather:
      1. company entity + fundamentals
      2. price_bar OHLCV history
      3. company scores + indicator breakdown + sparklines
      4. active geo_events (last 30 days, exposure magnitude > 0)
      5. ai_recommendation history (last 20 records)
    Returns tenant-scoped data only. Returns 404 if company not found for tenant.
    Returns 403 if company exists but does not belong to tenant's tracked universe.
    """
    ...
```

```typescript
// src/frontend/pages/CompanyDetail/hooks/useAnalyzeNow.ts (key signature)

interface UseAnalyzeNowResult {
  triggerAnalysis: () => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

// Calls POST /api/v1/companies/{companyId}/analysis
// On success, stores run_id and subscribes to WebSocket channel for that workflow_id
// On message received, calls onReportReady(analysisHistoryItem) which the parent
// uses to prepend the new item to AnalysisHistoryPanel
export function useAnalyzeNow(
  companyId: string,
  onReportReady: (item: AnalysisHistoryItem) => void,
): UseAnalyzeNowResult
```

## Implementation Tasks

### TASK-001: PriceBarRepository — IPriceBarRepository protocol and TimescaleDB implementation · M/TDD · src/storage/repositories/price_bar_repository.py,src/storage/repositories/__init__.py,tests/unit/storage/test_price_bar_repository.py,tests/integration/storage/test_price_bar_repository.py

Implement `IPriceBarRepository` protocol and `PriceBarRepository` using SQLAlchemy 2.0
async session. The `get_ohlcv_history` method queries the `price_bar` TimescaleDB hypertable
(partitioned by `ts`) with a compound WHERE clause: `company_id = :cid AND tenant_id = :tid
AND interval = :interval AND ts BETWEEN :from_ts AND :to_ts ORDER BY ts ASC LIMIT :limit`.
The `limit` parameter is capped internally at 1000 rows to honour the tool library bounded-output
principle (Architecture §7.3). The method must include `tenant_id` in every query — the
`price_bar` table is tenant-scoped (Architecture §12.3). The `PriceBar` response schema maps
directly to `price_bar` columns; no business logic.

**Tests to write first (TDD):**
- `test_get_ohlcv_history_returns_bars_in_asc_ts_order` — insert 3 bars at different timestamps; assert returned list is sorted by `ts` ascending
- `test_get_ohlcv_history_filters_by_tenant_id` — insert bars for two tenants; assert only requesting tenant's bars returned
- `test_get_ohlcv_history_filters_by_interval` — insert "1d" and "1h" bars; assert only "1d" returned when requested
- `test_get_ohlcv_history_respects_from_to_range` — insert bars outside the range; assert they are excluded
- `test_get_ohlcv_history_caps_at_internal_limit` — request `limit=2000`; assert at most 1000 rows returned
- `test_get_ohlcv_history_empty_result_returns_empty_list` — no bars for company returns `[]` without raising

**AC covered**: AC-001

---

### TASK-002: Company Detail response schemas and aggregated API endpoint · M/TDD · src/api/v1/company_detail_router.py,src/api/v1/schemas/company_detail.py,src/api/v1/__init__.py,tests/unit/api/test_company_detail_router.py,tests/integration/api/test_company_detail_endpoint.py

Implement all Pydantic response DTOs in `company_detail.py` per the contracts in Component
Design. Implement `GET /api/v1/companies/{company_id}/detail` in `company_detail_router.py`.
The endpoint executes five data fetches in parallel using `asyncio.gather`:
1. `CompanyRepository.get_by_id(company_id, tenant_id)` — company entity + fundamentals
2. `IPriceBarRepository.get_ohlcv_history(...)` — OHLCV data
3. `ICompanyScoreRepository.get_current` + `IIndicatorRepository` lookups — scores + breakdown
4. `EventExposureRepository.get_active_for_company(company_id, tenant_id, days=30)` — active events
5. `AiRecommendationRepository.list_for_company(company_id, tenant_id, limit=20)` — analysis history

`directional_accuracy_t1d` is computed inline from track record items where `actual_t1d`
is not None: `sum(correct_t1d) / count(filled records)`. Score sparklines (last 30 daily
values) are fetched via `ICompanyScoreRepository.get_history(limit=30)` for each indicator,
concurrently inside the scores gather call.

The endpoint enforces: JWT authentication; tenant ownership of the company (404 if
`company.is_tracked = False` for this tenant or company does not exist); `profile_id`
defaults to `current_user.scoring_profile_default` when not supplied as a query param.
Register the router in `src/api/v1/__init__.py`.

**Tests to write first (TDD):**
- `test_endpoint_returns_200_with_all_panels` — mock all five repositories; assert response contains all top-level keys of `CompanyDetailResponse`
- `test_endpoint_404_for_unknown_company_id` — company not found for tenant returns 404
- `test_endpoint_401_without_jwt` — unauthenticated request returns 401
- `test_endpoint_scopes_data_to_tenant` — asserts every repository call receives the authenticated user's `tenant_id`
- `test_endpoint_directional_accuracy_computed_correctly` — 3 filled records, 2 correct → accuracy 0.667
- `test_endpoint_uses_default_profile_when_profile_id_not_supplied` — asserts score lookup uses `current_user.scoring_profile_default`
- `test_endpoint_parallel_fetches_via_asyncio_gather` — mock `asyncio.gather`; assert it is awaited once with five coroutines (not sequential awaits)

**AC covered**: AC-001, AC-003, AC-004

---

### TASK-003: Score breakdown panel data — formula summary and sub-score contribution · M/TDD · src/api/v1/company_detail_router.py,src/api/v1/schemas/company_detail.py,tests/unit/api/test_company_detail_router.py

Extend the aggregated endpoint (TASK-002) to populate the `ScoreBreakdownItem` list.
For each active indicator in the user's scoring profile: fetch the current `company_score`
row (score, raw_value, geo_adjusted, inputs_hash), the `indicator` record (name,
formula_dsl, geo_weight), and the 30-day sparkline via `ICompanyScoreRepository.get_history`.
Map the profile's per-indicator weight to `weight` and compute
`sub_score_contribution = weight * score / 100.0`. Truncate `formula_dsl` to 120 characters
for `formula_summary`; append `"..."` if truncated. The sparkline list must be ordered
oldest-to-newest so the frontend can render it left-to-right without sorting.

This task extends TASK-002's endpoint; it does not introduce a new endpoint. If a
`company_score` row does not exist for an indicator (score not yet computed), emit a
`ScoreBreakdownItem` with `score=0.0`, `raw_value=None`, `sparkline=[]`, and
`sub_score_contribution=0.0` rather than omitting the indicator.

**Tests to write first (TDD):**
- `test_score_breakdown_truncates_formula_at_120_chars` — DSL string of 150 chars produces `formula_summary` of 123 chars ending in `"..."`
- `test_score_breakdown_sub_score_contribution_calculation` — weight 0.4, score 75.0 → contribution 0.30
- `test_score_breakdown_missing_score_row_yields_zero_defaults` — `get_current` returns `None`; item has `score=0.0`, `sparkline=[]`
- `test_score_breakdown_sparkline_is_oldest_first` — insert rows with timestamps t1 < t2 < t3; sparkline list order is `[t1_score, t2_score, t3_score]`
- `test_score_breakdown_all_indicators_in_profile_present` — profile with 3 indicators; response has exactly 3 `ScoreBreakdownItem` entries

**AC covered**: AC-004

---

### TASK-004: Recommendation track record panel data · S/no-TDD · src/api/v1/company_detail_router.py,src/api/v1/schemas/company_detail.py

Extend the aggregated endpoint to populate the `track_record` list and the
`directional_accuracy_t1d` summary field. The track record is sourced from
`AiRecommendationRepository.list_for_company` (already fetched in TASK-002 gather call);
no additional DB query is needed. For each `ai_recommendation` row, map to `TrackRecordItem`:
- `direction` is derived from `action_signal`: BUY_OPP → "bullish"; REDUCE_RISK, HEDGE →
  "bearish"; HOLD, WATCH, CONTRARIAN → "neutral"
- `correct_t1d` = `True` when direction is "bullish" and `actual_t1d > 0`, or direction is
  "bearish" and `actual_t1d < 0`; `False` otherwise; `None` when `actual_t1d` is `None`
- `correct_t1w` computed analogously from `actual_t1w`

`directional_accuracy_t1d = sum(correct_t1d for items where correct_t1d is not None) /
count(items where correct_t1d is not None)`; returns `None` when no filled records exist.

This task is S complexity because it performs pure mapping logic with no new I/O, branching
entirely within the endpoint layer.

**AC covered**: AC-003

---

### TASK-005: CompanyDetailPage — React page with all panels · L/TDD · src/frontend/pages/CompanyDetail/CompanyDetailPage.tsx,src/frontend/pages/CompanyDetail/PriceChartPanel.tsx,src/frontend/pages/CompanyDetail/FundamentalsPanel.tsx,src/frontend/pages/CompanyDetail/ScoreBreakdownPanel.tsx,src/frontend/pages/CompanyDetail/ActiveEventsPanel.tsx,src/frontend/pages/CompanyDetail/AnalysisHistoryPanel.tsx,src/frontend/pages/CompanyDetail/TrackRecordPanel.tsx,src/frontend/pages/CompanyDetail/hooks/useCompanyDetail.ts,src/frontend/pages/CompanyDetail/hooks/useScoreHistory.ts,src/frontend/App.tsx

Implement the full Company Detail page layout and all read-only display panels. The page
mounts at `/company/:companyId` and is reachable from the Intelligence Map's progressive
disclosure flow. `useCompanyDetail` uses TanStack Query to fetch `GET /api/v1/companies/{companyId}/detail`
with stale time of 60 seconds; the query key includes `companyId` and `activeProfileId`
from `ActiveProfileContext` (introduced in PLAN-F-017 TASK-018), so a profile switch
automatically refreshes scores.

**PriceChartPanel**: `Recharts ComposedChart` (candlestick via `Bar` + `Line` for close).
Active events rendered as vertical `ReferenceLine` markers at `occurred_at` timestamps.
Score change markers rendered as `ReferenceLine` at `computed_at` timestamps from the
sparkline data. A time-range selector (buttons: 1W, 1M, 3M, 1Y) passes `price_from_days`
as a query param refetch. No WebSocket; price data is fetched on mount and on range change.

**FundamentalsPanel**: Four metric tiles (P/E, EPS, Revenue, Debt/Equity) with a "source"
badge (FMP / EDGAR / cross-validated). Null metric renders as "—".

**ScoreBreakdownPanel**: One card per `ScoreBreakdownItem`. Each card shows indicator name,
formula summary (truncated, with a tooltip showing the full DSL), weight badge, score meter
(0–100), geo_adjusted badge (shown only when `geo_adjusted != score`), sub-score contribution,
and a 30-day sparkline (Recharts `Sparkline`).

**ActiveEventsPanel**: List of `ActiveEventSummary` items. Each item shows intensity badge,
category tags, event title, occurred_at. Clicking an item dispatches a URL navigation to
`/?eventId={event_id}` (the Intelligence Map) so the map focuses on that event pulse.

**AnalysisHistoryPanel**: Scrollable list of `AnalysisHistoryItem`. Action signal rendered
as a coloured badge (BUY_OPP=green, REDUCE_RISK=red, WATCH=amber, etc.). New items prepended
in real-time by `useAnalyzeNow` callback without a page refetch.

**TrackRecordPanel**: Table of `TrackRecordItem`. `correct_t1d` shown as a checkmark or
cross icon; null shown as "—". Directional accuracy summary displayed at top of panel as
"Directional accuracy (T+1d): 72%"; hidden when `directional_accuracy_t1d` is `null`.

Register the `/company/:companyId` route in `src/frontend/App.tsx`.

**Tests to write first (TDD):**
- `useCompanyDetail` — mock `fetch`; assert TanStack Query makes one GET to `/api/v1/companies/{id}/detail`; loading=true before response
- `useCompanyDetail` — assert query key includes `activeProfileId`; profile change causes refetch
- `PriceChartPanel` renders without crashing with empty `priceHistory` array (loading state guard)
- `FundamentalsPanel` renders "—" for null `pe_ratio`
- `ScoreBreakdownPanel` renders one card per score item; formula tooltip present
- `ActiveEventsPanel` clicking an event item navigates to map URL with `eventId` param
- `AnalysisHistoryPanel` renders action signal badges with correct colour class per signal type
- `TrackRecordPanel` renders accuracy summary line; hidden when `directional_accuracy_t1d` is null

**AC covered**: AC-001, AC-003, AC-004

---

### TASK-006: AnalyzeNowButton — trigger, loading state, and WebSocket result delivery · M/TDD · src/frontend/pages/CompanyDetail/AnalyzeNowButton.tsx,src/frontend/pages/CompanyDetail/hooks/useAnalyzeNow.ts,tests/unit/frontend/CompanyDetail/test_AnalyzeNowButton.tsx,tests/unit/frontend/CompanyDetail/test_useAnalyzeNow.ts

Implement `useAnalyzeNow` hook and `AnalyzeNowButton` component.

`useAnalyzeNow` flow:
1. On `triggerAnalysis()`: POST `POST /api/v1/companies/{companyId}/analysis`; set `isLoading=true`
2. Store returned `run_id` and subscribe to the WebSocket channel for that workflow
3. On `workflow.status === "COMPLETED"` message: parse the report into an `AnalysisHistoryItem`
   and call `onReportReady(item)`; set `isLoading=false`
4. On `workflow.status === "HIL_PENDING"`: still call `onReportReady` (with a low-confidence banner
   flag in the item); set `isLoading=false`
5. On `workflow.status === "BLOCKED"` or error: set `error` message; set `isLoading=false`
6. On component unmount with active subscription: unsubscribe (WebSocket cleanup)
7. While `isLoading=true`, disable the button and show a spinner label "Analyzing..."
8. A 409 response from the trigger endpoint (another analysis already in progress) shows
   inline message "Analysis already in progress" without entering loading state

`AnalyzeNowButton` is a controlled component: it reads `isLoading` and `error` from
`useAnalyzeNow` and exposes no internal state of its own. Button label: "Analyze Now"
(default) → "Analyzing..." (loading). Button is disabled when `isLoading=true`.

**Tests to write first (TDD):**
- `test_use_analyze_now_triggers_post_on_call` — mock fetch; `triggerAnalysis()` → POST to correct URL
- `test_use_analyze_now_sets_is_loading_true_after_trigger` — `isLoading` is true immediately after POST response
- `test_use_analyze_now_subscribes_to_websocket_with_run_id` — mock WebSocket; assert subscription opened with `run_id`
- `test_use_analyze_now_calls_on_report_ready_on_completed_message` — WebSocket mock emits `{status: "COMPLETED"}`; asserts `onReportReady` called with parsed item
- `test_use_analyze_now_sets_is_loading_false_on_result` — after WebSocket message received, `isLoading=false`
- `test_use_analyze_now_409_sets_error_without_loading` — fetch returns 409; `isLoading` stays false; `error` is set
- `test_analyze_now_button_shows_spinner_when_loading` — renders with `isLoading=true`; button text is "Analyzing..."
- `test_analyze_now_button_disabled_when_loading` — button has `disabled` attribute when loading

**AC covered**: AC-002

---

## Acceptance Criteria Coverage

- AC-001: Company Detail page displays price chart, fundamentals, all custom scores with indicator breakdown, active events, and AI analysis history → TASK-001, TASK-002, TASK-003, TASK-005
- AC-002: "Analyze Now" triggers on-demand analysis; loading indicator shown; report appended to AI analysis history when complete → TASK-006
- AC-003: Recommendation Track Record shows directional accuracy for past calls with actual_t1d data → TASK-002, TASK-004, TASK-005
- AC-004: Score breakdown panel shows each indicator's name, formula summary, weight, and sub-score contribution → TASK-002, TASK-003, TASK-005

## Acceptance Notes

The `actual_t1d` and `actual_t1w` fields on `ai_recommendation` rows are filled by the
ex-post calibration job described in Architecture §9 (Tier 3). At the time a recommendation
is first created, these fields are `null`. The track record panel must render gracefully when
all records have `null` outcome data: the accuracy summary line is hidden and each row shows
"—" in the outcome columns. No special handling or fallback is needed beyond the null-guard
already specified in TASK-004.

The "Analyze Now" button produces a 409 when another on-demand analysis for the same company
is already `RUNNING` (enforced by the PLAN-F-007 TASK-008 rate-limit check). The frontend
must surface this as an inline message rather than disabling the button permanently, because
the running analysis will eventually complete and update the history panel via WebSocket.

## Risks and Notes

- The aggregated endpoint (TASK-002) fetches sparklines for every indicator in the active
  profile inside the scores gather call. For a profile with many indicators (e.g. 10+), this
  becomes 10 parallel `get_history` queries. Use `asyncio.gather` for sparklines within the
  scores sub-gather. If the profile has more than 20 indicators, log a warning — this is a
  signal to introduce a dedicated batch-sparkline endpoint later.
- PLAN-F-017 `ICompanyScoreRepository.get_history` is called with `limit=30` for sparklines.
  The `company_score` TimescaleDB hypertable stores event-driven snapshots (D4), not daily
  snapshots. A company with infrequent score changes may return fewer than 30 rows; the sparkline
  renders however many points are available. The frontend should not assume 30 points are always
  present.
- The OHLCV chart's event markers depend on `ActiveEventSummary.occurred_at` overlapping the
  visible price history time window. If the user selects a short time range (1W) and all active
  events occurred outside that window, no markers appear. This is correct behaviour; no special
  warning is needed.
- `useAnalyzeNow` subscribes to the WebSocket channel for a single `run_id`. If the user navigates
  away before the workflow completes, the React cleanup function must unsubscribe to prevent memory
  leaks and stale-closure callbacks. This is enforced by the test `test_analyze_now_button_disabled_when_loading`
  indirectly, but the executor should also test the cleanup path explicitly.
- Score breakdown panel shows `formula_summary` (truncated DSL). The full DSL is shown in a
  tooltip on hover. The tooltip must be keyboard-accessible (title attribute or aria-describedby)
  to meet basic accessibility requirements. This is not a hard blocker but should be implemented
  in TASK-005.
- `AiRecommendationRepository.list_for_company` (introduced in PLAN-F-007 TASK-010) returns
  up to `limit=20` recommendations ordered by `generated_at DESC`. The endpoint reuses this
  same list for both `analysis_history` (display all 20) and `track_record` (filter to those
  with `actual_t1d` or `actual_t1w` filled). No second DB query is needed for track record.
