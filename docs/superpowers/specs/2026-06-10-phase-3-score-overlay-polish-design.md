# Phase 3 — Score Overlay & Polish: Design Spec

**Date:** 2026-06-10
**Author:** brainstorming session (jakub + assistant)
**Status:** Approved for planning
**Branch target:** `phase-3/score-overlay-polish`
**Predecessor:** `docs/superpowers/specs/2026-06-10-phase-2b-hero-screens-design.md`

---

## 0. Why this exists

Phase 1 established the frontend foundations. Phase 2a applied them to the Intelligence
Map. Phase 2b applied them to the remaining five hero screens. All frontend violations are
now resolved and all backend routers are mounted.

Phase 3 activates the features that were deliberately kept dormant through Phases 1–2b:

1. **Score overlay** — `useScoreOverlay` subscribes to `WSS /ws/scores` and renders
   coloured company markers near each event. The hook already exists and already uses
   `apiSocket`, but `profileActive` is hardwired to `false`. Phase 3 creates the
   `/ws/scores` WebSocket endpoint and wires the active profile through the component tree.

2. **Live events feed** — `useEventFeed` already calls `apiSocket('/api/v1/events/feed')`
   but no backend WebSocket handler exists. Phase 3 creates it with server-side bbox/sector
   subscription filtering.

3. **Sector dropdown** — `MapContextSwitcher` has a hardcoded static `SECTORS` array.
   Phase 3 adds `GET /api/v1/screener/sectors` and a `useSectors` hook so the dropdown
   reflects actual data.

4. **Scores history** — `GET /api/v1/scores/history` is wired through validation but
   calls `_stub_get_score_at_time`. Phase 3 adds `get_score_at_time` to
   `ICompanyScoreRepository` and `CompanyScoreRepository`.

5. **Storybook + screenshot CI** — map component stories and a GitHub Actions visual
   regression check.

**Scope rule (unchanged from Phases 1–2b):**
The frontend never mocks backend behaviour. Stub-mode badges are rendered when the
backend declares an integration as `mode: stub`.

---

## 1. Goals and non-goals

### 1.1 Goals

1. `useScoreOverlay` activates when a scoring profile is selected; markers appear on
   the map coloured by geo-adjusted score.
2. `/ws/scores` WebSocket endpoint exists, authenticates via `?token=`, registers
   connections to `geo_modifier_broadcaster`, and deregisters on disconnect.
3. `/api/v1/events/feed` WebSocket endpoint exists; clients can subscribe with optional
   `bbox` and `sector` filters; the broadcaster filters events before push.
4. `GET /api/v1/screener/sectors` returns distinct sectors from the tenant's company
   table; `MapContextSwitcher` fetches it via `useSectors`.
5. `GET /api/v1/scores/history` calls the real `CompanyScoreRepository.get_score_at_time`
   (no stub); `ICompanyScoreRepository` protocol is extended with that method.
6. `ScoringProfileSelector` and `ActiveProfileProvider` are wired into `AppShell` and
   `TopNav`; `ScoringProfileSelector` uses `api<T>()` (no raw `fetch()`), and uses
   Tailwind tokens (no BEM class names / inline styles).
7. Storybook 8 (`@storybook/react-vite`) is installed and configured; stories exist for
   `MapContextSwitcher`, `EventPopup` (PD version), `SidePanel`, and `ScoreOverlay`.
8. A GitHub Actions workflow runs Storybook test-runner on every push/PR.
9. `npm run typecheck && lint && test && build` exit 0; all existing tests pass.

### 1.2 Non-goals (Phase 4 or later)

- Real-time event ingestion pipeline (events from market data sources); events remain
  stubbed at the repository layer.
- `/ws/analysis/{run_id}` WebSocket backend — company detail analyze-now stream.
- Portfolio / Watchlist real implementations.
- Password reset, OAuth2/SSO.
- Chromatic visual diffing (CI uses local Playwright snapshots, not a hosted service).
- Custom scoring indicator builder UI.
- Multi-tenant WebSocket isolation via Redis pub/sub (single-process in-memory registry
  is acceptable for Phase 3 single-instance deployments).

---

## 2. Dependencies on Phases 1, 2a, 2b

Phase 3 does not redefine any prior contract. It consumes:

| Dependency | Provided by | Used by |
|---|---|---|
| `lib/api/client.ts:api()` | Phase 1 | `ScoringProfileSelector`, `useSectors` |
| `lib/api/ws.ts:apiSocket()` | Phase 1 | `useEventFeed` (already), `useScoreOverlay` (already) |
| Tailwind v4 design tokens | Phase 1 | `ScoringProfileSelector` migration |
| `IntelligenceMap.profileActive` prop | Phase 2a | Phase 3 passes real value |
| `ProgressiveDisclosureProvider` wired in router | Phase 2b | `IntelligenceMapPage` extended in Phase 3 |
| `ActiveProfileProvider` / `useActiveProfileContext` | Phase 2b plan (written), not yet implemented | Phase 3 mounts it in `AppShell`; one soft dependency — Phase 3 task that extends `IntelligenceMapPage.tsx` must start from Phase 2b's end state |

The `ScoringProfileSelector.tsx` and `useActiveProfile.ts` files exist already
(written as part of earlier plans) but are not mounted anywhere. Phase 3 wires them in.

**The single file where Phase 2b must be implemented first:**
`IntelligenceMapPage.tsx` — Phase 2b changes it to use `useDisclosure()`. Phase 3
then also reads from `useActiveProfileContext()`. The plan task that touches this file
carries a `prerequisite: Phase 2b complete` note.

---

## 3. Architecture

### 3.1 Score overlay data flow

```
User selects profile in ScoringProfileSelector
  └─► setActiveProfile(profileId) in ActiveProfileProvider (AppShell)
        └─► useActiveProfileContext() in IntelligenceMapPage
              └─► profileActive={!!activeProfileId} to IntelligenceMap
                    └─► useScoreOverlay(profileActive, events)
                          └─► apiSocket('/ws/scores', …)  ←── geo_modifier_broadcaster.broadcast()
                                                                  ▲
                                                               GET /api/v1/scores/history
                                                               (initial load of stored scores)
```

### 3.2 Live events feed data flow

```
IntelligenceMap mounts
  └─► useEventFeed(mode, sector, bbox)
        └─► apiSocket('/api/v1/events/feed?sector=X&bbox=W,S,E,N', …)
              └─► EventsFeedHandler (new, Phase 3)
                    registers subscription { sector, bbox } in EventsBroadcaster
                    on new event: filter by subscription → push or skip
```

### 3.3 Provider nesting in AppShell

```
QueryClientProvider (already wraps AppShell)
  └─► ActiveProfileProvider  ← new, Phase 3
        └─► AppShell children (TopNav includes ScoringProfileSelector)
              └─► Outlet → … → IntelligenceMapPage (reads activeProfileId)
```

---

## 4. Per-subsystem design

### 4.1 Score overlay activation

#### 4.1.1 `AppShell.tsx`

Wrap the shell content with `ActiveProfileProvider` from
`src/frontend/features/scoring/ScoringProfileSelector.tsx`:

```tsx
import { ActiveProfileProvider } from '@/features/scoring/ScoringProfileSelector';

export function AppShell() {
  const { open, setOpen } = useCommandPalette();
  const health = useQuery({ … });

  if (health.isSuccess && !health.data) {
    return <BackendUnreachable onRetry={() => health.refetch()} />;
  }

  return (
    <ActiveProfileProvider>
      <div className="min-h-screen bg-surface-0 text-text">
        <a href="#main" className="sr-only …">Skip to content</a>
        <TopNav onOpenCommand={() => setOpen(true)} />
        <main id="main" className="pb-16 md:pb-0"><Outlet /></main>
        <MobileNav />
        <CommandPalette open={open} onOpenChange={setOpen} />
        <Toaster richColors closeButton position="bottom-right" />
      </div>
    </ActiveProfileProvider>
  );
}
```

#### 4.1.2 `TopNav.tsx`

Add `ScoringProfileSelector` in the right-side controls, between the search button and
`ThemeToggle`:

```tsx
import { ScoringProfileSelector } from '@/features/scoring/ScoringProfileSelector';

// Inside the ml-auto flex div:
<ScoringProfileSelector className="hidden md:flex" />
```

The `className` prop passes Tailwind classes into the component's root element; the
component is hidden on mobile (the map canvas is the full screen on small devices).

#### 4.1.3 `IntelligenceMapPage.tsx` (Phase 2b end state + Phase 3 addition)

```tsx
import { useDisclosure } from '@/features/progressive-disclosure/ProgressiveDisclosureProvider';
import { useActiveProfileContext } from '@/features/scoring/ScoringProfileSelector';

export function IntelligenceMapPage() {
  const { onExpandEvent } = useDisclosure();
  const { activeProfileId } = useActiveProfileContext();
  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap
        onExpandEvent={onExpandEvent}
        profileActive={!!activeProfileId}
      />
    </div>
  );
}
```

#### 4.1.4 `ScoringProfileSelector.tsx` — violation fixes

Three violations to fix:

**1. Raw `fetch()` → `api<T>()`**

```typescript
// Before
async function fetchScoringProfiles(): Promise<ScoringProfile[]> {
  const response = await fetch("/api/v1/scoring-profiles");
  if (!response.ok) { throw new Error(…); }
  const json = await response.json();
  return json.data.profiles as ScoringProfile[];
}

// After
import { api } from '@/lib/api/client';

async function fetchScoringProfiles(): Promise<ScoringProfile[]> {
  const data = await api<{ profiles: ScoringProfile[] }>('/scoring-profiles');
  return data?.profiles ?? [];
}
```

`api<T>()` returns `body.data`, so the path is `/scoring-profiles` (no `/api/v1/`
prefix — `api()` prepends it) and the return type is `{ profiles: ScoringProfile[] }`.

**2. BEM class names → Tailwind tokens**

All `scoring-profile-selector*` class names are replaced with Tailwind utilities.
Key mappings:

| Old BEM class | Tailwind replacement |
|---|---|
| `.scoring-profile-selector` (root) | `flex items-center gap-2` |
| `--loading` / `--error` | `text-muted text-xs` / `text-negative text-xs` |
| `__builtins` group | `flex gap-1` |
| `__pill` (inactive) | `rounded-full border border-border px-2.5 py-0.5 text-xs text-muted hover:text-text` |
| `__pill--active` | `rounded-full bg-signal px-2.5 py-0.5 text-xs font-semibold text-surface-0` |
| `__custom` container | `flex items-center gap-1` |
| `__label` | `text-xs text-muted` |
| `__select` | `rounded border border-border bg-surface-1 px-2 py-0.5 text-xs text-text` |
| `__empty` | `text-xs text-muted` |

**3. `ActiveProfileProvider` export stays as-is** — it is already correct; no change
needed to the context/hook internals.

---

### 4.2 `/ws/scores` backend

**New file:** `src/api/routers/ws_scores_router.py`

```python
"""
api.routers.ws_scores_router — WebSocket endpoint for geo-modifier score broadcasts.

Authenticates via ?token= query parameter (same mechanism as /api/v1/events/feed).
Registers the connection with geo_modifier_broadcaster; deregisters on disconnect.

PLAN-F-018 TASK-004 defined the broadcaster; this route activates it.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.auth_deps import validate_ws_token
from src.api.websocket.geo_modifier_broadcaster import (
    deregister_geo_connection,
    register_geo_connection,
)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/scores")
async def ws_scores(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    """Subscribe to geo-modifier score broadcast for the authenticated tenant."""
    user = await validate_ws_token(token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    register_geo_connection(str(user.tenant_id), websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client sends no frames
    except WebSocketDisconnect:
        pass
    finally:
        deregister_geo_connection(str(user.tenant_id), websocket)
```

**`validate_ws_token`** is a new helper in `src/api/auth_deps.py` that accepts a raw
token string, verifies the JWT, and returns a `CurrentUser`-compatible object or
`None`:

```python
async def validate_ws_token(token: str) -> CurrentUser | None:
    try:
        return await _decode_and_fetch_user(token)
    except Exception:
        return None
```

The implementation delegates to the existing JWT decode logic already used by
`get_current_user`; it just wraps it in a try/except instead of raising `HTTPException`.

**Mount in `main.py`:**

```python
from src.api.routers.ws_scores_router import router as ws_scores_router
app.include_router(ws_scores_router)  # no prefix — route is /ws/scores
```

---

### 4.3 `/api/v1/events/feed` WebSocket backend

**New file:** `src/api/websocket/events_broadcaster.py`

Modelled after `geo_modifier_broadcaster.py`. Stores per-connection subscriptions
(bbox + sector filter) alongside the WebSocket reference.

```python
"""
api.websocket.events_broadcaster — WebSocket connection registry and fan-out for
the live events feed.

Each connection carries an optional SubscriptionFilter (bbox + sector).
broadcast_event() filters before pushing to keep clients from receiving noise.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionFilter:
    sector: str | None = None
    bbox: tuple[float, float, float, float] | None = None  # west, south, east, north


@dataclass
class _Subscriber:
    websocket: Any
    filter: SubscriptionFilter = field(default_factory=SubscriptionFilter)


_subscribers: dict[str, list[_Subscriber]] = {}  # tenant_id → list


def register_events_connection(
    tenant_id: str, websocket: Any, filter: SubscriptionFilter | None = None
) -> None:
    sub = _Subscriber(websocket=websocket, filter=filter or SubscriptionFilter())
    _subscribers.setdefault(tenant_id, []).append(sub)


def deregister_events_connection(tenant_id: str, websocket: Any) -> None:
    subs = _subscribers.get(tenant_id, [])
    _subscribers[tenant_id] = [s for s in subs if s.websocket is not websocket]


def update_subscription_filter(
    tenant_id: str, websocket: Any, filter: SubscriptionFilter
) -> None:
    for sub in _subscribers.get(tenant_id, []):
        if sub.websocket is websocket:
            sub.filter = filter
            return


async def broadcast_event(payload: dict, tenant_id: str) -> None:
    subs = list(_subscribers.get(tenant_id, []))
    if not subs:
        return

    dead: list[Any] = []

    async def _send(sub: _Subscriber) -> None:
        if not _matches(payload, sub.filter):
            return
        try:
            await sub.websocket.send_json({"type": "event", "payload": payload})
        except Exception:
            dead.append(sub.websocket)

    await asyncio.gather(*(_send(s) for s in subs), return_exceptions=True)
    for ws in dead:
        deregister_events_connection(tenant_id, ws)


def _matches(event: dict, f: SubscriptionFilter) -> bool:
    if f.sector is not None:
        companies = event.get("affected_companies", [])
        if not any(c.get("sector") == f.sector for c in companies):
            return False
    if f.bbox is not None:
        west, south, east, north = f.bbox
        lat = event.get("lat", 0)
        lon = event.get("lon", 0)
        if not (south <= lat <= north and west <= lon <= east):
            return False
    return True
```

**New file:** `src/api/routers/ws_events_router.py`

```python
"""
api.routers.ws_events_router — WebSocket endpoint for the live events feed.

Path: /api/v1/events/feed
Auth: ?token= query parameter.
Subscribe frame: {"type": "subscribe", "sector": "Technology", "bbox": "W,S,E,N"}
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.auth_deps import validate_ws_token
from src.api.websocket.events_broadcaster import (
    SubscriptionFilter,
    deregister_events_connection,
    register_events_connection,
    update_subscription_filter,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/events", tags=["websocket"])


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        return None


@router.websocket("/feed")
async def ws_events_feed(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    sector: str | None = Query(default=None),
    bbox: str | None = Query(default=None, description="west,south,east,north"),
) -> None:
    """Live event feed WebSocket. Optional sector and bbox filters on connect."""
    user = await validate_ws_token(token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    initial_filter = SubscriptionFilter(
        sector=sector, bbox=_parse_bbox(bbox)
    )
    register_events_connection(str(user.tenant_id), websocket, initial_filter)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "subscribe":
                new_filter = SubscriptionFilter(
                    sector=msg.get("sector"),
                    bbox=_parse_bbox(msg.get("bbox")),
                )
                update_subscription_filter(
                    str(user.tenant_id), websocket, new_filter
                )
    except WebSocketDisconnect:
        pass
    finally:
        deregister_events_connection(str(user.tenant_id), websocket)
```

**Mount in `main.py`:**

```python
from src.api.routers.ws_events_router import router as ws_events_router
app.include_router(ws_events_router)  # prefix already in the router
```

**Frontend — `useEventFeed.ts` subscribe frame**

`useEventFeed` already calls `apiSocket('/api/v1/events/feed', …)`. When `mode` or
`sector` changes, it closes and re-opens the socket (existing behaviour from Phase 2a).
The query-string filter on connect handles the initial subscription. No frontend change
is needed for basic operation.

Future: if sub-second filter changes without reconnect are desired, the frontend can
send a `{"type": "subscribe", …}` frame instead of reconnecting — the backend handles
it. That optimisation is not required for Phase 3.

---

### 4.4 `GET /api/v1/scores/history` real implementation

**Files to change:**

| File | Change |
|---|---|
| `src/scoring/repositories/interfaces.py` | Add `get_score_at_time` to `ICompanyScoreRepository` |
| `src/scoring/repositories/company_score_repo.py` | Implement `get_score_at_time` |
| `src/api/v1/scoring/scores.py` | Replace `_stub_get_score_at_time` call with DI-injected repo |

**Interface addition:**

```python
async def get_score_at_time(
    self,
    company_ids: list[UUID],
    at_time: datetime,
    tenant_id: UUID,
) -> list[CompanyScoreRecord]: ...
```

**Repository implementation** (SQLAlchemy async):

```python
async def get_score_at_time(
    self,
    company_ids: list[UUID],
    at_time: datetime,
    tenant_id: UUID,
) -> list[CompanyScoreRecord]:
    stmt = (
        select(_CompanyScoreRow)
        .where(
            _CompanyScoreRow.company_id.in_(company_ids),
            _CompanyScoreRow.computed_at <= at_time,
        )
        .distinct(_CompanyScoreRow.company_id, _CompanyScoreRow.indicator_id)
        .order_by(
            _CompanyScoreRow.company_id,
            _CompanyScoreRow.indicator_id,
            _CompanyScoreRow.computed_at.desc(),
        )
    )
    result = await self._session.execute(stmt)
    return [_row_to_record(row) for row in result.scalars()]
```

**Endpoint wiring** — inject `ICompanyScoreRepository` via FastAPI `Depends`:

```python
@router.get("/history", response_model=dict)
async def get_scores_at_time(
    user: AuthUser,
    repo: Annotated[ICompanyScoreRepository, Depends(get_company_score_repo)],
    …  # existing params unchanged
) -> dict:
    …
    scores = await repo.get_score_at_time(parsed_ids, at_time, user.tenant_id)
    return {"data": [s.model_dump(mode="json") for s in scores], "meta": {}, "error": None}
```

`get_company_score_repo` is a new FastAPI dependency that constructs
`CompanyScoreRepository(session)` from the async session dependency (same pattern as
other repository injections in the codebase).

---

### 4.5 Sectors endpoint + `useSectors` hook

#### 4.5.1 Backend: `GET /api/v1/screener/sectors`

Add to `src/api/v1/screener/router.py`:

```python
@router.get("/sectors", response_model=dict)
async def get_sectors(user: AuthUser, session: AsyncSession = Depends(get_async_session)) -> dict:
    """Return distinct sector values for the tenant's companies, sorted A-Z."""
    result = await session.execute(
        select(Company.sector)
        .where(Company.tenant_id == user.tenant_id, Company.sector.isnot(None))
        .distinct()
        .order_by(Company.sector)
    )
    sectors = [row[0] for row in result.all()]
    return {"data": {"sectors": sectors}, "meta": {}, "error": None}
```

#### 4.5.2 Frontend: `useSectors` hook

**New file:** `src/frontend/features/intelligence-map/hooks/useSectors.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api/client';

async function fetchSectors(): Promise<string[]> {
  const data = await api<{ sectors: string[] }>('/screener/sectors');
  return data?.sectors ?? [];
}

export function useSectors(): string[] {
  const { data = [] } = useQuery({
    queryKey: ['sectors'],
    queryFn: fetchSectors,
    staleTime: 10 * 60 * 1000, // 10 minutes — sector list changes rarely
  });
  return data;
}
```

#### 4.5.3 `MapContextSwitcher.tsx` — consume `useSectors`

Remove the hardcoded `SECTORS` constant. Accept `sectors` as a prop (so the component
stays pure and testable):

```tsx
export interface MapContextSwitcherProps {
  mode: MapMode;
  sector: string | null;
  sectors: string[];          // ← new, replaces hardcoded constant
  onSetMode: (mode: MapMode) => void;
  onSetSector?: (sector: string) => void;
}
```

`IntelligenceMap.tsx` already passes props to `MapContextSwitcher`. Add:

```tsx
// In IntelligenceMap.tsx
const sectors = useSectors();
// …
<MapContextSwitcher mode={mode} sector={sector} sectors={sectors} onSetMode={setMode} onSetSector={setSector} />
```

---

### 4.6 Storybook

**Install and configure Storybook 8 with the Vite builder:**

```bash
npx storybook@latest init --type react --builder vite --skip-install
npm install --save-dev @storybook/react-vite @storybook/react @storybook/addon-essentials
```

This adds `.storybook/main.ts` and `.storybook/preview.ts` (auto-generated). The
preview must import the global CSS:

```typescript
// .storybook/preview.ts
import '../src/frontend/styles/globals.css';
import '../src/frontend/styles/tokens.css';
```

**`package.json` scripts to add:**

```json
"storybook": "storybook dev -p 6006",
"build-storybook": "storybook build"
```

**Stories to create:**

| Story file | Component | Key variants |
|---|---|---|
| `MapContextSwitcher.stories.tsx` | `MapContextSwitcher` | global, portfolio, sector selected |
| `EventPopup.stories.tsx` | `EventPopup` (PD version) | loading, loaded, error |
| `SidePanel.stories.tsx` | `SidePanel` | closed, open |
| `ScoreOverlay.stories.tsx` | `ScoreOverlay` | no markers, 3 markers (low/mid/high score) |

Stories use `fn()` from `@storybook/test` for callbacks. Components that fetch data
via hooks (e.g., `usePopupData`) show their loading state in stories — no live backend
needed; the goal is layout and token verification, not data content.

All stories receive a `QueryClientProvider` decorator so TanStack Query hooks don't
crash:

```typescript
// shared decorator in .storybook/preview.ts
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

export const decorators = [
  (Story) => (
    <QueryClientProvider client={queryClient}>
      <Story />
    </QueryClientProvider>
  ),
];
```

Components that fetch data via hooks will show loading state in stories (no live
backend). This is acceptable — the visual goal is layout/token verification.

---

### 4.7 Screenshot CI

**New file:** `.github/workflows/visual.yml`

```yaml
name: Visual Regression

on:
  push:
    branches: [main]
  pull_request:

jobs:
  storybook-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - run: npm ci
      - run: npm run build-storybook -- --quiet
      - uses: playwright/action@v1
        with:
          version: v1.44.0
      - run: |
          npx concurrently -k -s first -n "SB,TEST" -c "magenta,blue" \
            "npx http-server storybook-static --port 6006 --silent" \
            "npx wait-on tcp:6006 && npm run test-storybook"
```

**`package.json` script to add:**

```json
"test-storybook": "test-storybook --url http://localhost:6006"
```

Install `@storybook/test-runner` and `concurrently`:

```bash
npm install --save-dev @storybook/test-runner concurrently http-server
```

The test-runner uses Playwright under the hood; it renders each story in a headless
browser and asserts no uncaught errors. Visual snapshot comparisons are not enabled by
default — the goal is a no-crash baseline that catches regressions in token usage.

---

## 5. File map

| File | Action | Phase 3 task |
|---|---|---|
| `src/api/main.py` | Add 2 router mounts (`ws_scores`, `ws_events`) | §4.2 / §4.3 |
| `src/api/auth_deps.py` | Add `validate_ws_token` | §4.2 |
| `src/api/routers/ws_scores_router.py` | Create | §4.2 |
| `src/api/routers/ws_events_router.py` | Create | §4.3 |
| `src/api/websocket/events_broadcaster.py` | Create | §4.3 |
| `src/scoring/repositories/interfaces.py` | Add `get_score_at_time` | §4.4 |
| `src/scoring/repositories/company_score_repo.py` | Implement `get_score_at_time` | §4.4 |
| `src/api/v1/scoring/scores.py` | Wire real repo via DI | §4.4 |
| `src/api/v1/screener/router.py` | Add `/sectors` endpoint | §4.5 |
| `src/frontend/features/intelligence-map/hooks/useSectors.ts` | Create | §4.5 |
| `src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx` | Add `sectors` prop, remove hardcoded array | §4.5 |
| `src/frontend/features/intelligence-map/IntelligenceMap.tsx` | Pass `sectors` to `MapContextSwitcher` | §4.5 |
| `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx` | Add `useActiveProfileContext`, pass `profileActive` | §4.1 |
| `src/frontend/features/scoring/ScoringProfileSelector.tsx` | Fix raw fetch, migrate BEM → Tailwind | §4.1 |
| `src/frontend/layout/AppShell.tsx` | Wrap with `ActiveProfileProvider` | §4.1 |
| `src/frontend/layout/TopNav.tsx` | Add `ScoringProfileSelector` | §4.1 |
| `.storybook/main.ts` | Create (Storybook config) | §4.6 |
| `.storybook/preview.ts` | Create (global CSS + decorators) | §4.6 |
| `src/frontend/features/intelligence-map/components/MapContextSwitcher.stories.tsx` | Create | §4.6 |
| `src/frontend/features/progressive-disclosure/components/EventPopup.stories.tsx` | Create | §4.6 |
| `src/frontend/features/progressive-disclosure/components/SidePanel.stories.tsx` | Create | §4.6 |
| `src/frontend/features/intelligence-map/components/ScoreOverlay.stories.tsx` | Create | §4.6 |
| `.github/workflows/visual.yml` | Create | §4.7 |
| `package.json` | Add storybook/build-storybook/test-storybook scripts | §4.6 / §4.7 |

---

## 6. Error handling

| Scenario | Behaviour |
|---|---|
| `/ws/scores` receives invalid token | Close with code 4401 before accepting |
| `/ws/scores` client disconnects | `WebSocketDisconnect` caught; connection deregistered in `finally` |
| `/api/v1/events/feed` receives malformed subscribe frame | `json.JSONDecodeError` caught; connection stays open; frame ignored |
| `GET /api/v1/scores/history` DB error | FastAPI 500 (no special handling; infra concern) |
| `GET /api/v1/screener/sectors` no companies | Returns `{"data": {"sectors": []}, …}` |
| `useSectors` query fails | `data` defaults to `[]`; `MapContextSwitcher` shows "Select sector" prompt with no options |
| `fetchScoringProfiles` fails | TanStack Query `error` branch renders "Failed to load profiles" (existing error UI, just migrated to Tailwind) |

---

## 7. Testing strategy

### 7.1 Backend

| Test | What to assert |
|---|---|
| `test_ws_scores_auth` | Invalid token → 4401; valid token → connection accepted |
| `test_ws_scores_broadcast` | `broadcast_geo_modifier()` reaches the registered WebSocket |
| `test_ws_events_auth` | Invalid token → 4401; valid token → accepted |
| `test_ws_events_filter_sector` | Event with wrong sector is NOT forwarded; matching sector IS |
| `test_ws_events_filter_bbox` | Event outside bbox is NOT forwarded |
| `test_ws_events_subscribe_frame` | Subscribe frame updates filter; subsequent broadcast respects new filter |
| `test_get_scores_at_time_repo` | `get_score_at_time` returns correct snapshot; future snapshots excluded |
| `test_get_sectors` | Returns sorted distinct sectors from company table |

### 7.2 Frontend

| Test | What to assert |
|---|---|
| `useSectors.test.ts` | `api` called with `/screener/sectors`; returns sorted list |
| `MapContextSwitcher.test.tsx` | Renders props-supplied sectors; no hardcoded SECTORS |
| `ScoringProfileSelector.test.tsx` | `api` called (not raw `fetch`); pill classes use Tailwind tokens |
| `IntelligenceMapPage.test.tsx` | `profileActive=true` when `activeProfileId` is set |
| `AppShell.test.tsx` | `ActiveProfileProvider` is in the tree |

### 7.3 Storybook

`npm run test-storybook` passes (no uncaught errors in any story).

---

## 8. Open items for follow-up specs

- `/ws/analysis/{run_id}` backend WebSocket — company detail analyze-now stream.
- Redis pub/sub for multi-process WebSocket scaling.
- Real event ingestion pipeline (events from market-data sources, not stubs).
- Custom indicator builder UI.
- Portfolio / Watchlist real implementations.

---

*End of spec.*
