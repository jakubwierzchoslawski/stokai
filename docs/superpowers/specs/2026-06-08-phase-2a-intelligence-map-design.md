# Phase 2a — Intelligence Map: Design Spec

**Date:** 2026-06-08
**Author:** brainstorming session (jakub + assistant)
**Status:** Approved for planning
**Branch target:** `phase-2a/intelligence-map`
**Predecessor:** `docs/superpowers/specs/2026-06-08-phase-1-frontend-foundation-design.md`
**Successor (out of scope, to be written after Phase 2a ships):** Phase 2b — Hero Screens spec.

---

## 0. Why this exists

The intelligence map is StokAI's hero route — the first screen a logged-in
user sees after onboarding. Phase 1 reserved `/` for
`<ComingSoon plan="PLAN-F-019" />` while it consolidated frontend foundations
(API client, auth, visual tokens, shadcn primitives, SSE/WS wrappers).

The pre-Phase-1 implementations of the map (`features/intelligence-map/`) were
written before those foundations existed. They contain five architectural
violations:

1. `events.api.ts` calls raw `fetch()` and reads tokens from `localStorage`.
2. `useHistoricalEvents.ts` does the same.
3. `useScoreAtTime.ts` does the same (and its result is unused at the call site).
4. `useEventFeed.ts` ships its own inline WebSocket manager.
5. `IntelligenceMap.tsx` uses wall-to-wall inline `style={{}}` instead of the
   Phase 1 design tokens.

Phase 2a wires the map to live backend APIs through Phase 1's foundations,
fixes all five violations, defines the backend contracts for events REST and
WS, and replaces the placeholder so route `/` works against a real backend.

**Scope rule (inherited from Phase 1):** the frontend never mocks backend
behaviour. Where market-data or news integrations are not configured, the
*backend* returns a deterministic stub event set, and the frontend surfaces
"stub mode" honestly via `<StubModeBadge>`.

---

## 1. Goals & non-goals

### 1.1 Goals

1. Route `/` renders `<IntelligenceMapPage>` against a live backend (REST + WS)
   for authenticated, onboarded users.
2. All five Phase 1 architectural violations resolved inside
   `features/intelligence-map/`.
3. Backend contracts for `GET /api/v1/events` (live + historical) and
   `WSS /api/v1/events/feed` defined, documented, and conformant.
4. Pulse click opens a MapLibre Popup with headline + intensity + affected
   companies count + "View details →" button that navigates to
   `/events/:eventId/deep-dive` (which renders `<ComingSoon plan="PLAN-F-020">`
   until Phase 2b ships).
5. Empty / loading / error states use Phase 1 patterns (`ApiError` predicates,
   typed error toasts, `<StubModeBadge>` for stubbed integrations).
6. `npm run typecheck && lint && test && build` exit 0. Phase 1 lint rules
   (no `fetch` outside `lib/api/client.ts`; no inline style colors/spacing)
   leave zero violations inside `features/intelligence-map/`.
7. Performance: smooth pan/zoom with up to 1000 events; supercluster runs
   off-main-thread; frame time during continuous pan stays under 16 ms.

### 1.2 Non-goals (explicitly Phase 2b / Phase 3)

- **Phase 2b:** Progressive Disclosure side-panel consumer of `onExpandEvent`.
- **Phase 3:** Score overlay WebSocket consumer (`useScoreOverlay` stays in
  place but dormant; `profileActive=false` default is never flipped in
  Phase 2a).
- **Phase 3:** Sector dropdown UX (uses MARKET_REGISTRY); the current minimal
  `MapContextSwitcher` is kept as-is.
- **Phase 3:** `GET /api/v1/scores/history` contract and a fresh
  `useScoreSnapshot` hook. Phase 2a deletes the dead `useScoreAtTime` rather
  than patch it.
- **Phase 3:** Storybook entries for map components; screenshot / visual
  regression CI.
- **Phase 3:** Server-side WS subscription filtering by bbox/sector.

---

## 2. Dependencies on Phase 1

Phase 2a will not begin implementation until the following Phase 1 steps have
shipped on `phase-1/foundation`:

| Phase 1 step | What Phase 2a needs |
|---|---|
| Step 7 — Auth | `AuthProvider`, `useAuth()`, `getAccessToken()` from `lib/api/client.ts` |
| Step 8 — Layout | `AppShell`, `TopNav` (`h-12`), sidebar opt-in via outlet context |
| Step 9 — Routes | Route `/` exists with `<ComingSoon plan="PLAN-F-019" />` — Phase 2a swaps it |
| Step 13 — Broken-import stubs | `features/intelligence-map/lib/empty-state-message.ts` and `time-mode-empty-state.ts` already created |
| Step 14 — Test migration | All `intelligence-map` tests already migrated to vitest; Phase 2 wiring tests `.skip`'d with explanatory comments |

Phase 2a does **not** redefine any Phase 1 contract. If Phase 1 ships a
different `AuthContextValue` shape than the Phase 1 spec defines, Phase 2a
updates its consumer call sites only.

The intelligence-map directory is the canonical location after Phase 1
Step 12 (which lists `features/intelligence-map/*` as "unchanged"), so there
is no directory-level conflict between the two phases.

---

## 3. Backend contracts (new for Phase 2a)

### 3.1 `GET /api/v1/events` — unified live + historical endpoint

Single endpoint, two modes selected by query params. The presence of `from`
and `to` means historical; their absence means live.

**Query parameters:**

| Param | Required | Description |
|---|---|---|
| `bbox` | optional | `"west,south,east,north"` (floats); clips events to viewport |
| `zoom` | optional | 0–22 integer; informs server-side LOD pruning at low zooms |
| `context` | optional | `global` \| `portfolio` \| `sector` (default `global`) |
| `sector` | required when `context=sector` | sector code (e.g., `GICS-45`) |
| `from` | required for historical | ISO-8601 datetime (UTC) |
| `to` | required for historical | ISO-8601 datetime (UTC) |

**Response (200):**

```json
{
  "data": [ /* EventPulse[] — schema matches frontend types/map.types.ts */ ],
  "meta": {
    "request_id": "uuid",
    "elapsed_ms": 12,
    "count": 247,
    "truncated": false,
    "max_per_request": 1000
  }
}
```

**`EventPulse` schema (frozen for Phase 2a):**

```ts
interface EventPulse {
  event_id: string;             // UUID
  category: string[];
  intensity: 1 | 2 | 3 | 4 | 5;
  headline: string;
  timestamp: string;            // ISO 8601
  lat: number;
  lon: number;
  relevance_window_end: string; // ISO 8601
  affected_companies: Array<{
    company_id: string;
    ticker: string;
    score_delta: number;
  }>;
}
```

The frontend validates this with a zod schema in
`features/intelligence-map/api/events.schema.ts` per Phase 1 §6.8 contract
drift detection.

**Behaviour:**

- Live mode returns events where `timestamp <= now < relevance_window_end`.
- Historical mode returns events where `timestamp ∈ [from, to]`, sorted
  ascending by `timestamp`.
- `truncated: true` when the result hits `max_per_request` (1000). Frontend
  shows an empty-state hint ("zoom in or narrow date range"). No pagination
  in Phase 2a — date range is the user's primary filter.
- `context=portfolio` filters to events touching the caller's portfolio
  holdings.
- `context=sector` requires `sector` param; the backend returns
  `400 VALIDATION_FIELD_REQUIRED` otherwise.

**Cache headers:**

- Live: `Cache-Control: no-cache`.
- Historical: `Cache-Control: public, max-age=3600` for windows ending more
  than 24 h in the past (events older than 24 h are immutable).

**Error codes** (Phase 1 envelope, §6.2):

- `401 AUTH_TOKEN_EXPIRED` — handled by `client.ts` silent refresh.
- `400 VALIDATION_FIELD_REQUIRED` — malformed bbox/date, missing `sector`.
- `503 EXTERNAL_UNAVAILABLE` — never raised when integrations are in
  `mode: stub`; the backend returns its seeded fixture instead.

### 3.2 `WSS /api/v1/events/feed?token=<access_token>` — live push

Phase 1 §6.4 pre-defined the wire frames. Phase 2a confirms and extends:

**Frames (server → client):**

```json
{ "type": "event.created", "event": { /* EventPulse */ } }
{ "type": "event.updated", "event": { /* EventPulse */ } }
{ "type": "ping" }
```

**Frames (client → server):** none in Phase 2a. (Phase 3 may add subscription
filters.)

**Behaviour:**

- Server pushes events **created or updated after connection establishment**.
  There is no initial sync — the frontend seeds from the REST
  `GET /api/v1/events` call; WS appends only. This avoids cross-channel
  deduplication in Phase 2a.
- `ping` every 25 s for keepalive; client ignores `ping` frames.
- Server broadcasts globally; the client filters by bbox/context/sector
  locally. Server-side subscription filtering is Phase 3.
- Malformed frames: server logs and drops; client silently drops (already
  implemented).

**Auth and reconnect:**

- Token via `?token=<access_token>` query param (Phase 1 standard;
  `apiSocket` injects it).
- On `4401` close (token expired): client triggers `auth.refresh()`;
  reconnects with exponential backoff (1 s, 2 s, 4 s, 8 s, max 30 s).
- On normal close (`1000`) or React unmount: no reconnect.

**Proxy:** Phase 1 `vite.config.ts` proxies `/api/v1/events/feed` through the
`/api` rule (HTTP upgrade to WS). Phase 2a uses
`apiSocket('/api/v1/events/feed', …)`, not the existing code's `/ws/events`.

### 3.3 Score endpoints — explicitly out of scope

`GET /api/v1/scores/history` and `WSS /ws/scores` are **not** defined by
Phase 2a. They remain Phase 3 contracts. Phase 2a removes the dead
`useScoreAtTime` call site in `IntelligenceMap.tsx` and deletes the hook
file. `useScoreOverlay` stays in place but is dormant
(`profileActive=false` default).

### 3.4 Backend stub-mode behaviour

Per Phase 1 §6.5, `GET /api/v1/system/integrations` declares each
integration's mode. For events:

- If `market_data.mode === "stub"` **or** `news.mode === "stub"`, the
  backend serves a deterministic seeded event set: ~50 events distributed
  across the globe with fixed `event_id`s and timestamps relative to "now".
- The frontend renders `<StubModeBadge integration="news" />` (and/or
  `"market_data"`) top-left of the map canvas when either integration is in
  `stub` mode.
- WS in stub mode: the backend pushes one synthetic event every 30 s with
  a rotating category — proves the live channel works end-to-end without
  real data.

---

## 4. Frontend migration plan

### 4.1 The five violation fixes

**Fix 1 — `events.api.ts` → `lib/api/client.ts`**

Rewrite using `api<EventPulse[]>('/events?…')`. Drop the inline
`EventFetchError` class (replaced by `ApiError` from `lib/api/errors.ts`).
Drop hand-rolled `isValidEventPulse` and `validateEventsResponse`; replace
with a zod schema in `events.schema.ts` parsed at the call site. Drop the
`getAuthToken` localStorage accessor entirely.

**Fix 2 — `useHistoricalEvents.ts` → `lib/api/client.ts`**

Same pattern as Fix 1. Imports the same zod schema from
`events.schema.ts` — single source of truth for `EventPulse` validation.

**Fix 3 — `useScoreAtTime.ts` → delete**

The hook is invoked from `IntelligenceMap.tsx` but its `scoreAtTimeData`
return is never read (verified by grep). Delete the hook file, delete the
test file, remove the call site. Phase 3 rebuilds this cleanly against the
proper score-history endpoint.

**Fix 4 — `useEventFeed.ts` → `apiSocket`**

Remove the inline `subscribeToEventChannel` function. Replace with:

```ts
const handle = apiSocket('/api/v1/events/feed', {
  onMessage: (msg) => {
    // parse frame; if event.created|event.updated, append via setWsEvents
  },
  onClose: (ev) => {
    // exp-backoff reconnect handled by apiSocket itself
  },
});
```

Cleanup: `handle.close()`. The 4401 → refresh → reconnect logic lives
entirely inside the Phase 1 `lib/api/ws.ts` wrapper.

**Fix 5 — `IntelligenceMap.tsx` → Tailwind tokens**

Every `style={{}}` declaring colors, spacing, or layout is converted to
Tailwind classes using the Phase 1 design tokens:

- Root container:
  `relative flex h-[calc(100vh-3rem)] w-full flex-row overflow-hidden`
  (height accounts for the `h-12` `TopNav`).
- Map canvas div: `relative h-full min-w-0 flex-1`.
- Right side panel:
  ```ts
  cn(
    'h-full shrink-0 overflow-y-auto border-l border-subtle bg-surface-1',
    breakpoint === 'lg' || breakpoint === 'xl' ? 'w-[360px]' : 'w-[280px]'
  )
  ```
- Loading chip and drawer-toggle button: shadcn `Badge` and `Button`
  primitives.

The only `style` allowed afterward is dynamic geometry that cannot be
expressed as a class (e.g., MapLibre marker absolute positions computed
from coordinates).

### 4.2 Child-component Tailwind sweep

The following React-rendered child components receive the same treatment:

`FilterPanel`, `MapContextSwitcher`, `TimeModeToolbar`,
`PlaybackControls`, `EmptyState`, `ScoreOverlay`, `ClusterDonut`.

MapLibre-layer components (`PulseLayer`, `ClusterLayer`) and the worker
(`supercluster.worker.ts`) render through canvas / imperative APIs and have
no DOM styles to migrate.

### 4.3 Pieces to add

**`VITE_MAP_STYLE_URL` environment variable.** Add to the `lib/env.ts` zod
schema as an optional string with default
`https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` (already
the in-code fallback). Lets ops override per environment.

**`useIntegrations()` shared hook in `lib/api/integrations.ts`.** A
TanStack Query hook over `GET /api/v1/system/integrations` with
`staleTime: 5 * 60 * 1000`. Used by the map (for `<StubModeBadge>`) and by
the admin/system page. Phase 2a creates this file if Phase 1 has not.

**Pulse-click MapLibre Popup.** Replaces the current `console.log` stub. On
pulse click:

1. MapLibre Popup anchors at the pulse coordinate.
2. Content (DOM, themed via Tailwind classes that resolve through the
   global stylesheet — confirmed: MapLibre popups attach to the map
   container):
   - Headline (1–2 lines, `text-base font-medium`).
   - Intensity badge (color-mapped to `--pulse-*` tokens).
   - Affected-companies count (`text-xs text-muted`).
   - "View details →" `Button` (variant `default`, size `sm`).
3. Clicking "View details" calls
   `navigate('/events/' + event_id + '/deep-dive')`. Until Phase 2b ships,
   that route renders `<ComingSoon plan="PLAN-F-020" />` — clean handoff,
   no broken link.
4. The `onExpandEvent` prop continues to fire so Phase 2b's full
   side-panel consumer can subscribe later.

The popup is the **first-level progressive disclosure**; Phase 2b's full
side-panel is the second level.

**`<StubModeBadge>` shared primitive.** A new component at
`src/frontend/lib/ui/StubModeBadge.tsx` (shared, because Phase 1 §6.5
declares "features depending on a stubbed integration render
`<StubModeBadge integration="market_data" />`" — implying any feature can
mount it). Reads `useIntegrations()`. If `market_data.mode === "stub"` or
`news.mode === "stub"`, renders top-left of the map canvas:

```
absolute left-4 top-4 z-50 rounded-md border border-subtle
bg-surface-2/90 px-3 py-1.5 text-xs text-muted backdrop-blur
```

Click → popover with the `reason` field from the integrations payload and a
link to `/admin/system` (admin only; the link hides for non-admin users).

### 4.4 Route mount

In `src/frontend/app/router.tsx`, swap:

```tsx
// Before (Phase 1 Step 9):
<Route path={ROUTES.home} element={<ComingSoon plan="PLAN-F-019" />} />

// After (Phase 2a):
<Route path={ROUTES.home} element={<IntelligenceMapPage />} />
```

`IntelligenceMapPage` is a thin wrapper component at
`src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`. Pseudo-code
(exact AppShell-context API depends on what Phase 1 Step 8 ships):

```tsx
export function IntelligenceMapPage() {
  const navigate = useNavigate();
  // Hide the AppShell sidebar by default on this route. The mechanism is
  // whatever Phase 1 §5.7 ("Sidebar opt-in per route via outlet context")
  // landed on — outlet context, layout prop, or route data.
  useAppShellLayout({ sidebar: 'hidden' });

  return (
    <>
      <StubModeBadge />
      <IntelligenceMap
        onExpandEvent={(event) =>
          navigate(`/events/${event.event_id}/deep-dive`)
        }
      />
    </>
  );
}
```

### 4.5 Migration sequence (13 commits, green-after-each)

| # | Step | Size |
|---|---|---|
| 1 | Add `VITE_MAP_STYLE_URL` to `lib/env.ts` zod schema | S |
| 2 | Add `useIntegrations()` hook in `lib/api/integrations.ts` (if not present) | S |
| 3 | Migrate `events.api.ts` — `api<T>()` + zod schema. Tests updated. | M |
| 4 | Migrate `useHistoricalEvents.ts` — shares the zod schema. Tests updated. | M |
| 5 | Delete `useScoreAtTime.ts` and remove its unused call from `IntelligenceMap.tsx` | S |
| 6 | Migrate `useEventFeed.ts` to `apiSocket('/api/v1/events/feed', …)`. Tests updated. | M |
| 7 | Tailwind sweep on `IntelligenceMap.tsx` (height `calc(100vh-3rem)`) | M |
| 8 | Tailwind sweep on 7 child components | M |
| 9 | MapLibre Popup on pulse click + "View details" navigation | M |
| 10 | `<StubModeBadge>` component + mount in `IntelligenceMapPage` | S |
| 11 | Replace `<ComingSoon plan="PLAN-F-019" />` with `<IntelligenceMapPage />` | S |
| 12 | Un-skip Phase 2 wiring tests (Phase 1 Step 14 marked them); update to vitest + msw against §3 contracts | M |
| 13 | Backend audit: confirm `GET /api/v1/events` and `WSS /api/v1/events/feed` conform to §3; file backend tasks for any gap | S |

Total: 6 S + 6 M, no L. Each step builds green. Commits are independent
enough to interleave reviewable PRs.

---

## 5. Visual integration

- **AppShell context:** `IntelligenceMapPage` declares `{ sidebar: false }`
  via outlet context. The sidebar toggle in `TopNav` can reveal it on
  demand without remounting the map.
- **Map canvas height:** `calc(100vh − 3rem)` below the `h-12` `TopNav`.
- **Right side panel:** `360px` at `lg+`, `280px` at `md`, drawer at `sm`.
  Classes converted from inline `style` to Tailwind tokens.
- **`<StubModeBadge>`:** absolute top-left of the map canvas, `z-50`,
  `bg-surface-2/90 backdrop-blur`, `text-xs text-muted`.
- **Pulse popup:** MapLibre Popup with Tailwind-styled DOM content. The
  popup container picks up the global stylesheet because it attaches to
  the map container DOM (confirmed against MapLibre 4.x).
- **Loading indicator:** small floating chip top-center of the map canvas;
  shadcn `Badge` primitive.
- **Drawer toggle (mobile):** shadcn `Button variant="default" size="sm"`,
  fixed bottom-right.

---

## 6. Acceptance criteria

Phase 2a is "done" when every AC below is true.

**AC-1 — Route**

- Path `/` renders `<IntelligenceMapPage>` for authenticated users; anonymous
  users still redirect to `/login` via Phase 1 `RequireAuth`.
- Onboarding-incomplete users still land on `/onboarding` via the Phase 1
  `OnboardingGate`.
- The AppShell sidebar is hidden by default on `/`; the `TopNav` toggle
  reveals it without remounting the map.

**AC-2 — Build & lint**

- `npm run typecheck`, `npm run lint --max-warnings=0`, `npm run test`,
  `npm run build` all exit 0.
- Phase 1 lint rule: no `fetch` call against `/api/...` outside
  `lib/api/client.ts`. Zero violations in `features/intelligence-map/`.
- Phase 1 lint rule: no `WebSocket` / `EventSource` constructor outside
  `lib/api/`. Zero violations in `features/intelligence-map/`.
- No inline `style={{}}` color / spacing / layout in
  `features/intelligence-map/`. Allowed: dynamic geometry only (e.g.,
  MapLibre marker absolute positions).

**AC-3 — Visual system**

- All seven React child components use Tailwind tokens; zero hardcoded
  hex / rgb / hsl colors outside `tokens.css` and `lib/viz.ts`.
- Map canvas fills `100vh − 3rem`; resizes correctly on viewport resize
  without overflow.
- Right side panel: `360px` at `lg+`, `280px` at `md`, drawer at `sm`.
  Drawer toggle visible only at `sm`.
- Dark theme is default; light theme renders without contrast failures
  (Lighthouse a11y ≥ 95 on `/`).
- All interactive elements have visible focus rings (Phase 1 §4.10).

**AC-4 — Backend contracts conform**

- `GET /api/v1/events` (live mode) returns `EventPulse[]` in the standard
  envelope with `meta.count` and `meta.truncated`. Schema validated by zod
  on the client; mismatches throw
  `ApiError(0, "CONTRACT_MISMATCH", ...)`.
- `GET /api/v1/events?from=&to=` returns historical events sorted ascending
  by `timestamp`.
- `WSS /api/v1/events/feed?token=` accepts the access token via query
  param and emits `event.created` / `event.updated` / `ping` frames
  matching Phase 1 §6.4 shape.
- WS reconnects on `4401` via `apiSocket` (Phase 1 wrapper) — verified by
  integration test.
- `GET /api/v1/system/integrations` already exists from Phase 1 §6.5; no
  new endpoint here.

**AC-5 — UX flows**

- Map loads cluster + pulse rendering within 1.5 s of route entry on the
  synthetic stub dataset (~50 events).
- Pan / zoom: supercluster runs in worker; main-thread frame time stays
  under 16 ms during continuous pan (perf assertion in test).
- Clicking a cluster zooms in by one zoom level.
- Clicking a pulse opens a MapLibre Popup with headline + intensity badge
  + affected-companies count + "View details →" button.
- Clicking "View details" navigates to `/events/:eventId/deep-dive`
  (`<ComingSoon plan="PLAN-F-020" />` until Phase 2b).
- Time-mode toggle (Live / Historical / Playback) preserves bbox and
  resets event set per AC-7.
- Playback mode: play / pause / reset / speed controls modify the visible
  event subset over time; controls hidden in Live and Historical modes.

**AC-6 — Stub mode honesty**

- When `GET /api/v1/system/integrations` reports `market_data.mode ===
  "stub"` or `news.mode === "stub"`, `<StubModeBadge>` renders top-left of
  the map canvas listing the affected integration(s).
- Click `<StubModeBadge>` opens a popover with the `reason` from the
  integrations payload and a link to `/admin/system` (admin only; the link
  hides for non-admin users).
- Stub-mode dataset is deterministic — the same events render every reload,
  enabling stable screenshot tests in Phase 3.

**AC-7 — Time-mode integrity**

- Switching to Historical without selecting a date range shows the
  time-mode empty state ("Select a date range to view historical events");
  zero network calls fired.
- Switching to Live cancels in-flight historical fetches and re-opens the
  WS subscription (handled by `useEventFeed` re-mount on key change).
- Switching to Playback with no historical events shows the time-mode
  empty state from `lib/time-mode-empty-state.ts` (Phase 1 Step 13 stub).

**AC-8 — Error handling**

- `GET /api/v1/events` returning 401 triggers exactly one silent refresh
  via `lib/api/client.ts`; success retries once; failure logs out and
  redirects to `/login?reason=session_expired`.
- `GET /api/v1/events` returning 5xx surfaces a toast ("Events service
  unavailable") and renders the map empty with a retry chip; the map
  shell itself does not crash.
- WS connection failure: the map continues to function with REST-seeded
  data; no toast spam — one log entry per backoff window.
- Zod `CONTRACT_MISMATCH` in dev: developer toast with the zod issues;
  prod: generic "Data error" toast.

**AC-9 — Tests**

- All previously `.skip`'d Phase 2 wiring tests (marked in Phase 1
  Step 14) un-skipped and passing under vitest with msw mocking backend
  endpoints per §3.
- New test: `IntelligenceMapPage.test.tsx` covers route mount,
  sidebar-hidden default, navigate on "View details", `<StubModeBadge>`
  conditional render.
- New test: `apiSocket` integration test against a local WS mock proves
  `4401` → refresh → reconnect with fake-timer-driven backoff.
- Coverage ≥ 80 % lines on `events.api.ts`, `events.schema.ts`,
  `useEventFeed.ts`, `useHistoricalEvents.ts`, `lib/api/integrations.ts`.

**AC-10 — Documentation**

- `docs/ARCHITECTURE.md` updated with the events REST + WS contract and
  the `useIntegrations()` shared hook.
- `src/frontend/features/intelligence-map/README.md` documents the
  data-flow diagram (REST seed → WS append → worker cluster → MapLibre
  layers).
- Phase 2b spec opens with the `onExpandEvent` consumer contract handed
  off cleanly from Phase 2a.

---

## 7. Testing strategy

- **Unit (vitest + msw):** every API wrapper (`events.api.ts`,
  `useHistoricalEvents.ts`, `integrations.ts`) is tested in isolation
  with msw against the Phase 2a contract.
- **Hook tests (React Testing Library + msw):** `useEventFeed` REST seed
  + WS merge behaviour; reset-on-key-change; unsubscribe on unmount.
- **Component tests:** `IntelligenceMap.tsx` — renders with mocked
  maplibre-gl + worker; verifies `TimeModeToolbar` and `PlaybackControls`
  switching; pulse-click popup; cluster-click `flyTo`.
- **Integration test:** `IntelligenceMapPage` mounted under a test router
  with mocked `AuthProvider`; verifies route guard interaction and
  navigation on "View details".
- **WS reconnect test:** dedicated to `apiSocket` — fake-timer-driven
  exponential backoff sequence; `4401` close triggers token refresh
  exactly once.
- **Schema-mismatch test:** mocked backend returns malformed `EventPulse`
  → zod throws `ApiError(0, "CONTRACT_MISMATCH", ...)`; UI shows
  developer toast in dev.
- **No screenshot / Lighthouse-CI tests in Phase 2a.** Visual regression
  is Phase 3 polish.

---

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Phase 1 ships a different `AuthContextValue` shape than the Phase 1 spec defines | Medium | Phase 2a's only auth-touching code is `getAccessToken()` (in `lib/api/client.ts`, already done) and `useAuth().state.status` checks in the page wrapper. Drift is a Phase 1 bug, not a Phase 2a redesign. |
| Phase 1 Step 13 ships empty-state stubs with different signatures than the existing tests expect | Medium | Phase 2a Step 12 (test un-skip) updates tests to match whatever Phase 1 actually shipped. If signatures diverge significantly, a backend-style task is filed against Phase 1 Step 13 before un-skipping. |
| MapLibre Popup HTML escapes Tailwind's class scope (popups render in a side-tree) | Medium | Confirmed against MapLibre 4.x: popups attach to the map container, so Tailwind classes resolve via the global stylesheet. Fallback: scoped CSS module for popup styles if classes don't apply. |
| Backend doesn't implement the WS endpoint by Phase 2a ship date | High | AC-4 includes a backend audit step (#13 in migration sequence). Backend tasks are filed as Phase-2a-blocking. Stub-mode backend serves a synthetic event every 30 s so the channel is verifiable without real data. |
| Supercluster worker performance degrades with > 1000 events | Low | Phase 2a caps the backend response at 1000 events (`max_per_request`). Truncation hint prompts the user to zoom or narrow the range. Performance assertion in component test guards regressions. |
| `<StubModeBadge>` popover anchor logic conflicts with MapLibre's own popover system | Low | Badge is a regular React element overlaid on the map container via absolute positioning — not a MapLibre Popup. No conflict. |
| `4401` WS close + concurrent `api()` 401 race could double-refresh | Medium | `lib/api/client.ts` already implements a single in-flight refresh promise (Phase 1 §5.5 / §6.6). `apiSocket` uses `getAccessToken()` after refresh resolves — single source of truth. Integration test asserts no double-refresh. |
| Score overlay accidentally activated by a stray Phase 3 change | Low | Phase 2a does not touch `useScoreOverlay`; it remains dormant. Phase 3 owns activation and the `/ws/scores` endpoint definition. |

---

## 9. Phase 2b preview (not scope)

After Phase 2a ships, Phase 2b covers the remaining five hero screens:

| Route | Feature | Plan |
|---|---|---|
| `/events/:eventId/deep-dive` + side-panel | Progressive Disclosure | PLAN-F-020 |
| `/briefs`, `/briefs/:id` | Briefs Reader | PLAN-F-026 |
| `/qa` | Q&A Chat (SSE) | PLAN-F-027 |
| `/companies/:ticker` | Company Detail + Analyze-Now | PLAN-F-023 |
| `/admin/ai-audit` | AI Audit Console | PLAN-F-029 |

Phase 2b depends on Phase 2a's: `lib/api/integrations.ts`,
`<StubModeBadge>`, the pulse-click → `onExpandEvent` →
`/events/:id/deep-dive` navigation contract, and the events REST + WS
backend contracts defined in §3 (the deep-dive route reuses event data).

---

## 10. End-state demo script

> Visit `http://localhost:5173`. Log in. Land on the Intelligence Map at
> `/`. See ~50 deterministic stub events distributed across the globe,
> rendered as pulses and clusters with the dark-first design system.
> `<StubModeBadge>` sits top-left because `news` is in stub mode. Pan and
> zoom — supercluster keeps the frame rate smooth. Click a pulse; a clean
> MapLibre popup shows headline, intensity, affected-companies count, and
> a "View details →" button. Click it; route to
> `/events/:eventId/deep-dive` and see the `<ComingSoon plan="PLAN-F-020">`
> placeholder — the next phase's handoff is wired. Switch to Historical
> mode, pick a date range; events refetch through the new contract.
> Switch to Playback; the timeline plays forward. Throughout, token
> refresh is silent and the WS reconnects on transient failure. The map
> feels alive and looks finished — that is Phase 2a done.

---

## 11. Open items for follow-up specs

- **Phase 2b spec** — written after Phase 2a ships, scoped to the five
  hero plans above. Reuses Phase 2a's `useIntegrations`, `<StubModeBadge>`,
  and the events backend contracts.
- **Phase 3 spec** — scoring overlay endpoints (`/api/v1/scores/history`,
  `/ws/scores`), sector dropdown UX, Storybook, screenshot CI, server-side
  WS subscription filtering.
- **Backend audit punch list** — produced in Step 13; tracked under Phase
  2a until closed.

---

*End of spec.*
