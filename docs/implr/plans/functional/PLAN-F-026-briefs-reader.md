---
plan_id: PLAN-F-026
slug: briefs-reader
title: Briefs and Reports Reader
linked_requirement: REQ-F-026
type: functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "tenant_id + user_id ownership check on every brief and feedback lookup; IDOR prevention" }
  - { id: REQ-N-014, reason: "Brief HTML content rendered in a responsive, accessible layout; confidence and disclaimer displayed at all viewport widths" }
dependencies:
  - { id: PLAN-F-006, reason: "workflow_run rows for morning_brief type are the source records rendered by this reader" }
  - { id: PLAN-F-015, reason: "Layer 4 IFeedbackRepository.append_feedback() is the write path for all user feedback captured here" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-026 — Briefs and Reports Reader

## Linked Requirement
**REQ-F-026** — Briefs and Reports Reader
Status: approved | Jira: —

## Objective

Build the Briefs Reader: a FastAPI REST layer and a React 18 + TypeScript frontend section
that displays all four brief types (Morning Brief, Watchlist Scan, Earnings Brief, Event
Deep-Dive) produced by Mode B workflows. Each brief entry in the list exposes type, date,
headline, confidence, and delivery status. Opening a brief renders its full HTML content with
confidence and sample size shown prominently in the header; when sample_size < 5 the body
includes an inline low-sample disclaimer. Every brief carries thumbs-up / thumbs-down / edit
feedback controls that immediately write a `user_feedback` row to the Layer 4 memory table
via `IFeedbackRepository`. An edit correction additionally writes a `golden_dataset_candidate`
record visible in the Admin AI Audit Console (PLAN-F-029). The backend reads brief content
from the `workflow_run` table (Layer 1 episodic memory) and exposes it through a paginated,
filterable `/api/v1/briefs` endpoint. This plan owns only the reader surface and its feedback
write path; brief generation remains in PLAN-F-006 and the sibling workflow plans.

## Architecture Context

This plan spans two layers of the six-layer system model:

- **Layer 5 — Serving**: two new FastAPI routers under `src/api/briefs/` for brief listing /
  detail retrieval and feedback submission.
- **Layer 6 — Presentation**: a new `BriefsReader` React section with a list view, a detail
  view, and an inline feedback widget.

**Data sources (read-only for this plan):**
- `workflow_run` (Architecture §10 — Agentic Layer Tables): holds `workflow_type`,
  `final_state` (JSONB, contains brief HTML content, confidence, sample_size, low_sample
  flag, headline, sent_at), `status`, `completed_at`, `tenant_id`.
- The brief content model does not introduce a separate `brief` table; briefs are a
  projection of `workflow_run` rows where `workflow_type IN ('morning_brief',
  'watchlist_scan', 'earnings_brief', 'event_deep_dive')`.

**Data writes:**
- `user_feedback` (Architecture §10 — Agentic Layer Tables via PLAN-F-015 Layer 4):
  written through `IFeedbackRepository.append_feedback()` from the feedback service. The
  architecture schema has `report_id` (maps to `workflow_run.workflow_id`) and
  `recommendation_id` (null for brief-level feedback). The requirement's `decision_ref`
  field corresponds to `report_id` in the DB schema.
- `golden_dataset_candidate`: a new table (introduced by this plan) written when
  `feedback_type = edit`; consumed by PLAN-F-029 Admin AI Audit Console.

**Relevant ARCHITECTURE.md sections:**
- §7.4 Four-Layer Memory Subsystem — Layer 1 stores workflow_run; Layer 4 stores
  user_feedback.
- §7.5 Five Core Workflows — brief types and their workflow_type values.
- §10 Data Model — `workflow_run`, `user_feedback` schemas.
- §11 Frontend Architecture — React 18 + TypeScript, TanStack Query for data fetching.
- §5 Backend Module Map — `api` module owns HTTP routing; `storage` module owns DB access.
- §12.1 Authentication — JWT required; tenant_id + user_id ownership checked on every lookup.

**Layering rule:** `BriefService` calls `BriefRepository` and `FeedbackRepository`
(from PLAN-F-015). No router writes SQL. No service imports concrete repository classes
directly — only injected interfaces.

## Component Design

### New Components

```
Module: api/briefs  (src/api/briefs/)
  ├── briefs_router.py          — FastAPI router: GET /api/v1/briefs, GET /api/v1/briefs/{id}
  ├── feedback_router.py        — FastAPI router: POST /api/v1/briefs/{id}/feedback
  └── briefs_schemas.py         — Request/response Pydantic models (BriefListItem,
                                   BriefDetail, FeedbackRequest, FeedbackResponse)

Module: briefs  (src/briefs/)
  ├── interfaces/
  │   ├── i_brief_repository.py — IBriefRepository (abstract)
  │   └── i_brief_service.py    — IBriefService (abstract)
  ├── repositories/
  │   └── brief_repository.py   — BriefRepository — queries workflow_run table; extracts
  │                                brief projection; SQLAlchemy 2.0 async
  ├── services/
  │   ├── brief_service.py      — BriefService — list, detail, ownership check; maps
  │                                workflow_run → BriefDetail DTO; applies low_sample flag
  │   └── brief_feedback_service.py  — BriefFeedbackService — validates feedback payload;
  │                                    calls IFeedbackRepository.append_feedback();
  │                                    on edit: writes golden_dataset_candidate row
  ├── models/
  │   └── brief_models.py       — SQLAlchemy ORM: GoldenDatasetCandidate (new table)
  ├── schemas/
  │   └── brief_schemas.py      — Pydantic domain DTOs: BriefProjection, BriefFeedbackCreate
  └── __init__.py

Frontend: src/frontend/src/features/briefs/
  ├── BriefsPage.tsx            — Route container; renders BriefsList + pagination
  ├── BriefsList.tsx            — Sorted list of brief entries (reverse chrono)
  ├── BriefListItem.tsx         — Single row: type badge, date, headline, confidence,
  │                               delivery status; links to BriefDetailPage
  ├── BriefDetailPage.tsx       — Full brief: confidence header block, HTML content via
  │                               SafeHtmlRenderer, low-sample disclaimer, FeedbackWidget
  ├── SafeHtmlRenderer.tsx      — DOMPurify-sanitized HTML renderer for brief content
  ├── FeedbackWidget.tsx        — Thumbs-up / thumbs-down / edit controls; edit opens
  │                               inline correction textarea; calls useFeedback hook
  ├── hooks/
  │   ├── useBriefs.ts          — TanStack Query: GET /api/v1/briefs (paginated, filterable)
  │   ├── useBriefDetail.ts     — TanStack Query: GET /api/v1/briefs/{id}
  │   └── useFeedback.ts        — TanStack Mutation: POST /api/v1/briefs/{id}/feedback
  └── briefs.types.ts           — TypeScript types matching API response DTOs

Alembic migration:
  alembic/versions/XXXX_add_golden_dataset_candidate.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/router.py` | Register `briefs_router` and `feedback_router` | Wire new routes into the FastAPI application |
| `src/frontend/src/App.tsx` | Add `/briefs` and `/briefs/:id` routes | Navigate to the Briefs section from the sidebar |
| `src/frontend/src/components/Sidebar.tsx` | Add Briefs navigation link | User entry point to the reader |

### Interfaces and Contracts

```python
# src/briefs/interfaces/i_brief_repository.py

class IBriefRepository(ABC):
    @abstractmethod
    async def list_briefs(
        self,
        tenant_id: UUID,
        brief_type: BriefType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BriefProjection], str | None]: ...
    # Returns (items, next_cursor); sorted by completed_at DESC.

    @abstractmethod
    async def get_brief(
        self, brief_id: UUID, tenant_id: UUID
    ) -> BriefProjection | None: ...
    # Returns None if not found or tenant_id does not match (IDOR prevention).

# src/briefs/interfaces/i_brief_service.py

class IBriefService(ABC):
    @abstractmethod
    async def list_briefs(
        self,
        user_id: UUID,
        tenant_id: UUID,
        brief_type: BriefType | None,
        cursor: str | None,
        limit: int,
    ) -> BriefListResult: ...

    @abstractmethod
    async def get_brief_detail(
        self, brief_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> BriefDetail: ...

    @abstractmethod
    async def submit_feedback(
        self,
        brief_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        payload: BriefFeedbackCreate,
    ) -> None: ...

# BriefType enum
class BriefType(str, Enum):
    morning_brief = "morning_brief"
    watchlist_scan = "watchlist_scan"
    earnings_brief = "earnings_brief"
    event_deep_dive = "event_deep_dive"

# BriefProjection — projection of workflow_run fields
class BriefProjection(BaseModel):
    brief_id: UUID           # workflow_run.workflow_id
    type: BriefType          # workflow_run.workflow_type
    headline: str            # extracted from final_state JSONB
    content_html: str        # extracted from final_state JSONB
    confidence: float        # extracted from final_state JSONB
    sample_size: int         # extracted from final_state JSONB
    low_sample: bool         # sample_size < 5
    delivery_status: str     # workflow_run.status (sent | hil_held | blocked)
    sent_at: datetime | None # workflow_run.completed_at when dispatched

# BriefFeedbackCreate
class BriefFeedbackCreate(BaseModel):
    feedback_type: Literal["thumbs_up", "thumbs_down", "edit"]
    correction: str | None = None   # required when feedback_type == "edit"

# GoldenDatasetCandidate ORM (new table)
class GoldenDatasetCandidate(Base):
    __tablename__ = "golden_dataset_candidate"
    candidate_id: UUID PK
    tenant_id: UUID
    brief_id: UUID          # FK → workflow_run.workflow_id
    user_id: UUID
    original_content: str   # brief content at time of edit
    correction: str
    created_at: datetime
    reviewed: bool DEFAULT false
    review_notes: str | None

# API response envelope (follows §7 success envelope)
# GET /api/v1/briefs
# { "data": { "items": [BriefListItem], "next_cursor": str | null }, "meta": {...}, "error": null }
# GET /api/v1/briefs/{id}
# { "data": BriefDetail, "meta": {...}, "error": null }
# POST /api/v1/briefs/{id}/feedback
# { "data": { "feedback_id": UUID }, "meta": {}, "error": null }
```

## Implementation Tasks

### TASK-001: BriefRepository — workflow_run projection query · M/TDD · src/briefs/interfaces/i_brief_repository.py, src/briefs/repositories/brief_repository.py, src/briefs/models/brief_models.py, src/briefs/schemas/brief_schemas.py

Implement `IBriefRepository` and `BriefRepository` using SQLAlchemy 2.0 async. The repository queries the `workflow_run` table, filtering `workflow_type IN ('morning_brief', 'watchlist_scan', 'earnings_brief', 'event_deep_dive')` and `tenant_id = :tenant_id`. List query uses cursor-based pagination (cursor = base64-encoded `completed_at + workflow_id` composite) ordered by `completed_at DESC`. The JSONB `final_state` column is parsed to extract `headline`, `content_html`, `confidence`, `sample_size`; `low_sample` is computed as `sample_size < 5`. `delivery_status` is mapped from `workflow_run.status`.

`get_brief` enforces `tenant_id` in the WHERE clause and returns `None` for mismatched records; the service layer converts that to a 404 response — never expose whether a record exists to unauthorized callers.

**Tests to write first (TDD):**
- `test_list_briefs_returns_all_four_types_for_tenant` — insert workflow_run rows of each type for tenant A and a different type for tenant B; assert only tenant A's rows are returned.
- `test_list_briefs_cursor_pagination` — insert 15 rows; call list with limit=10, capture cursor; call again with cursor; assert non-overlapping complete set.
- `test_list_briefs_sorted_reverse_chronological` — insert rows with different completed_at; assert returned order is most recent first.
- `test_get_brief_returns_none_for_wrong_tenant` — insert brief for tenant A; call get_brief with tenant_b_id; assert None returned.
- `test_low_sample_flag_set_when_sample_size_less_than_five` — insert workflow_run with sample_size=3; assert projection.low_sample is True.
- `test_low_sample_flag_not_set_when_sample_size_five_or_more` — sample_size=5; assert low_sample is False.

**AC covered:** AC-002 (brief_id/report_id sourced here), AC-004 (low_sample computed here), AC-005 (reverse chronological list, all fields present)

---

### TASK-002: BriefService and BriefFeedbackService · M/TDD · src/briefs/interfaces/i_brief_service.py, src/briefs/services/brief_service.py, src/briefs/services/brief_feedback_service.py

Implement `IBriefService` with `BriefService`. `list_briefs` delegates to `IBriefRepository.list_briefs` and maps projections to `BriefListResult` DTO. `get_brief_detail` fetches from `IBriefRepository.get_brief` and raises `BriefNotFoundError` (maps to HTTP 404) when `None` is returned.

Implement `BriefFeedbackService.submit_feedback`:
1. Validates that if `feedback_type == "edit"`, `correction` is non-null and non-empty (raise `ValidationError` otherwise).
2. Calls `IFeedbackRepository.append_feedback(FeedbackCreate(tenant_id=..., report_id=brief_id, recommendation_id=None, feedback_type=feedback_type, feedback_text=None, user_edit=correction, submitted_at=utcnow()))`.
3. If `feedback_type == "edit"`: writes a `GoldenDatasetCandidate` row via `IGoldenDatasetRepository.create_candidate(...)`.
4. Returns without error; all writes are async; no awaited I/O is held in a tight loop.

All injected collaborators are interfaces, not concrete classes. `BriefFeedbackService` depends on `IFeedbackRepository` (from PLAN-F-015) and `IGoldenDatasetRepository` (new, defined in this task).

**Tests to write first (TDD):**
- `test_submit_thumbs_down_calls_feedback_repository` — mock `IFeedbackRepository`; call submit_feedback with thumbs_down; assert append_feedback called with correct feedback_type and report_id; assert golden_dataset_repository not called.
- `test_submit_edit_calls_both_repositories` — mock both repos; call with edit + correction; assert append_feedback called and create_candidate called with correct brief_id and correction text.
- `test_submit_edit_without_correction_raises_validation_error` — call with feedback_type=edit, correction=None; assert `ValidationError` raised.
- `test_submit_edit_with_empty_correction_raises_validation_error` — correction=""; assert `ValidationError`.
- `test_get_brief_detail_raises_not_found_when_repo_returns_none` — mock repo returns None; assert `BriefNotFoundError` raised.
- `test_list_briefs_returns_mapped_result_with_cursor` — mock repo returns 5 projections + cursor; assert service maps all fields including confidence and low_sample.

**AC covered:** AC-002 (thumbs_down feedback_type + report_id), AC-003 (edit + correction + golden_dataset_candidate), AC-005 (list delegation with type/date/confidence)

---

### TASK-003: GoldenDatasetCandidate migration and repository · S/no-TDD · alembic/versions/XXXX_add_golden_dataset_candidate.py, src/briefs/models/brief_models.py, src/briefs/repositories/golden_dataset_repository.py

Create the `golden_dataset_candidate` table via an Alembic migration. The ORM model `GoldenDatasetCandidate` (defined in TASK-001 schema) maps to this table. Implement `IGoldenDatasetRepository` (abstract) and `GoldenDatasetRepository` (concrete, SQLAlchemy 2.0 async). The repository exposes `create_candidate(candidate: GoldenDatasetCandidateCreate) -> GoldenDatasetCandidate`.

Migration includes: `candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `tenant_id UUID NOT NULL`, `brief_id UUID NOT NULL REFERENCES workflow_run(workflow_id)`, `user_id UUID NOT NULL`, `original_content TEXT NOT NULL`, `correction TEXT NOT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `reviewed BOOLEAN NOT NULL DEFAULT false`, `review_notes TEXT`. Index on `(tenant_id, reviewed, created_at DESC)` for the Admin Audit Console query.

**AC covered:** AC-003 (golden_dataset_candidate persisted, consumed by PLAN-F-029)

---

### TASK-004: FastAPI routers for briefs list, detail, and feedback · M/TDD · src/api/briefs/briefs_router.py, src/api/briefs/feedback_router.py, src/api/briefs/briefs_schemas.py, src/api/router.py

Implement two FastAPI routers:

`GET /api/v1/briefs` — paginated briefs list. Query params: `type` (optional, BriefType enum), `cursor` (optional), `limit` (default 20, max 50). Requires JWT auth. Reads `user_id` and `tenant_id` from token. Returns `{ "data": { "items": [...], "next_cursor": ... }, "meta": { "limit": N }, "error": null }`. Each item: `brief_id`, `type`, `date` (sent_at), `headline`, `confidence`, `delivery_status`.

`GET /api/v1/briefs/{brief_id}` — brief detail. Returns full `BriefDetail` including `content_html`, `confidence`, `sample_size`, `low_sample`, all list fields.

`POST /api/v1/briefs/{brief_id}/feedback` — submit feedback. Body: `{ "feedback_type": "thumbs_up"|"thumbs_down"|"edit", "correction": str|null }`. Returns `{ "data": { "feedback_id": UUID }, "meta": {}, "error": null }`. Rate-limited (follows DEV-STANDARDS §8 mutation endpoint rule).

All three endpoints verify resource ownership through the service layer (tenant_id from JWT never overridden by client input). Brief HTML content is never stripped at the API layer — sanitization happens in the frontend `SafeHtmlRenderer`.

Register both routers in `src/api/router.py` under the `v1` prefix.

**Tests to write first (TDD):**
- `test_list_briefs_returns_200_with_items` — mock BriefService; GET /api/v1/briefs; assert 200 and items list in response body.
- `test_list_briefs_type_filter_passed_to_service` — call with ?type=morning_brief; assert service.list_briefs called with BriefType.morning_brief.
- `test_get_brief_detail_returns_200_with_confidence` — mock service returns BriefDetail with confidence=0.82; assert response includes confidence field.
- `test_get_brief_detail_returns_404_on_not_found` — mock service raises BriefNotFoundError; assert HTTP 404.
- `test_post_feedback_thumbs_down_returns_201` — valid body; assert 201 and feedback_id in response.
- `test_post_feedback_edit_without_correction_returns_422` — body has feedback_type=edit, correction=null; assert HTTP 422.
- `test_post_feedback_requires_auth` — no JWT; assert HTTP 401.

**AC covered:** AC-001 (confidence exposed in detail response), AC-002 (feedback POST writes via service), AC-003 (edit payload accepted), AC-004 (low_sample in detail response), AC-005 (list endpoint returns type/date/confidence)

---

### TASK-005: React BriefsList and BriefListItem components · S/no-TDD · src/frontend/src/features/briefs/BriefsPage.tsx, src/frontend/src/features/briefs/BriefsList.tsx, src/frontend/src/features/briefs/BriefListItem.tsx, src/frontend/src/features/briefs/hooks/useBriefs.ts, src/frontend/src/features/briefs/briefs.types.ts

Implement the briefs list view. `useBriefs` uses TanStack Query `useInfiniteQuery` with cursor-based pagination, calling `GET /api/v1/briefs` with optional `type` filter. `BriefsPage` renders a type-filter toolbar (All / Morning Brief / Watchlist Scan / Earnings Brief / Event Deep-Dive) and the `BriefsList`. `BriefsList` maps items to `BriefListItem` rows; a "Load more" button triggers the next page fetch. `BriefListItem` shows: type badge (coloured by brief type), date (formatted), headline, confidence as a percentage with colour coding (green ≥ 70%, amber 40–69%, red < 40%), delivery status chip. Clicking a row navigates to `/briefs/:brief_id`.

Items are rendered in the order returned by the API, which is already reverse chronological.

**AC covered:** AC-005 (all fields visible in list: type, date, headline, confidence, delivery status; reverse chronological)

---

### TASK-006: React BriefDetailPage and SafeHtmlRenderer · M/TDD · src/frontend/src/features/briefs/BriefDetailPage.tsx, src/frontend/src/features/briefs/SafeHtmlRenderer.tsx, src/frontend/src/features/briefs/hooks/useBriefDetail.ts

Implement `BriefDetailPage`. It calls `useBriefDetail(briefId)` (TanStack Query, `GET /api/v1/briefs/:id`). The page renders a header block containing: brief type label, date, a prominently styled confidence display (large font, coloured badge — not a tooltip or footnote), and sample size. When `brief.low_sample === true`, renders an inline disclaimer inside the content area, visually contiguous with the brief body text (not in a footer): "Based on a small historical sample (fewer than 5 analogies) — treat this analysis with additional caution." This disclaimer must appear before the first recommendation paragraph. `SafeHtmlRenderer` sanitizes `content_html` using DOMPurify before injecting as `dangerouslySetInnerHTML`.

**Tests to write first (TDD):**
- `test_confidence_rendered_in_header_not_tooltip` — render BriefDetailPage with mocked brief (confidence=0.82); assert element with role="heading" or explicit header class contains "82%" text; assert no `title` attribute and no tooltip wrapper around confidence.
- `test_low_sample_disclaimer_visible_in_body_when_low_sample_true` — mock brief with low_sample=true; render; assert disclaimer text is present in the document and appears before feedback widget.
- `test_low_sample_disclaimer_absent_when_low_sample_false` — mock brief with low_sample=false; render; assert disclaimer text is absent.
- `test_safe_html_renderer_strips_script_tags` — pass HTML with `<script>alert(1)</script>`; render SafeHtmlRenderer; assert no script element in DOM output.

**AC covered:** AC-001 (confidence in brief header, not footnote/tooltip), AC-004 (low_sample disclaimer inline in body)

---

### TASK-007: FeedbackWidget React component and useFeedback hook · M/TDD · src/frontend/src/features/briefs/FeedbackWidget.tsx, src/frontend/src/features/briefs/hooks/useFeedback.ts

Implement `FeedbackWidget`. It receives `briefId` and renders three controls: thumbs-up icon button, thumbs-down icon button, edit icon button (pencil). Pressing thumbs-up or thumbs-down immediately calls `useFeedback` mutation with `{ feedback_type: "thumbs_up"|"thumbs_down" }` against `POST /api/v1/briefs/:id/feedback`. After a successful mutation the pressed button shows a visual confirmation state (filled icon / green tick); no page reload. Pressing edit expands an inline `<textarea>` for the correction, a "Submit correction" button, and a cancel link. Submitting the edit calls the mutation with `{ feedback_type: "edit", correction: textareaValue }`. Empty correction text is blocked client-side with an inline validation message before the request fires.

`useFeedback` is a TanStack Query `useMutation` that POSTs to the feedback endpoint. On error it surfaces a toast notification without crashing the page.

**Tests to write first (TDD):**
- `test_thumbs_down_calls_feedback_mutation_with_correct_payload` — render FeedbackWidget; click thumbs-down; assert mutation called with `{ feedback_type: "thumbs_down" }` and no correction.
- `test_edit_button_expands_textarea` — click edit icon; assert textarea is visible.
- `test_submit_correction_calls_mutation_with_edit_type` — expand edit, type "correction text", click submit; assert mutation called with `{ feedback_type: "edit", correction: "correction text" }`.
- `test_empty_correction_blocked_client_side` — expand edit, leave textarea empty, click submit; assert mutation not called; assert validation message visible.
- `test_successful_thumbs_up_shows_confirmation_state` — mock mutation resolves; assert thumbs-up button has confirmation CSS class applied.

**AC covered:** AC-002 (thumbs-down widget fires feedback), AC-003 (edit widget collects and submits correction text)

---

### TASK-008: Sidebar navigation and route wiring · S/no-TDD · src/frontend/src/App.tsx, src/frontend/src/components/Sidebar.tsx

Add a "Briefs" entry to the sidebar navigation that routes to `/briefs`. Add React Router routes `/briefs` (renders `BriefsPage`) and `/briefs/:brief_id` (renders `BriefDetailPage`) to `App.tsx`. Both routes are protected (require authenticated session). No other layout or navigation changes.

**AC covered:** AC-005 (user navigates to Briefs section)

## Acceptance Criteria Coverage

- AC-001: User opens a Morning Brief — confidence score displayed prominently within the brief header, not in a footnote or tooltip → TASK-006 (BriefDetailPage header block), TASK-004 (confidence field in API response)
- AC-002: User clicks thumbs down — user_feedback row written to Layer 4 with feedback_type=thumbs_down and brief's workflow_run_id as decision_ref (report_id in schema), without any admin action → TASK-007 (FeedbackWidget mutation), TASK-004 (feedback router), TASK-002 (BriefFeedbackService → IFeedbackRepository)
- AC-003: User provides an edit correction — user_feedback row includes correction text and admin AI audit console surfaces a golden dataset candidate proposal → TASK-007 (edit widget + submit), TASK-002 (BriefFeedbackService writes golden_dataset_candidate), TASK-003 (GoldenDatasetCandidate table)
- AC-004: Brief generated with sample_size < 5 — disclaimer visible inline in the brief body → TASK-001 (low_sample flag computed in BriefRepository), TASK-006 (disclaimer rendered in body, before recommendations)
- AC-005: User navigates to Briefs section — all past briefs listed in reverse chronological order with type, date, and confidence visible → TASK-001 (repository ordered by completed_at DESC), TASK-004 (list API), TASK-005 (BriefsList + BriefListItem), TASK-008 (navigation route)

## Acceptance Notes

The `golden_dataset_candidate` table introduced in TASK-003 is consumed by PLAN-F-029 (Admin AI Audit Console). PLAN-F-029 must not be executed before TASK-003 migration has been applied. The Admin Audit Console plan should reference this migration in its own dependency setup — coordinate migration ordering in the Alembic version chain.

## Risks and Notes

- **HTML content sanitization**: brief `content_html` is generated by the Narrative Writer agent (Opus 4.7). Even though it is system-generated, it must still pass through DOMPurify in the frontend to prevent any stored-XSS path. The backend never strips or re-encodes this content; sanitization is the frontend's responsibility and must happen in `SafeHtmlRenderer` before `dangerouslySetInnerHTML`.
- **JSONB schema assumption**: `BriefRepository` parses `workflow_run.final_state` JSONB to extract `headline`, `content_html`, `confidence`, `sample_size`. If the workflow plans (PLAN-F-006, PLAN-F-008, PLAN-F-009, PLAN-F-010) emit different JSONB key names, extraction will fail silently. Executor must validate the `final_state` key names against the actual workflow output schema before implementing the repository projection.
- **report_id vs decision_ref naming**: The requirement uses `decision_ref` as the FK concept; the architecture `user_feedback` table uses `report_id`. This plan uses `report_id` throughout the implementation to match the DB schema. The semantic is identical.
- **No separate brief table**: Briefs are a filtered projection of `workflow_run`. This avoids duplication but means the query depends on the JSONB structure of `final_state`. If workflow types later need different delivery metadata, this projection approach may require a denormalized view or dedicated table.
- **Confidence display colour thresholds**: AC-001 requires "prominent" display. The colour coding defined in TASK-005 (green ≥ 70%, amber 40–69%, red < 40%) aligns with the confidence routing thresholds from Architecture D9, providing consistent visual language across the application.
- **DOMPurify dependency**: `dompurify` and `@types/dompurify` must be added to `package.json`. Executor should confirm the package is not already present from another frontend feature.
