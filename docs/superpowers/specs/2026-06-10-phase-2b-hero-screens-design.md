# Phase 2b — Hero Screens: Design Spec

**Date:** 2026-06-10
**Author:** brainstorming session (jakub + assistant)
**Status:** Approved for planning
**Branch target:** `phase-2b/hero-screens`
**Predecessor:** `docs/superpowers/specs/2026-06-08-phase-2a-intelligence-map-design.md`
**Successor (out of scope):** Phase 3 — Score Overlay & Polish spec.

---

## 0. Why this exists

Phase 1 established the frontend foundations (single API client, WebSocket wrapper, SSE
wrapper, auth, design tokens, route guards). Phase 2a applied those foundations to the
Intelligence Map, fixing five architectural violations and wiring the map to live backend
contracts.

The remaining five hero screens were written before Phase 1 existed. They are in the same
state the Intelligence Map was in at the start of Phase 2a: routes are mounted (or a
`<ComingSoon>` placeholder exists), the code is present, but the code has the same class of
violations:

1. Raw `fetch()` calls instead of `lib/api/client.ts:api()`
2. Raw `new WebSocket()` instead of `lib/api/ws.ts:apiSocket()`
3. Inline `style={{}}` instead of Tailwind design tokens

Additionally, every backend router for these screens is fully implemented but **not registered**
in `src/api/main.py`. The backend gap is entirely a mounting gap — no new endpoints need to be
written.

Phase 2b applies the same integration pass Phase 2a used, across all five screens, and adds
the `ProgressiveDisclosureProvider` wiring that Phase 2a deferred.

**Scope rule (inherited from Phase 1/2a, zero exceptions):**
The frontend never mocks backend behaviour. Where a backend integration is not configured,
the *backend* serves a deterministic stub and declares it via `GET /api/v1/system/integrations`.
The frontend surfaces "stub mode" honestly via `<StubModeBadge>`.

---

## 1. Goals and non-goals

### 1.1 Goals

1. All five routes render real, backend-connected content for authenticated, onboarded users.
2. **Zero** raw `fetch()` calls outside `lib/api/client.ts` in any modified file.
   Exception: POST+SSE in `qaApi.ts` (see §4.3) — raw `fetch` with `getAccessToken()` is
   the correct and only option since `lib/api/stream.ts` supports GET SSE only.
3. **Zero** raw `new WebSocket()` calls — only `apiSocket` from `lib/api/ws.ts`.
4. **Zero** inline `style={{}}` in any file touched by Phase 2b — Tailwind tokens only.
5. `ProgressiveDisclosureProvider` is wired into the router; the 3-level pulse-click flow
   (popup → side panel → deep dive) works end-to-end.
6. All five backend routers are mounted in `src/api/main.py`.
7. `npm run typecheck && lint && test && build` exit 0.
8. All existing tests continue to pass; new violations tests are added for each screen's
   migrated hooks.

### 1.2 Non-goals (Phase 3 or later)

- Score overlay activation — `useScoreOverlay` stays dormant; Phase 3 owns `/ws/scores`.
- Sector dropdown UX (MARKET_REGISTRY) — Phase 3.
- Storybook entries, screenshot CI — Phase 3.
- Server-side WS subscription filtering by bbox/sector — Phase 3.
- Portfolio / Watchlist / Screener wiring — not in the five Phase 2b screens.
- Password reset, OAuth2/SSO.
- Real AI/market-data integrations (backend stubs are acceptable at Phase 2b).

---

## 2. Dependencies on Phase 1 and Phase 2a

Phase 2b does not redefine any prior contract. It consumes:

| Dependency | Provided by | Used by |
|---|---|---|
| `lib/api/client.ts:api()` | Phase 1 | All 5 screens (replaces raw `fetch()`) |
| `lib/api/client.ts:getAccessToken()` | Phase 1 | Q&A POST+SSE auth header |
| `lib/api/ws.ts:apiSocket()` | Phase 1 | Company Detail Analyze-Now WebSocket |
| `lib/api/stream.ts:apiStream()` | Phase 1 | Not used in Phase 2b (GET SSE only; Q&A is POST+SSE) |
| `lib/api/errors.ts:ApiError` predicates | Phase 1 | Error states in all 5 screens |
| Tailwind v4 design tokens | Phase 1 | Tailwind migration of all modified files |
| `AuthProvider` / `RequireAuth` | Phase 1 | All screens (already wired via route guards) |
| `lib/api/integrations.ts:useIntegrations()` | Phase 2a | `<StubModeBadge>` in screens that surface stub state |
| `IntelligenceMap.onExpandEvent` injectable prop | Phase 2a | `ProgressiveDisclosureProvider` injects its handler |
| `ROUTES.events = '/events/:eventId/deep-dive'` | Phase 1 routes.ts | Router wiring for DeepDivePage |

Phase 2b does **not** modify `lib/api/client.ts`, `lib/api/ws.ts`, `lib/api/stream.ts`, or
any Phase 1/2a shared primitive. If a Phase 1/2a export has the wrong shape, Phase 2b updates
only the call site.

---

## 3. The root cause and the fix pattern

**Root cause:** Every Phase 2b screen was implemented against a non-existent "local API layer"
before Phase 1 established the canonical wrappers. The symptom set is identical across all five
screens: raw `fetch()` with `credentials: 'include'` but no `Authorization: Bearer` header
(so the JWT is not sent and requests fail when `httpOnly` cookie fallback is absent), raw
`new WebSocket()` without auth or reconnect logic, and inline `style={{}}` bypassing the
design system.

**The fix:**

| Violation | Fix | Notes |
|---|---|---|
| `fetch(url, { credentials: 'include' })` | `api<T>(path, init)` from `lib/api/client.ts` | Adds `Authorization: Bearer`, silent refresh, dedup, typed `ApiError` |
| `fetch()` for POST+SSE (Q&A only) | Keep `fetch()`, add `getAccessToken()` for auth header | `lib/api/stream.ts` is GET-only; POST+SSE has no wrapper — intentional exception |
| `new WebSocket(url)` | `apiSocket(path, handlers)` from `lib/api/ws.ts` | Adds auth, reconnect, typed handlers |
| `style={{ ... }}` | Tailwind utility classes using Phase 1 design tokens | Check `tailwind.config.ts` and token reference in Phase 1 spec §5 |

---

## 4. Per-screen breakdown

### 4.1 Progressive Disclosure — PLAN-F-020

The most complex screen: the only one with a `<ComingSoon>` still in the router, and the one
that requires provider-level wiring in addition to violation fixes.

#### 4.1.1 Router wiring (`src/frontend/app/router.tsx`)

Two changes:

1. **Wrap the root route** with `<ProgressiveDisclosureProvider>`:

   ```tsx
   // Before
   <Route path={ROUTES.home} element={<S><IntelligenceMapPage /></S>} />

   // After
   <Route
     path={ROUTES.home}
     element={
       <S>
         <ProgressiveDisclosureProvider>
           <IntelligenceMapPage />
         </ProgressiveDisclosureProvider>
       </S>
     }
   />
   ```

   The provider renders overlay siblings (popup, side panel, audit trail) as children of
   the router context so `useNavigate()` is available for deep-dive navigation.

2. **Replace `<ComingSoon>` with `<DeepDivePage>`** for `ROUTES.events`:

   ```tsx
   // Before
   <Route path={ROUTES.events} element={<ComingSoon feature="Event Deep-Dive" />} />

   // After (lazy-loaded, same pattern as other routes)
   const DeepDivePage = lazy(() =>
     import("@/features/progressive-disclosure/components/DeepDivePage")
       .then((m) => ({ default: m.DeepDivePage }))
   );
   <Route path={ROUTES.events} element={<S><DeepDivePage /></S>} />
   ```

#### 4.1.2 IntelligenceMapPage update (`src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`)

Currently `IntelligenceMapPage` holds a local `handleExpand` that calls `navigate()` directly,
bypassing the 3-level disclosure flow. Phase 2b replaces this with the provider's callback:

```tsx
// Before: direct navigation, skips popup/side-panel
const navigate = useNavigate();
const handleExpand = React.useCallback(
  (event: EventPulse) => navigate(`/events/${event.event_id}/deep-dive`),
  [navigate],
);

// After: uses provider's onExpandEvent (activates popup → side panel → deep dive flow)
const { onExpandEvent } = useDisclosure();
// Pass onExpandEvent directly to <IntelligenceMap onExpandEvent={onExpandEvent} />
```

`IntelligenceMap` already accepts `onExpandEvent?: (event: EventPulse) => void` (Phase 2a,
PLAN-F-019 TASK-011). The internals of `IntelligenceMap.tsx` do **not** change.

#### 4.1.3 Frontend violations

`src/frontend/features/progressive-disclosure/` was written before Phase 1. All components
use wall-to-wall `style={{}}` and `disclosure.api.ts` uses raw `fetch()` with manually
assembled `Authorization: Bearer` headers.

**Files requiring violation fixes:**

| File | Violation | Fix |
|---|---|---|
| `api/disclosure.api.ts` | Raw `fetch()` + manual auth header assembly | Replace `disclosureFetch()` internals with `api<T>()` from `lib/api/client.ts`; delete `getAuthToken()` and `authHeaders()` helpers |
| `components/EventPopup.tsx` | Inline styles throughout | Tailwind migration |
| `components/SidePanel.tsx` | Inline styles throughout | Tailwind migration |
| `components/DeepDivePage.tsx` | Inline styles throughout | Tailwind migration |
| `components/AuditTrailView.tsx` | Inline styles throughout | Tailwind migration |
| `components/ContrarianCallout.tsx` | Inline styles | Tailwind migration |
| `components/LowSampleDisclaimer.tsx` | Inline styles | Tailwind migration |
| `components/SidePanelAnalogies.tsx` | Inline styles | Tailwind migration |
| `components/SidePanelSparkline.tsx` | Inline styles | Tailwind migration |
| `ProgressiveDisclosureProvider.tsx` | None — no inline styles, no raw fetch | No change |

The Tailwind migration follows the Phase 2a precedent: every `style={{ color, background,
fontSize, padding, ... }}` becomes a Tailwind class using the Phase 1 design token set
(`text-text`, `bg-surface-1`, `text-muted`, `border-default`, etc.). See Phase 1 spec §5
for the full token reference.

#### 4.1.4 Backend mounting

`src/api/progressive_disclosure/` is fully implemented (router, service, repository,
schemas, interfaces). Add to `src/api/main.py`:

```python
from src.api.progressive_disclosure.router import router as disclosure_router
app.include_router(disclosure_router, prefix="/api/v1")  # PLAN-F-020: Progressive Disclosure
```

The `disclosure_router` has its own prefix `/events` and serves:
- `GET /api/v1/events/{event_id}/popup`
- `GET /api/v1/events/{event_id}/side-panel`
- `GET /api/v1/events/{event_id}/audit-trail`
- `GET /api/v1/events/{event_id}/deep-dive`

**Note on path conflict:** `src/api/v1/events.py` (the map's `GET /api/v1/events`) must also
be mounted. Its prefix is `/events` under `/api/v1`. Verify no path overlap with the
disclosure router's `/{event_id}/popup` etc. at mount time — they are distinct paths.

---

### 4.2 Briefs Reader — PLAN-F-026

Route: `/briefs` → `<BriefsPage>`, `/briefs/:briefId` → `<BriefDetailPage>`.
Already in the router. No `<ComingSoon>` placeholder.

#### 4.2.1 Frontend violations

| File | Violation | Fix |
|---|---|---|
| `hooks/useBriefs.ts` | Raw `fetch()` (lines 24–29) | `api<BriefListApiResponse>()` |
| `hooks/useBriefDetail.ts` | Raw `fetch()` (line 12) | `api<BriefDetailApiResponse>()` |
| `hooks/useFeedback.ts` | Raw `fetch()` (line 16) | `api<void>()` with POST body |
| `BriefDetailPage.tsx` | Inline `style={{}}` (6 occurrences) | Tailwind migration |
| `BriefListItem.tsx` | `style={{ cursor: 'pointer' }}` | `cursor-pointer` class |

#### 4.2.2 Backend mounting

```python
from src.api.briefs.briefs_router import router as briefs_router
from src.api.briefs.feedback_router import router as briefs_feedback_router
app.include_router(briefs_router, prefix="/api/v1")        # PLAN-F-026: Briefs list + detail
app.include_router(briefs_feedback_router, prefix="/api/v1")  # PLAN-F-026: Brief feedback
```

---

### 4.3 Q&A Chat — PLAN-F-027

Route: `/qa` → `<QAChatPanel>`.
Already in the router. Backend (`qa_router`) **already mounted** in Phase 1/2a.

#### 4.3.1 Frontend violations

| File | Violation | Fix |
|---|---|---|
| `qaApi.ts` — `createQASession()` | Raw `fetch()` without `Authorization` header | `api<CreateSessionResponse>('/qa/sessions', { method: 'POST' })` |
| `qaApi.ts` — `submitQuestionFetch()` | Raw `fetch()` for POST+SSE; no `Authorization` header | Keep raw `fetch()`; add `Authorization: Bearer ${getAccessToken()}` header using `getAccessToken()` from `lib/api/client.ts` |

**POST+SSE rationale:** `lib/api/stream.ts:apiStream()` issues a GET request — it cannot
be used for Q&A's POST-based SSE stream. Raw `fetch()` with `ReadableStream` is the only
correct pattern. This is not a violation of Phase 1's rule, which says `api()` must be
used for standard request/response calls. The SSE call is streaming — just ensure
`getAccessToken()` is imported and used for the auth header.

#### 4.3.2 Backend mounting

No change — `qa_router` is already registered.

---

### 4.4 Company Detail + Analyze-Now — PLAN-F-023

Route: `/companies/:ticker` → `<CompanyDetailPage>`.
Already in the router.

#### 4.4.1 Frontend violations

| File | Violation | Fix |
|---|---|---|
| `hooks/useCompanyDetail.ts` | Raw `fetch()` (line 24) | `api<CompanyDetailResponse>()` |
| `hooks/useRecommendationTrackRecord.ts` | Raw `fetch()` (line 43) | `api<TrackRecordResponse>()` |
| `hooks/useScoreHistory.ts` | Raw `fetch()` (line 25) | `api<ScoreHistoryResponse>()` |
| `hooks/useAnalyzeNow.ts` | Raw `fetch()` (line 100) + **`new WebSocket()`** (line 70) | `api<AnalysisRunResponse>()` + `apiSocket(path, handlers)` |
| `ScoreBreakdownPanel.tsx` | `style={{ height: ... }}` (line 55) | Use Tailwind arbitrary value or CSS variable |

**`useAnalyzeNow.ts` WebSocket migration:** The current code constructs `new WebSocket(buildWsUrl(newRunId))`. Replace with `apiSocket('/ws/analysis/' + newRunId, { onMessage, onError, onClose })`. Verify the path matches the backend's WebSocket route for analysis runs.

#### 4.4.2 Backend mounting

```python
from src.api.v1.company_detail_router import router as company_detail_router
app.include_router(company_detail_router, prefix="/api/v1")  # PLAN-F-023: Company Detail
```

---

### 4.5 AI Audit Console — PLAN-F-029

Route: `/admin/ai-audit` → `<AiAuditConsolePage>` (guarded by `<RequireAdmin>`).
Already in the router.

#### 4.5.1 Frontend violations

| File | Violation | Fix |
|---|---|---|
| `hooks/useAdminOverride.ts` | Raw `fetch()` (line 29) | `api<void>()` |
| `hooks/useCalibration.ts` | Raw `fetch()` (lines 43, 50) | `api<CalibrationResponse>()` |
| `hooks/useDecisionLog.ts` | Raw `fetch()` (line 67) | `api<DecisionLogResponse>()` |
| `hooks/usePromptHistory.ts` | Raw `fetch()` (line 23) | `api<PromptHistoryResponse>()` |
| `hooks/useRollback.ts` | Raw `fetch()` (line 24) | `api<void>()` |
| `hooks/useWorkflowHistory.ts` | Raw `fetch()` (lines 63, 69) | `api<WorkflowHistoryResponse>()` |
| `DecisionLogPanel.tsx` | Inline `fetch()` (line 36) | Extract to hook, use `api<DecisionDetailResponse>()` |
| `WorkflowHistoryPanel.tsx` | Inline `fetch()` (line 21) | Extract to hook, use `api<WorkflowDetailResponse>()` |

**Inline `fetch()` in panel components:** `DecisionLogPanel.tsx:36` and
`WorkflowHistoryPanel.tsx:21` call `fetch()` directly inside the component body. These must
be extracted into small dedicated hooks (`useDecisionDetail`, `useWorkflowDetail`) or
absorbed into the existing hooks. No business logic may live in the router layer.

#### 4.5.2 Backend mounting

```python
from src.api.admin.audit.audit_router import router as audit_router
app.include_router(audit_router, prefix="/api/v1")  # PLAN-F-029: Admin AI Audit Console
```

---

## 5. Backend mounting — consolidated diff for `src/api/main.py`

The entire Phase 2b backend change is adding six `include_router` calls and their imports.
No new Python modules are written.

```python
# Phase 2a contract — was missing from main.py, add here
from src.api.v1.events import router as events_v1_router

# Phase 2b routers (all fully implemented; mounting only)
from src.api.progressive_disclosure.router import router as disclosure_router
from src.api.briefs.briefs_router import router as briefs_router
from src.api.briefs.feedback_router import router as briefs_feedback_router
from src.api.admin.audit.audit_router import router as audit_router
from src.api.v1.company_detail_router import router as company_detail_router

# Mount (add after existing include_router calls)
app.include_router(events_v1_router, prefix="/api/v1")       # Phase 2a: GET /api/v1/events
app.include_router(disclosure_router, prefix="/api/v1")      # PLAN-F-020: Progressive Disclosure
app.include_router(briefs_router, prefix="/api/v1")          # PLAN-F-026: Briefs list + detail
app.include_router(briefs_feedback_router, prefix="/api/v1") # PLAN-F-026: Brief feedback
app.include_router(audit_router, prefix="/api/v1")           # PLAN-F-029: AI Audit Console
app.include_router(company_detail_router, prefix="/api/v1")  # PLAN-F-023: Company Detail
```

---

## 6. End state

After Phase 2b ships:

| Route | State |
|---|---|
| `/` | Intelligence Map. Pulse click → `ProgressiveDisclosureProvider` popup (Level 1). "Expand" → side panel (Level 2). "Full Analysis" → deep dive (Level 3). |
| `/events/:id/deep-dive` | `<DeepDivePage>` renders full analysis memo, scenario tree, analogies, companies. Polls every 5s for pending deep-dive. |
| `/briefs` | Briefs list via `GET /api/v1/briefs`. |
| `/briefs/:id` | Brief detail via `GET /api/v1/briefs/{id}`. |
| `/qa` | Q&A chat with POST session creation + POST+SSE streaming, both auth-correct. |
| `/companies/:ticker` | Company detail with score breakdown, track record, geo-events. Analyze-Now triggers WS-streamed analysis via `apiSocket`. |
| `/admin/ai-audit` | Decision log, prompt history, calibration, workflow history — all via `api()`. |

**Quality bar:**
- `npm run typecheck && lint && test && build` all exit 0
- Zero raw `fetch()` outside `lib/api/client.ts` (grep: `grep -r "= await fetch\|return fetch" src/frontend/features src/frontend/pages`)
- Zero `new WebSocket(` in frontend source
- Zero `style={{` in any file modified by Phase 2b
- All prior tests pass; new tests cover migrated hooks

---

## 7. Risks and notes

**Tailwind migration scope:** 8 progressive-disclosure components have wall-to-wall inline
styles. This is the largest single sub-task. Follow the Phase 2a precedent exactly: use
the token reference from Phase 1 spec §5 (`text-text`, `bg-surface-1`, `text-muted`,
`border-default`, `text-signal`, etc.) and Tailwind arbitrary values only where no token fits.
Do not invent new tokens.

**`disclosure.api.ts` internal helpers:** The file contains `getAuthToken()` and
`authHeaders()` helper functions that replicate what `lib/api/client.ts` already does.
Both must be deleted when migrating to `api()`. The `DisclosureFetchError` typed error class
must be replaced with Phase 1's `ApiError` where the error is surfaced to the user.

**`useAnalyzeNow.ts` WebSocket path:** Verify `buildWsUrl(newRunId)` constructs the correct
path before migrating to `apiSocket`. The `apiSocket` path parameter must be the path
component only (e.g., `/ws/analysis/{run_id}`), not a full URL. If `buildWsUrl` returns a
full URL, extract the path.

**Path conflict check:** `src/api/v1/events.py` and `src/api/progressive_disclosure/router.py`
both register routes under `/api/v1/events/`. Confirm FastAPI resolves `GET /api/v1/events`
(no trailing segment) to the map router and `GET /api/v1/events/{event_id}/popup` to the
disclosure router. These are distinct path shapes and should not conflict, but verify at
mount time.

**`DecisionLogPanel` and `WorkflowHistoryPanel` inline fetch:** Extracting inline `fetch()`
calls into dedicated hooks is required (no `fetch()` in component bodies). If the hooks
have a narrow scope, they can be local to the panel file rather than added to the hooks
directory — single-responsibility, not forced extraction.

**Q&A `credentials: 'include'` vs Bearer:** The current `fetch()` calls use
`credentials: 'include'` only. After migration, `createQASession` uses `api()` (which sends
Bearer), and `submitQuestionFetch` adds `Authorization: Bearer ${getAccessToken()}`. Remove
`credentials: 'include'` from the SSE `fetch()` call — it is not needed when Bearer auth is
in use and may cause CORS preflight issues.

**Phase 2a gap — `GET /api/v1/events` unmounted:** The map's REST endpoint was defined in
Phase 2a but never registered in `main.py`. Including its mount in Phase 2b's `main.py`
diff corrects this. The map currently serves empty events (the stub returns `[]`); after
mounting, stub events will be served.

---

## 8. Phase 3 preview (not in scope)

- `useScoreOverlay` activation and `/ws/scores` WebSocket endpoint
- `GET /api/v1/scores/history` for sparkline data on the score overlay
- Sector dropdown UX tied to `MARKET_REGISTRY`
- Server-side WS subscription filtering
- Storybook and screenshot CI

---

*End of spec.*
