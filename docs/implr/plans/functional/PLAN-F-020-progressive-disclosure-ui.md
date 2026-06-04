---
plan_id: PLAN-F-020
slug: progressive-disclosure-ui
title: Progressive Disclosure UI (Popup, Side Panel, Deep Dive)
linked_requirement: REQ-F-020
type: functional
status: ready
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-001, reason: "Popup must render within 300ms; data must be available from the Mode A pipeline cache (step 12 artifact) at click time" }
dependencies:
  - { id: PLAN-F-019, reason: "IntelligenceMap provides the onExpandEvent injectable prop and the EventPulse payload that seeds the popup" }
  - { id: PLAN-F-016, reason: "Audit trail view reads agent_invocation rows and Langfuse trace links produced by the evaluation framework" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-03T00:00:00Z
updated_at: 2026-06-03T00:00:00Z
---

# PLAN-F-020 — Progressive Disclosure UI (Popup, Side Panel, Deep Dive)

## Linked Requirement
**REQ-F-020** — Progressive Disclosure UI (Popup, Side Panel, Deep Dive)
Status: approved | Jira:

## Objective

Implement the three-level progressive disclosure interaction layer that sits over the
Intelligence Map. Level 1 is a MapLibre GL JS popup that renders within 300 ms from cached
event data when the user clicks a map pulse; it shows event essentials and an "Expand" button.
Level 2 is a CSS drawer side panel that slides open on "Expand", loads full analysis from the
API, and exposes sparklines, analogies, affected-company scores, a contrarian callout when
applicable, social posts when enabled, and a "Why this read?" link. Level 3 is a full
deep-dive page reachable from the side panel that displays the complete analysis memo,
scenario tree, and per-company breakdowns. A "Why this read?" audit trail view can be opened
from the side panel and shows historical analogs with similarity scores, the prompt SHA used,
the agent reasoning chain, and a Langfuse trace link. Low-sample disclaimers (sample_size < 5)
are rendered inline in both popup and side panel when the API sets `low_sample: true`.

The plan adds three new API endpoints to the `api` module, a React feature module
`src/features/progressive-disclosure/`, and injects the popup handler into the
`IntelligenceMap` component via its existing `onExpandEvent` prop without modifying that
component's internals.

## Architecture Context

This plan spans **Layer 5 — Serving** (three new FastAPI endpoints) and **Layer 6 —
Presentation** (the React feature module). It does not touch Layer 4 processing; it reads
data already produced by Mode A (PLAN-F-001) and stored in `ai_recommendation` and
`agent_invocation` tables.

**API Layer (ARCHITECTURE.md §5):** Three endpoints are defined by the architecture:
- `GET /api/v1/events/{id}/popup` → `PopupData`
- `GET /api/v1/events/{id}/side-panel` → `SidePanelData`
- `GET /api/v1/events/{id}/audit-trail` → audit trail (agent reasoning chain + Langfuse link)

**Frontend Stack (ARCHITECTURE.md §11):** React 18 + TypeScript, TanStack Query for data
fetching, shadcn/ui for drawer/card components, Recharts or visx for T±7d price sparklines.
The side panel is a CSS drawer overlay (z-index over map). The popup is a MapLibre GL JS
`Popup` component already scaffolded as a stub in PLAN-F-019 TASK-011.

**Four-Layer Memory (ARCHITECTURE.md §7.4):** Layer 1 `agent_invocation` rows store the
complete reasoning chain for every workflow run. The audit trail API reads from these rows
joined with `workflow_run` to produce the reasoning chain and the Langfuse trace URL.
PLAN-F-016 (evaluation framework) owns the `agent_invocation` repository interface; this
plan reads from it via the existing `IEvaluationRepository` or a new slim
`IAuditTrailRepository`.

**Disclaimer injection (ARCHITECTURE.md §12):** The `low_sample` flag on `PopupData` and
`SidePanelData` is set at the API serialization level when `ai_recommendation.sample_size < 5`.
The frontend renders the disclaimer field when present; it does not compute the threshold.

**PLAN-F-019 integration:** `IntelligenceMap.tsx` exposes `onExpandEvent?: (event: EventPulse) => void`
as an injectable prop (PLAN-F-019 TASK-011 Risk Note). This plan provides the concrete
handler implementation and wires it through the application's router-level composition.

## Component Design

### New Components

```
src/
  features/
    progressive-disclosure/
      components/
        EventPopup.tsx                  — MapLibre Popup wrapper; renders PopupData; "Expand" button
        EventPopup.test.tsx
        SidePanel.tsx                   — CSS drawer overlay; receives SidePanelData; full analysis
        SidePanel.test.tsx
        SidePanelSparkline.tsx          — T±7d OHLCV sparkline per ticker (Recharts/visx)
        SidePanelSparkline.test.tsx
        SidePanelAnalogies.tsx          — historical analogy list (top 3)
        SidePanelAnalogies.test.tsx
        ContrianCallout.tsx             — highlighted "history says" callout block (contrarian path)
        ContrarianCallout.test.tsx
        LowSampleDisclaimer.tsx         — inline disclaimer for low-sample recommendations
        LowSampleDisclaimer.test.tsx
        AuditTrailView.tsx              — full audit trail: analogs + prompt SHA + reasoning steps + Langfuse link
        AuditTrailView.test.tsx
        DeepDivePage.tsx                — full deep-dive page; scenario tree + analogy table + per-company breakdown
        DeepDivePage.test.tsx
      hooks/
        usePopupData.ts                 — TanStack Query: GET /api/v1/events/{id}/popup
        usePopupData.test.ts
        useSidePanelData.ts             — TanStack Query: GET /api/v1/events/{id}/side-panel; lazy (fires on Expand)
        useSidePanelData.test.ts
        useAuditTrail.ts                — TanStack Query: GET /api/v1/events/{id}/audit-trail; lazy
        useAuditTrail.test.ts
        useDeepDive.ts                  — TanStack Query: GET /api/v1/events/{id}/deep-dive
        useDeepDive.test.ts
      types/
        disclosure.types.ts             — PopupData, SidePanelData, AuditTrailData, DeepDiveData interfaces
      api/
        disclosure.api.ts               — fetch wrappers for all four endpoints (Zod-validated)
      ProgressiveDisclosureProvider.tsx — context provider; manages open/close state for all three levels
      ProgressiveDisclosureProvider.test.tsx

tests/
  integration/
    progressive-disclosure/
      popup-render.test.tsx             — popup renders PopupData within 300ms; low_sample disclaimer shown
      side-panel-expand.test.tsx        — Expand click opens side panel with full analysis content
      audit-trail.test.tsx              — "Why this read?" opens audit trail with all required fields
      contrarian-callout.test.tsx       — contrarian flag → callout block rendered before recommendation

src/
  api/
    progressive_disclosure/
      router.py                         — FastAPI router: popup, side-panel, audit-trail, deep-dive endpoints
      schemas.py                        — Pydantic request/response models: PopupDataResponse, SidePanelDataResponse, AuditTrailResponse
      service.py                        — ProgressiveDisclosureService: business logic, assembles response DTOs
      interfaces/
        i_progressive_disclosure_repository.py  — IProgressiveDisclosureRepository (abstract)
      repositories/
        progressive_disclosure_repository.py    — concrete implementation: queries geo_event, ai_recommendation, agent_invocation, price_bar

  alembic/
    (no new tables — reads from existing: geo_event, ai_recommendation, agent_invocation,
     workflow_run, event_exposure, company, price_bar)
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/app/router.tsx` | Add route `/events/:id/deep-dive` pointing to `<DeepDivePage />`; wrap root `<IntelligenceMap />` with `<ProgressiveDisclosureProvider>` and pass `onExpandEvent` handler | Deep dive requires its own route; popup/panel are overlay components wired via context |
| `src/api/app.py` (or equivalent FastAPI factory) | Register `progressive_disclosure` router at `/api/v1` prefix | Expose three new endpoints |

### Interfaces and Contracts

```typescript
// src/features/progressive-disclosure/types/disclosure.types.ts

export interface TickerDelta {
  ticker: string;
  score_delta: number;
}

export interface PopupData {
  event_id: string;             // UUID
  category: string[];
  intensity: number;            // 1–5
  headline: string;
  time_ago: string;             // e.g. "14 minutes ago"
  location: string;
  exposed_holdings_count: number;
  tickers_with_delta: TickerDelta[];
  action_signal: string;        // HOLD | WATCH | BUY_OPP | REDUCE_RISK | HEDGE | CONTRARIAN
  confidence: number;           // 0–1
  sample_size: number;
  low_sample: boolean;          // true when sample_size < 5
}

export interface SparklinePoint {
  ts: string;       // ISO date
  close: number;
}

export interface AnalogSummary {
  event_id: string;
  headline: string;
  occurred_at: string;
  similarity_score: number;     // 0–1
}

export interface AffectedCompany {
  company_id: string;
  ticker: string;
  name: string;
  score: number;
  delta: number;
}

export interface SocialPost {
  post_id: string;
  source: string;
  text: string;
  timestamp: string;
}

export interface SidePanelData extends PopupData {
  summary: string;
  sparklines: { ticker: string; ohlcv_7d: SparklinePoint[] }[];
  rationale: string;
  analogies: AnalogSummary[];   // top 3
  affected_companies: AffectedCompany[];
  is_contrarian: boolean;
  contrarian_callout: string | null;
  social_posts: SocialPost[] | null;
  audit_trail_url: string;      // relative path: /events/{id}/audit-trail
}

export interface ReasoningStep {
  agent_role: string;
  step_index: number;
  content: string;
  tool_calls: string[];         // tool names called in this step
}

export interface AuditTrailData {
  event_id: string;
  prompt_version: string;       // git SHA used
  langfuse_trace_url: string;
  analogies: (AnalogSummary & { similarity_score: number })[];
  reasoning_steps: ReasoningStep[];
}

export interface ScenarioNode {
  label: string;
  probability: number;
  description: string;
  children: ScenarioNode[];
}

export interface DeepDiveData {
  event_id: string;
  memo: string;                 // full analysis prose
  scenario_tree: ScenarioNode | null;
  analogies: AnalogSummary[];   // full table
  affected_companies: AffectedCompany[];
  generated_at: string;         // ISO timestamp
}


// src/features/progressive-disclosure/api/disclosure.api.ts

export async function fetchPopupData(eventId: string): Promise<PopupData>;
export async function fetchSidePanelData(eventId: string): Promise<SidePanelData>;
export async function fetchAuditTrail(eventId: string): Promise<AuditTrailData>;
export async function fetchDeepDive(eventId: string): Promise<DeepDiveData>;
```

```python
# src/api/progressive_disclosure/interfaces/i_progressive_disclosure_repository.py

class IProgressiveDisclosureRepository(ABC):
    @abstractmethod
    async def get_popup_data(self, event_id: UUID, tenant_id: UUID) -> PopupDataRow: ...

    @abstractmethod
    async def get_side_panel_data(self, event_id: UUID, tenant_id: UUID) -> SidePanelDataRow: ...

    @abstractmethod
    async def get_audit_trail(self, event_id: UUID) -> AuditTrailRow: ...

    @abstractmethod
    async def get_deep_dive(self, event_id: UUID) -> DeepDiveRow | None: ...

    @abstractmethod
    async def get_sparklines(
        self, company_ids: list[UUID], days: int = 7
    ) -> dict[UUID, list[PricePoint]]: ...
```

## Implementation Tasks

### TASK-001: TypeScript type definitions and Zod schemas · S/no-TDD · src/features/progressive-disclosure/types/disclosure.types.ts,src/features/progressive-disclosure/api/disclosure.api.ts

Define all TypeScript interfaces in `disclosure.types.ts`: `PopupData`, `SidePanelData`,
`AuditTrailData`, `DeepDiveData`, `TickerDelta`, `SparklinePoint`, `AnalogSummary`,
`AffectedCompany`, `SocialPost`, `ReasoningStep`, `ScenarioNode`. Interfaces follow the
data models specified in the requirement exactly.

Implement `disclosure.api.ts` with four async fetch functions, each using `fetch` with a
`Authorization: Bearer` header from the application auth context. Each function validates
its response with a Zod schema matching its TypeScript interface and throws a typed
`DisclosureFetchError` on HTTP errors (including 403 ownership) or schema violations.

No rendering, no side effects — pure data contracts and typed fetch wrappers.

**AC covered**: enables AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-002: Backend repository interface and implementation · M/TDD · src/api/progressive_disclosure/interfaces/i_progressive_disclosure_repository.py,src/api/progressive_disclosure/repositories/progressive_disclosure_repository.py

Define `IProgressiveDisclosureRepository` (abstract base class). Implement
`ProgressiveDisclosureRepository` using SQLAlchemy 2.0 async sessions.

`get_popup_data(event_id, tenant_id)`: JOIN `geo_event` + `event_exposure` +
`ai_recommendation` + `company`. Filter `tenant_id` on `geo_event` (NULL = global, also
visible). Return the scalar fields needed for `PopupData`: category, intensity, title, summary,
lat/lon for location, list of `(ticker, score_delta)` for exposed portfolio companies,
action_signal, confidence, sample_size. Compute `low_sample = sample_size < 5` at the
repository level.

`get_side_panel_data(event_id, tenant_id)`: extends the popup query to additionally return
rationale text, analogies JSONB (top 3 from `ai_recommendation.analogies`), affected company
list, is_contrarian flag and contrarian_callout, and social_posts if stored. Returns the
`audit_trail_url` as a computed relative path `/events/{event_id}/audit-trail`.

`get_audit_trail(event_id)`: JOIN `workflow_run` + `agent_invocation` WHERE
`workflow_run.inputs ->> 'event_id' = event_id`. Order `agent_invocation` rows by
`started_at`. Collect `prompt_version` from the last `agent_invocation` row for the
`recommendation_synthesizer` role. Extract Langfuse trace URL from
`workflow_run.langfuse_trace_id`.

`get_deep_dive(event_id)`: query `workflow_run` WHERE `workflow_type = 'event_deep_dive'`
AND `inputs ->> 'event_id' = event_id` ORDER BY `completed_at DESC LIMIT 1`. Extract memo
from `final_state JSONB`. If no deep-dive workflow has completed, return `None`.

`get_sparklines(company_ids, days=7)`: query `price_bar` for the past 7 days for each
company. Return dict `company_id → list[PricePoint]` (close price per day). Bounded to
`days * len(company_ids) ≤ 700` rows maximum.

All queries include ownership check: no row is returned unless `geo_event.tenant_id IS NULL
OR geo_event.tenant_id = :tenant_id`. This enforces ARCHITECTURE.md §12.1 IDOR prevention.

**Tests to write first (TDD):**
- `get_popup_data` with a seeded `geo_event` + `ai_recommendation` returns correct `PopupData` fields; `tenant_id` mismatch returns no row (ownership enforced)
- `low_sample=True` when `sample_size=4`; `low_sample=False` when `sample_size=5`
- `get_popup_data` for a global event (`tenant_id=NULL`) is accessible to any tenant
- `get_audit_trail` returns reasoning steps ordered by `started_at`; `prompt_version` matches the recommendation_synthesizer invocation
- `get_sparklines` bounded to 7 days of data; returns empty list for a company with no price bars
- `get_deep_dive` returns `None` when no `event_deep_dive` workflow has completed for the event

**AC covered**: AC-001, AC-002, AC-003, AC-005

---

### TASK-003: Backend service and Pydantic schemas · M/TDD · src/api/progressive_disclosure/service.py,src/api/progressive_disclosure/schemas.py

Define Pydantic v2 response models in `schemas.py`: `PopupDataResponse`, `SidePanelDataResponse`,
`AuditTrailResponse`, `DeepDiveResponse`, `ReasoningStepSchema`, `AnalogSummarySchema`,
`AffectedCompanySchema`, `SparklineSchema`, `SocialPostSchema`. All fields are non-nullable
except those explicitly optional in the data model.

Implement `ProgressiveDisclosureService`:

`get_popup(event_id, tenant_id) -> PopupDataResponse`:
1. Call `IProgressiveDisclosureRepository.get_popup_data`.
2. Map row to `PopupDataResponse`. `time_ago` is computed from `geo_event.occurred_at` to
   "N minutes/hours ago" string.
3. Return response. Raise `EventNotFoundError` (maps to 404) if no row returned.

`get_side_panel(event_id, tenant_id) -> SidePanelDataResponse`:
1. Call `IProgressiveDisclosureRepository.get_side_panel_data`.
2. Call `get_sparklines` for the list of exposed `company_ids`.
3. Assemble `SidePanelDataResponse` including sparklines.
4. If `is_contrarian=True`, ensure `contrarian_callout` is non-null.

`get_audit_trail(event_id, tenant_id) -> AuditTrailResponse`:
1. Ownership: verify the event belongs to the tenant via `get_popup_data` (reuses existing
   ownership check).
2. Call `IProgressiveDisclosureRepository.get_audit_trail`.
3. Map `agent_invocation.output JSONB` reasoning fields into `ReasoningStepSchema` list.

`get_deep_dive(event_id, tenant_id) -> DeepDiveResponse`:
1. Ownership check via `get_popup_data`.
2. Call `IProgressiveDisclosureRepository.get_deep_dive`.
3. If `None`: raise `DeepDiveNotReadyError` (maps to 202 Accepted with a
   `{"status": "pending"}` body indicating on-demand generation is in progress or not yet
   triggered).

**Tests to write first (TDD):**
- `get_popup` with a valid event returns `PopupDataResponse` with `time_ago` formatted as a human-readable string
- `get_popup` with an unknown `event_id` raises `EventNotFoundError`
- `get_side_panel` assembles sparklines alongside full analysis content; `contrarian_callout` is non-null when `is_contrarian=True`
- `get_audit_trail` maps `agent_invocation` rows into ordered `ReasoningStepSchema` list
- `get_deep_dive` raises `DeepDiveNotReadyError` when no completed `event_deep_dive` workflow exists
- `time_ago` helper: `occurred_at = now - 90s` → "1 minute ago"; `occurred_at = now - 7200s` → "2 hours ago"

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-004: FastAPI router for progressive disclosure endpoints · M/TDD · src/api/progressive_disclosure/router.py

Implement four REST endpoints under `/api/v1/events/{event_id}/`:

- `GET /api/v1/events/{event_id}/popup` — authenticated; calls `ProgressiveDisclosureService.get_popup`; returns `PopupDataResponse` (200) or 404
- `GET /api/v1/events/{event_id}/side-panel` — authenticated; calls `get_side_panel`; returns `SidePanelDataResponse` (200) or 404
- `GET /api/v1/events/{event_id}/audit-trail` — authenticated; calls `get_audit_trail`; returns `AuditTrailResponse` (200) or 404
- `GET /api/v1/events/{event_id}/deep-dive` — authenticated; calls `get_deep_dive`; returns `DeepDiveResponse` (200), 202 (pending), or 404

All endpoints use `Depends(get_current_user)` (JWT auth). Resource ownership is enforced in
the service layer — the controller does not add additional ownership checks. No business logic
in the router — parse, delegate, respond only.

**Tests to write first (TDD):**
- `GET /popup` with a valid JWT and existing event returns 200 with correct `PopupDataResponse` shape
- `GET /popup` without JWT returns 401
- `GET /popup` for an event belonging to a different tenant returns 404 (ownership enforced, not 403 to avoid leaking event existence)
- `GET /audit-trail` for a valid event returns 200 with `prompt_version` SHA and non-empty `reasoning_steps`
- `GET /deep-dive` when no workflow has completed returns 202 with `{"status": "pending"}`
- `GET /side-panel` with `is_contrarian=True` in mock data returns `contrarian_callout` as non-null string

**AC covered**: AC-001, AC-002, AC-003, AC-004

---

### TASK-005: TanStack Query hooks for popup, side panel, audit trail, deep dive · M/TDD · src/features/progressive-disclosure/hooks/usePopupData.ts,src/features/progressive-disclosure/hooks/usePopupData.test.ts,src/features/progressive-disclosure/hooks/useSidePanelData.ts,src/features/progressive-disclosure/hooks/useSidePanelData.test.ts,src/features/progressive-disclosure/hooks/useAuditTrail.ts,src/features/progressive-disclosure/hooks/useAuditTrail.test.ts,src/features/progressive-disclosure/hooks/useDeepDive.ts,src/features/progressive-disclosure/hooks/useDeepDive.test.ts

Implement four TanStack Query hooks:

`usePopupData(eventId: string | null)`: `useQuery` with `enabled: !!eventId`. `staleTime: 30_000` (popup data stays fresh for 30s — it is derived from the already-processed Mode A pipeline result). Returns `{ data: PopupData | undefined, isLoading, isError }`.

`useSidePanelData(eventId: string | null, enabled: boolean)`: `useQuery` with `enabled: !!eventId && enabled`. Lazy — only fires when the side panel is opened. `staleTime: 60_000`.

`useAuditTrail(eventId: string | null, enabled: boolean)`: `useQuery` with `enabled: !!eventId && enabled`. Lazy — fires only when "Why this read?" is clicked. No `staleTime` (audit trail is immutable).

`useDeepDive(eventId: string | null, enabled: boolean)`: `useQuery` with `enabled: !!eventId && enabled`. Handles the 202 response by treating it as a loading state that retries every 5 seconds (using `refetchInterval` when `data?.status === "pending"`).

**Tests to write first (TDD):**
- `usePopupData("evt-1")` with MSW returning valid `PopupData` → `data` is populated after `isLoading` resolves
- `usePopupData(null)` → query does not fire (no MSW request made)
- `useSidePanelData("evt-1", false)` → query does not fire; `useSidePanelData("evt-1", true)` → fires exactly once
- `useAuditTrail("evt-1", true)` with MSW returning `AuditTrailData` → `data.reasoning_steps` is a non-empty array
- `useDeepDive("evt-1", true)` with MSW returning 202 `{"status":"pending"}` → hook re-fetches after 5 seconds (fake timer assertion)
- `useDeepDive("evt-1", true)` with MSW returning valid `DeepDiveData` after 202 → eventually resolves to the data

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-006: EventPopup component · M/TDD · src/features/progressive-disclosure/components/EventPopup.tsx,src/features/progressive-disclosure/components/EventPopup.test.tsx

Implement `<EventPopup eventId={string} onExpand={() => void} onClose={() => void} />`.

The component calls `usePopupData(eventId)` on mount. While loading, it renders a minimal
skeleton (category placeholder, intensity badge, one-line headline). On data arrival it
renders: category badge(s), intensity badge (1–5 color-coded), headline, `time_ago`, location,
`exposed_holdings_count` with plural label, `tickers_with_delta` list (ticker + delta arrow
+ sign), `action_signal` in bold, `confidence` as a percentage, and an "Expand" button.

When `low_sample=true`, renders `<LowSampleDisclaimer />` inline below the confidence line
before the "Expand" button.

The component is rendered inside a MapLibre GL JS `Popup` whose anchor is the clicked pulse
coordinate. The popup does not include a scroll container — all content must fit within 300px
width. The "Expand" button calls `onExpand()` which the `ProgressiveDisclosureProvider`
handles to open the side panel; it does not close the popup.

Rendering must be complete within 300ms of `onExpandEvent` being called by `IntelligenceMap`.
This is achievable because `usePopupData` has `staleTime: 30_000` — for recently-seen events
the data may already be in the TanStack Query cache. For new events, the popup mounts
immediately with the skeleton, and the data arrives from `GET /popup` (which reads cached
pipeline output).

**Tests to write first (TDD):**
- Renders skeleton while `isLoading=true` (mock `usePopupData` to keep loading)
- Renders all required fields — category, intensity, headline, time_ago, location, exposed_holdings_count, action_signal, confidence — when data is available
- `tickers_with_delta` with `score_delta=+2.5` renders with a "+" prefix; negative delta renders with "−" prefix
- `low_sample=true` → `<LowSampleDisclaimer />` is present in the DOM
- `low_sample=false` → `<LowSampleDisclaimer />` is absent
- Clicking "Expand" button calls `onExpand` exactly once
- Clicking the popup close control calls `onClose` exactly once

**AC covered**: AC-001, AC-005

---

### TASK-007: LowSampleDisclaimer and ContrarianCallout components · S/no-TDD · src/features/progressive-disclosure/components/LowSampleDisclaimer.tsx,src/features/progressive-disclosure/components/LowSampleDisclaimer.test.tsx,src/features/progressive-disclosure/components/ContrarianCallout.tsx,src/features/progressive-disclosure/components/ContrarianCallout.test.tsx

Implement `<LowSampleDisclaimer />` as a small shadcn/ui `Alert` (variant: warning) with
fixed text: "Low sample — fewer than 5 historical analogies found. Treat this recommendation
with caution." The component takes no props; it is rendered at the call site when `low_sample`
is true. This follows the architecture's principle that the frontend renders the disclaimer
field when present without computing the threshold itself.

Implement `<ContrarianCallout text={string} />` as a prominently styled shadcn/ui `Alert`
(variant: info, with a distinctive left-border color distinct from warning). Renders the text
passed as `text` prop. The callout is designed to lead the side panel content visually —
it receives `z-index` and border treatment that makes it visually distinct from the main
recommendation body.

Both components are purely presentational — no data fetching, no side effects.

**AC covered**: AC-004, AC-005

---

### TASK-008: SidePanelSparkline and SidePanelAnalogies sub-components · M/TDD · src/features/progressive-disclosure/components/SidePanelSparkline.tsx,src/features/progressive-disclosure/components/SidePanelSparkline.test.tsx,src/features/progressive-disclosure/components/SidePanelAnalogies.tsx,src/features/progressive-disclosure/components/SidePanelAnalogies.test.tsx

Implement `<SidePanelSparkline ticker={string} ohlcv_7d={SparklinePoint[]} />` using
Recharts `<LineChart>` (or visx equivalent). The chart displays a T±7d close-price line
with no axes (sparkline style), a ticker label, and a color-coded final-point dot: green if
`ohlcv_7d[last].close >= ohlcv_7d[0].close`, red otherwise. Width fixed to 160px, height
48px. When `ohlcv_7d` is empty, renders a "No price data" placeholder text instead of the
chart. Each sparkline is rendered independently — the component is called once per ticker in
the `SidePanelData.sparklines` array.

Implement `<SidePanelAnalogies analogies={AnalogSummary[]} />` as a compact list. Each
entry shows: headline (truncated to 80 characters), `occurred_at` formatted as a short date,
and a `similarity_score` percentage badge. Maximum 3 analogies are rendered (the API returns
at most 3). If `analogies` is empty, renders "No historical analogies found."

**Tests to write first (TDD):**
- `<SidePanelSparkline ticker="AAPL" ohlcv_7d={[...7 points...]} />` → renders a chart element (assert `getByRole("img")` or test-id); final dot is green when last close > first close; red when last close < first close
- `<SidePanelSparkline ticker="AAPL" ohlcv_7d={[]} />` → renders "No price data" text
- `<SidePanelAnalogies analogies={[...3 items...]} />` → renders exactly 3 list entries
- `<SidePanelAnalogies analogies={[]} />` → renders "No historical analogies found"
- Similarity score displayed as percentage: `similarity_score=0.87` → "87%" in the DOM
- Headline truncated to ≤80 characters in the rendered output

**AC covered**: AC-002

---

### TASK-009: SidePanel component · L/TDD · src/features/progressive-disclosure/components/SidePanel.tsx,src/features/progressive-disclosure/components/SidePanel.test.tsx

Implement `<SidePanel eventId={string | null} isOpen={boolean} onClose={() => void} onOpenAuditTrail={() => void} onOpenDeepDive={() => void} />`.

The component is a CSS drawer overlay: `position: fixed; right: 0; top: 0; height: 100vh;
width: 420px; z-index: 200; transform: translateX(100%)` when closed, transitioning to
`translateX(0)` when `isOpen=true`. It renders over the map without blocking map interaction
on the left portion of the viewport.

When `isOpen=true` and `eventId` is set, calls `useSidePanelData(eventId, isOpen)`. While
loading, renders a multi-line skeleton matching the final layout. On data arrival:

1. If `is_contrarian=true`: renders `<ContrarianCallout text={contrarian_callout} />` as the
   first visible content block, before the AI action signal.
2. Renders event summary text.
3. Renders sparklines grid: one `<SidePanelSparkline />` per entry in `sparklines` (2-column grid, max 6).
4. Renders AI action signal, confidence percentage, sample_size line.
5. Renders `<LowSampleDisclaimer />` inline when `low_sample=true`.
6. Renders recommendation rationale text.
7. Renders `<SidePanelAnalogies analogies={analogies} />` (top 3).
8. Renders affected companies table: company name, ticker, score, score delta.
9. If `social_posts` is non-null and non-empty: renders a "Triggering posts" section with source, timestamp, and text for each post.
10. Renders "Why this read?" link that calls `onOpenAuditTrail()`.
11. Renders "Full Analysis" button that calls `onOpenDeepDive()`.

Close button in the top-right corner calls `onClose()`.

**Tests to write first (TDD):**
- `<SidePanel isOpen={false} />` → drawer is off-screen (transform contains "100%" or display is hidden); `useSidePanelData` is not called
- `<SidePanel isOpen={true} eventId="evt-1" />` with mock data → `useSidePanelData` fires; all required content sections are present: summary, sparklines, action signal, confidence, rationale, analogies section, affected companies table
- `is_contrarian=true` → `<ContrarianCallout />` renders before action signal text; it is the first non-header content node
- `is_contrarian=false` → `<ContrarianCallout />` is absent from the DOM
- `low_sample=true` → `<LowSampleDisclaimer />` is present in side panel
- `low_sample=false` → `<LowSampleDisclaimer />` is absent
- `social_posts` is a non-empty array → "Triggering posts" section is rendered with the correct count
- `social_posts` is null → "Triggering posts" section is absent
- Clicking "Why this read?" calls `onOpenAuditTrail` once
- Clicking "Full Analysis" calls `onOpenDeepDive` once
- Clicking close button calls `onClose` once

**AC covered**: AC-002, AC-004, AC-005

---

### TASK-010: AuditTrailView component · M/TDD · src/features/progressive-disclosure/components/AuditTrailView.tsx,src/features/progressive-disclosure/components/AuditTrailView.test.tsx

Implement `<AuditTrailView eventId={string | null} isOpen={boolean} onClose={() => void} />`.

Rendered as a full-width overlay panel (or modal) with `z-index: 300` (above side panel).
Calls `useAuditTrail(eventId, isOpen)` on mount.

On data arrival renders:
1. Header: "Why this read?" title with close button.
2. Historical analogies section: ordered list of analogies from `AuditTrailData.analogies`,
   each showing headline, date, and similarity score percentage.
3. Prompt section: "Prompt version: {prompt_version}" displayed as a monospace SHA string.
4. Reasoning chain section: ordered numbered list of `reasoning_steps`, each showing
   agent_role label, step content text, and tool calls made (comma-separated).
5. Langfuse trace link: an `<a>` tag with `target="_blank"` opening `langfuse_trace_url`.
   Link text: "View full trace in Langfuse". If `langfuse_trace_url` is empty, the link is
   omitted (Langfuse may be disabled in some self-host configurations).

**Tests to write first (TDD):**
- `<AuditTrailView isOpen={false} />` → `useAuditTrail` is not called; content not rendered
- `<AuditTrailView isOpen={true} eventId="evt-1" />` with mock audit trail data → `prompt_version` SHA is displayed; reasoning steps are listed in order; each step shows agent_role
- `analogies` list renders similarity_score as percentages; list is ordered by similarity_score descending
- `langfuse_trace_url` is non-empty → anchor element with `href` matching the URL is present; `target="_blank"` is set
- `langfuse_trace_url` is empty string → Langfuse link is absent from DOM
- Clicking close button calls `onClose` once

**AC covered**: AC-003

---

### TASK-011: DeepDivePage component · M/TDD · src/features/progressive-disclosure/components/DeepDivePage.tsx,src/features/progressive-disclosure/components/DeepDivePage.test.tsx

Implement `<DeepDivePage />` as a standalone full-page React route component at
`/events/:eventId/deep-dive`. It reads `eventId` from the route params and calls
`useDeepDive(eventId, true)`.

While loading or pending (202 status): renders a full-page loading spinner with text
"Generating deep-dive analysis… This may take up to 5 minutes." Auto-retries every 5 seconds
via `useDeepDive`'s `refetchInterval`.

On data arrival renders:
1. Full analysis memo text (`data.memo`) as formatted prose with headings preserved from the
   markdown output of the Narrative Writer agent.
2. Scenario tree: recursive rendering of `ScenarioNode` as a collapsible tree (shadcn/ui
   `Collapsible`). Each node shows label, probability percentage, and description. If
   `scenario_tree` is null, renders "No scenario analysis available."
3. Full analogies table: all analogies with headline, date, similarity score. Sortable by
   similarity score (client-side sort).
4. Per-company breakdowns: for each `AffectedCompany`, shows company name, ticker, current
   score, and score delta.
5. Back link to the Intelligence Map (`/`).

**Tests to write first (TDD):**
- `<DeepDivePage />` with `eventId="evt-1"` and MSW returning 202 `{"status":"pending"}` → loading message is shown; "Generating deep-dive analysis" text is present
- With MSW returning valid `DeepDiveData` → memo text is rendered; affected companies table has correct row count
- `scenario_tree` is null → "No scenario analysis available" is rendered
- `scenario_tree` has nested children → collapsible tree renders root node and child nodes
- Analogies table is sortable: clicking sort header → order changes (assert order of rendered rows changes)
- Back link with `href="/"` is present in the DOM

**AC covered**: AC-002 (full analysis accessible from side panel)

---

### TASK-012: ProgressiveDisclosureProvider and router wiring · M/TDD · src/features/progressive-disclosure/ProgressiveDisclosureProvider.tsx,src/features/progressive-disclosure/ProgressiveDisclosureProvider.test.tsx,src/app/router.tsx

Implement `<ProgressiveDisclosureProvider>` as a React context provider that manages the
three-level UI state machine:

```typescript
interface DisclosureState {
  selectedEventId: string | null;
  popupOpen: boolean;
  sidePanelOpen: boolean;
  auditTrailOpen: boolean;
}
```

Actions:
- `openPopup(eventId)` — sets `selectedEventId`, `popupOpen=true`; does not change side
  panel state
- `expandToSidePanel()` — sets `sidePanelOpen=true`; popup remains open (user can still see it)
- `openAuditTrail()` — sets `auditTrailOpen=true`; requires `sidePanelOpen=true`
- `closePopup()` — sets `popupOpen=false`, `sidePanelOpen=false`, `auditTrailOpen=false`,
  `selectedEventId=null` (closing the popup clears all levels)
- `closeSidePanel()` — sets `sidePanelOpen=false`, `auditTrailOpen=false` (popup may remain)
- `closeAuditTrail()` — sets `auditTrailOpen=false` only

The provider exposes a `onExpandEvent(event: EventPulse)` callback that is injected into
`<IntelligenceMap />` as the `onExpandEvent` prop. This callback calls `openPopup(event.event_id)`.

Renders children wrapped with the context. Renders overlay components as siblings to children:
`<EventPopup />`, `<SidePanel />`, `<AuditTrailView />` — each receiving relevant state slices.
Navigation to deep-dive (`onOpenDeepDive`) uses the router's `navigate('/events/${eventId}/deep-dive')`.

Wire into `src/app/router.tsx`:
- Wrap the `"/"` route's element with `<ProgressiveDisclosureProvider>` so that popup/panel
  state is co-located with the map route.
- Add route `"/events/:eventId/deep-dive"` pointing to `<DeepDivePage />`.

**Tests to write first (TDD):**
- Initial state: `popupOpen=false`, `sidePanelOpen=false`, `auditTrailOpen=false`, `selectedEventId=null`
- `openPopup("evt-1")` → `popupOpen=true`, `selectedEventId="evt-1"`
- `expandToSidePanel()` after `openPopup` → `sidePanelOpen=true`, `popupOpen` remains true
- `openAuditTrail()` after `expandToSidePanel` → `auditTrailOpen=true`
- `closePopup()` resets all state to initial values (selectedEventId=null, all false)
- `closeSidePanel()` sets `sidePanelOpen=false` and `auditTrailOpen=false` without changing `popupOpen`
- `onExpandEvent({ event_id: "evt-1" })` → state equivalent to `openPopup("evt-1")` called
- Router test: route `"/events/evt-1/deep-dive"` renders `<DeepDivePage />` with correct `eventId` param

**AC covered**: AC-001, AC-002, AC-003

---

### TASK-013: Integration tests — progressive disclosure flows · M/TDD · tests/integration/progressive-disclosure/popup-render.test.tsx,tests/integration/progressive-disclosure/side-panel-expand.test.tsx,tests/integration/progressive-disclosure/audit-trail.test.tsx,tests/integration/progressive-disclosure/contrarian-callout.test.tsx

Write integration tests using React Testing Library + MSW.

`popup-render.test.tsx`:
- Render `<ProgressiveDisclosureProvider>` wrapping a stub map; call `onExpandEvent` with a
  mock `EventPulse`. MSW returns `PopupData` with `low_sample=false`. Assert popup is present
  with category, intensity, headline, exposed_holdings_count, at least one ticker, action_signal,
  confidence. Assert side panel is not visible. Assert no disclaimer shown.
- Same setup with `low_sample=true` in MSW response → disclaimer text is visible in popup.

`side-panel-expand.test.tsx`:
- Render provider; call `openPopup`. Click "Expand" button in popup. MSW returns
  `SidePanelData` with `is_contrarian=false`. Assert side panel slides in (has visible class
  or is in viewport). Assert sparklines section is present. Assert "Why this read?" link is
  visible. Assert analogies section is present.
- `low_sample=true` in `SidePanelData` → disclaimer visible in side panel.
- `social_posts` non-null in `SidePanelData` → "Triggering posts" section rendered.

`audit-trail.test.tsx`:
- Render provider with side panel open. Click "Why this read?". MSW returns `AuditTrailData`
  with 2 reasoning steps, a SHA, and a Langfuse URL. Assert audit trail overlay is visible.
  Assert prompt SHA is displayed. Assert 2 reasoning step entries rendered. Assert Langfuse
  link has correct `href`.

`contrarian-callout.test.tsx`:
- Render provider; open side panel. MSW returns `SidePanelData` with `is_contrarian=true`
  and `contrarian_callout="History shows conflicts in this region cause short-term commodity spikes."`.
  Assert `<ContrarianCallout />` is the first visible content block in the side panel. Assert
  the callout text matches the mock value. Assert it appears before the action_signal text.

**Tests to write first (TDD):**
(Each bullet above is a discrete test case; they drive the integration of all prior components.)

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: User clicks a map pulse → popup renders within 300ms with category, intensity, headline, exposed holdings count, ticker symbols with score delta, action signal, and confidence; side panel is collapsed → TASK-001, TASK-003, TASK-004, TASK-006, TASK-012, TASK-013
- AC-002: User clicks "Expand" in popup → side panel opens showing full analysis content including sparklines, analogies, and confidence; "Why this read?" link is visible → TASK-003, TASK-004, TASK-008, TASK-009, TASK-011, TASK-013
- AC-003: User clicks "Why this read?" → view opens showing: historical analogs with similarity scores, the prompt SHA that was used, and the agent reasoning steps stored from the workflow run → TASK-002, TASK-003, TASK-004, TASK-010, TASK-012, TASK-013
- AC-004: AI recommendation is contrarian → side panel leads with a highlighted "history says" callout block before the main recommendation text → TASK-003, TASK-007, TASK-009, TASK-013
- AC-005: sample_size < 5 → popup and side panel both display the low-sample disclaimer inline with the recommendation → TASK-002, TASK-003, TASK-006, TASK-007, TASK-009, TASK-013

## Acceptance Notes

The 300ms popup render target (AC-001) is a client-side render latency measured from
`onExpandEvent` call to first visible non-skeleton content. It is achievable for events
already in the TanStack Query cache (`staleTime: 30_000`). For a cold popup (first click on a
new event), the skeleton renders immediately and data arrives from `GET /popup` which reads
from the already-populated `ai_recommendation` table — no additional AI processing is
triggered by the popup endpoint. Network latency on a local Docker deployment is
negligible; on cloud deployments the 300ms budget leaves ~250ms for the API round trip
(the API query itself is a simple multi-table JOIN with no LLM calls).

The "Why this read?" audit trail depends on `agent_invocation` rows having been written by
a Mode B workflow for the event. For Mode A-only events (intensity 1–3 with no portfolio
match) that never triggered a deep-dive workflow, `get_audit_trail` returns the reasoning
chain from the Mode A `evaluate_quality` node if PLAN-F-016 is executed, or an empty
reasoning chain otherwise. The frontend `<AuditTrailView />` handles an empty `reasoning_steps`
array gracefully by displaying "No reasoning chain available for this event."

## Risks and Notes

- **MapLibre Popup vs React portal:** MapLibre `Popup` instances live outside the React
  VDOM. `<EventPopup />` must use a React portal (`createPortal`) targeting the MapLibre
  popup's DOM container so that TanStack Query and the React context tree remain accessible.
  This is the standard pattern for MapLibre + React — verify the portal approach in a spike
  before TASK-006.

- **Side panel z-index and map interaction:** The side panel must not block pointer events
  on the left portion of the map canvas. Set `pointer-events: none` on the panel's
  transparent left margin zone. Only the panel's visible right-side content area should
  capture pointer events.

- **Audit trail dependency on PLAN-F-016:** The reasoning chain in `agent_invocation` is
  populated by the `evaluate_quality` node from PLAN-F-016. In a pre-PLAN-F-016 environment
  the audit trail will have empty `reasoning_steps`. The API returns a 200 with an empty
  array rather than a 404 — the frontend renders "No reasoning chain available" gracefully.

- **Deep dive 202 retry loop:** `useDeepDive` uses `refetchInterval` set to 5 seconds when
  `data?.status === "pending"`. This creates a polling loop for up to ~7 minutes (the Mode B
  Event Deep-Dive workflow budget). After 7 minutes without a 200, the hook should give up
  and surface an error state rather than polling indefinitely. Add a `retryCount` guard: stop
  polling after 85 attempts (85 × 5s ≈ 7 minutes).

- **Social posts rendering:** Social posts are only present when the Twitter/X source is
  enabled (D8, off by default). The `social_posts` field in `SidePanelData` is `null` when
  social sources are disabled. The frontend does not render the "Triggering posts" section
  when `social_posts` is null or empty — this is already specified in TASK-009.

- **IDOR prevention:** `ProgressiveDisclosureRepository` enforces `tenant_id` ownership on
  all event lookups. A user who guesses a foreign `event_id` receives a 404 (not a 403),
  per the security baseline in DEV-STANDARDS §8 — 403 would confirm the event exists.
