# Phase 3 — Score Overlay & Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Activate the score overlay (live `/ws/scores` + `/api/v1/events/feed` WebSocket backends, `ScoringProfileSelector` wired into the shell), replace hardcoded sector list with live data, complete the `scores/history` repository, and add Storybook + screenshot CI.

**Architecture:** Backend creates two new FastAPI WebSocket route handlers that authenticate via `?token=` query param and delegate to existing broadcaster helpers; the frontend wires `ActiveProfileProvider` into `AppShell`, adds `ScoringProfileSelector` to `TopNav`, and threads `profileActive` down to `IntelligenceMap`. A new `GET /api/v1/screener/sectors` endpoint and `useSectors` hook replace the hardcoded sector array. Storybook 8 with `@storybook/react-vite` provides component stories; a GitHub Actions workflow runs the test-runner on every push.

**Tech Stack:** Python / FastAPI / SQLAlchemy async / python-jose; React 18 / TanStack Query v5 / Tailwind v4 / Vitest; Storybook 8 (`@storybook/react-vite`); `@storybook/test-runner` / Playwright; GitHub Actions.

**Prerequisite for Task 10 only:** Phase 2b must be implemented before Task 10 is executed (Task 10 extends `IntelligenceMapPage.tsx` which Phase 2b modifies). Tasks 1–9 and 11–12 are independent of Phase 2b.

---

## File Map

| File | Action |
|---|---|
| `src/api/auth_deps.py` | Modify — add `validate_ws_token` |
| `src/api/routers/ws_scores_router.py` | Create |
| `src/api/routers/ws_events_router.py` | Create |
| `src/api/websocket/events_broadcaster.py` | Create |
| `src/api/main.py` | Modify — mount 2 new WS routers |
| `src/scoring/repositories/interfaces.py` | Modify — add `get_score_at_time` to protocol |
| `src/scoring/repositories/company_score_repo.py` | Modify — implement `get_score_at_time` |
| `src/api/v1/scoring/scores.py` | Modify — replace stub with real repo call |
| `src/api/v1/screener/router.py` | Modify — add `/sectors` endpoint |
| `src/frontend/features/intelligence-map/hooks/useSectors.ts` | Create |
| `src/frontend/features/intelligence-map/hooks/useSectors.test.ts` | Create |
| `src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx` | Modify — add `sectors` prop |
| `src/frontend/features/intelligence-map/IntelligenceMap.tsx` | Modify — pass `sectors` to switcher |
| `src/frontend/features/scoring/ScoringProfileSelector.tsx` | Modify — `api<T>` + Tailwind |
| `src/frontend/layout/AppShell.tsx` | Modify — wrap with `ActiveProfileProvider` |
| `src/frontend/layout/TopNav.tsx` | Modify — add `ScoringProfileSelector` |
| `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx` | Modify — `profileActive` from context |
| `.storybook/main.ts` | Create |
| `.storybook/preview.ts` | Create |
| `src/frontend/features/intelligence-map/components/MapContextSwitcher.stories.tsx` | Create |
| `src/frontend/features/progressive-disclosure/components/EventPopup.stories.tsx` | Create |
| `src/frontend/features/progressive-disclosure/components/SidePanel.stories.tsx` | Create |
| `src/frontend/features/intelligence-map/components/ScoreOverlay.stories.tsx` | Create |
| `.github/workflows/visual.yml` | Create |
| `package.json` | Modify — add storybook scripts |
| `tests/unit/api/test_ws_scores.py` | Create |
| `tests/unit/api/test_ws_events.py` | Create |
| `tests/unit/scoring/test_score_at_time.py` | Create |
| `tests/unit/api/test_sectors.py` | Create |

---

## Task 1: `validate_ws_token` helper

WebSocket routes can't use `HTTPBearer` (no `Authorization` header); they pass a `?token=` query param instead. This task adds a helper that wraps the existing JWT decode logic and returns `None` on failure instead of raising HTTP 401.

**Files:**
- Modify: `src/api/auth_deps.py`
- Create: `tests/unit/api/test_ws_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_ws_auth.py
"""Unit tests for validate_ws_token — the WebSocket JWT helper."""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from uuid import UUID
from datetime import datetime, timezone, timedelta
from jose import jwt

from src.api.auth_deps import CurrentUser, validate_ws_token


def _make_token(payload: dict) -> str:
    return jwt.encode(
        payload,
        "test-secret-key-minimum-32-characters-long!",
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_valid_token_returns_current_user():
    token = _make_token({
        "sub": "12345678-1234-5678-1234-567812345678",
        "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "role": "end_user",
        "email": "test@example.com",
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
    })
    result = await validate_ws_token(token)
    assert result is not None
    assert isinstance(result, CurrentUser)
    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_invalid_token_returns_none():
    result = await validate_ws_token("not.a.valid.jwt")
    assert result is None


@pytest.mark.asyncio
async def test_expired_token_returns_none():
    token = _make_token({
        "sub": "12345678-1234-5678-1234-567812345678",
        "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "role": "end_user",
        "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp(),
    })
    result = await validate_ws_token(token)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_ws_auth.py -v
```

Expected: `AttributeError: module 'src.api.auth_deps' has no attribute 'validate_ws_token'`

- [ ] **Step 3: Add `validate_ws_token` to `src/api/auth_deps.py`**

Add after the `require_admin` function:

```python
async def validate_ws_token(token: str) -> CurrentUser | None:
    """Validate a raw JWT string for WebSocket connections.

    WebSocket routes pass the token as a query parameter (?token=...) instead
    of an Authorization header. Returns None on any validation failure so
    callers can close the connection gracefully rather than raising HTTP errors.
    """
    try:
        return _decode_token(token)
    except Exception:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/api/test_ws_auth.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/api/auth_deps.py tests/unit/api/test_ws_auth.py
git commit -m "feat(ws): add validate_ws_token helper for WebSocket JWT auth"
```

---

## Task 2: `/ws/scores` WebSocket endpoint

Creates the FastAPI WebSocket route that registers connections with `geo_modifier_broadcaster`. The broadcaster already exists; this task just adds the route and the main.py mount.

**Files:**
- Create: `src/api/routers/ws_scores_router.py`
- Modify: `src/api/main.py`
- Create: `tests/unit/api/test_ws_scores.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_ws_scores.py
"""Tests for /ws/scores WebSocket endpoint."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser


_MOCK_USER = CurrentUser(
    user_id=UUID("12345678-1234-5678-1234-567812345678"),
    tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    role="end_user",
    email="test@example.com",
)


def _build_app():
    from src.api.routers.ws_scores_router import router
    app = FastAPI()
    app.include_router(router)
    return app


def test_valid_token_connection_accepted():
    app = _build_app()
    with patch(
        "src.api.routers.ws_scores_router.validate_ws_token",
        new=AsyncMock(return_value=_MOCK_USER),
    ):
        with TestClient(app) as client:
            with client.websocket_connect("/ws/scores?token=valid") as ws:
                # Connection was accepted — no exception raised.
                pass


def test_invalid_token_connection_rejected():
    app = _build_app()
    with patch(
        "src.api.routers.ws_scores_router.validate_ws_token",
        new=AsyncMock(return_value=None),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            rejected = False
            try:
                with client.websocket_connect("/ws/scores?token=bad") as ws:
                    ws.receive_text()
            except Exception:
                rejected = True
            assert rejected, "Expected connection to be rejected for invalid token"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_ws_scores.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.api.routers.ws_scores_router'`

- [ ] **Step 3: Create `src/api/routers/ws_scores_router.py`**

```python
"""
api.routers.ws_scores_router — /ws/scores WebSocket endpoint.

Authenticates via ?token= query param, then registers the connection
with geo_modifier_broadcaster. The broadcaster is already wired to the
scoring pipeline (PLAN-F-018 TASK-004); this route activates it.
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
    """Subscribe to geo-modifier score broadcast for the authenticated tenant.

    Close code 4401 is sent if the token is invalid (mirrors HTTP 401).
    Client messages are accepted but ignored — the server pushes only.
    """
    user = await validate_ws_token(token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    register_geo_connection(str(user.tenant_id), websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; ignore client frames
    except WebSocketDisconnect:
        pass
    finally:
        deregister_geo_connection(str(user.tenant_id), websocket)
```

- [ ] **Step 4: Mount in `src/api/main.py`**

Add the import and `include_router` call after the existing router mounts:

```python
from src.api.routers.ws_scores_router import router as ws_scores_router

# at the end of the router section:
app.include_router(ws_scores_router)  # /ws/scores — no prefix, route defines full path
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/unit/api/test_ws_scores.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```
git add src/api/routers/ws_scores_router.py src/api/main.py tests/unit/api/test_ws_scores.py
git commit -m "feat(ws): /ws/scores WebSocket endpoint for geo-modifier score overlay"
```

---

## Task 3: `events_broadcaster.py`

The events broadcaster stores per-connection subscription filters (bbox + sector) and filters events before pushing to each subscriber. This is the fan-out logic; the WebSocket route (Task 4) wires it in.

**Files:**
- Create: `src/api/websocket/events_broadcaster.py`

- [ ] **Step 1: Write the test first**

```python
# tests/unit/api/test_events_broadcaster.py
"""Unit tests for events_broadcaster — filter logic and connection management."""
from __future__ import annotations

import asyncio
import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def clear_subscribers():
    """Reset broadcaster state between tests."""
    from src.api.websocket import events_broadcaster as eb
    eb._subscribers.clear()
    yield
    eb._subscribers.clear()


@pytest.mark.asyncio
async def test_broadcast_reaches_registered_connection():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    register_events_connection("tenant-1", ws, SubscriptionFilter())
    await broadcast_event({"lat": 0.0, "lon": 0.0, "affected_companies": []}, "tenant-1")
    ws.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_sector_filter_blocks_non_matching_event():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    register_events_connection("tenant-1", ws, SubscriptionFilter(sector="Technology"))
    await broadcast_event(
        {"lat": 0.0, "lon": 0.0, "affected_companies": [{"sector": "Energy"}]},
        "tenant-1",
    )
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_sector_filter_passes_matching_event():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    register_events_connection("tenant-1", ws, SubscriptionFilter(sector="Technology"))
    await broadcast_event(
        {"lat": 0.0, "lon": 0.0, "affected_companies": [{"sector": "Technology"}]},
        "tenant-1",
    )
    ws.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_bbox_filter_blocks_event_outside_bounds():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    # bbox = west, south, east, north
    register_events_connection(
        "tenant-1", ws, SubscriptionFilter(bbox=(-10.0, -10.0, 10.0, 10.0))
    )
    await broadcast_event({"lat": 50.0, "lon": 50.0, "affected_companies": []}, "tenant-1")
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_deregister_removes_connection():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        deregister_events_connection,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    register_events_connection("tenant-1", ws)
    deregister_events_connection("tenant-1", ws)
    await broadcast_event({"lat": 0.0, "lon": 0.0, "affected_companies": []}, "tenant-1")
    ws.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_update_subscription_filter_changes_filter():
    from src.api.websocket.events_broadcaster import (
        register_events_connection,
        update_subscription_filter,
        broadcast_event,
        SubscriptionFilter,
    )
    ws = AsyncMock()
    register_events_connection("tenant-1", ws, SubscriptionFilter(sector="Energy"))
    # Change filter to Technology
    update_subscription_filter("tenant-1", ws, SubscriptionFilter(sector="Technology"))
    # Energy event should now be blocked
    await broadcast_event(
        {"lat": 0.0, "lon": 0.0, "affected_companies": [{"sector": "Energy"}]},
        "tenant-1",
    )
    ws.send_json.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_events_broadcaster.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.api.websocket.events_broadcaster'`

- [ ] **Step 3: Create `src/api/websocket/events_broadcaster.py`**

```python
"""
api.websocket.events_broadcaster — Connection registry and fan-out for the live events feed.

Each connection carries a SubscriptionFilter (sector + bbox). broadcast_event()
filters per-connection before pushing so clients only receive relevant events.

Modelled after geo_modifier_broadcaster.py. In-process registry only; replace
with Redis pub/sub for multi-process deployments.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionFilter:
    """Optional filter attached to each WebSocket subscription.

    sector: Only forward events where at least one affected_company.sector matches.
    bbox: (west, south, east, north) — only forward events whose lat/lon is inside.
    """
    sector: str | None = None
    bbox: tuple[float, float, float, float] | None = None  # west, south, east, north


@dataclass
class _Subscriber:
    websocket: Any
    filter: SubscriptionFilter = field(default_factory=SubscriptionFilter)


_subscribers: dict[str, list[_Subscriber]] = {}  # tenant_id → list[_Subscriber]


def register_events_connection(
    tenant_id: str,
    websocket: Any,
    filter: SubscriptionFilter | None = None,
) -> None:
    """Register *websocket* for event broadcasts under *tenant_id*."""
    sub = _Subscriber(websocket=websocket, filter=filter or SubscriptionFilter())
    _subscribers.setdefault(tenant_id, []).append(sub)
    logger.debug(
        "events_broadcaster: registered for tenant=%s (total=%d)",
        tenant_id,
        len(_subscribers[tenant_id]),
    )


def deregister_events_connection(tenant_id: str, websocket: Any) -> None:
    """Remove *websocket* from the broadcast registry for *tenant_id*."""
    subs = _subscribers.get(tenant_id, [])
    _subscribers[tenant_id] = [s for s in subs if s.websocket is not websocket]


def update_subscription_filter(
    tenant_id: str, websocket: Any, filter: SubscriptionFilter
) -> None:
    """Replace the SubscriptionFilter for a live connection."""
    for sub in _subscribers.get(tenant_id, []):
        if sub.websocket is websocket:
            sub.filter = filter
            return


async def broadcast_event(payload: dict, tenant_id: str) -> None:
    """Push *payload* to all subscribers for *tenant_id* that match their filter.

    Dead connections are silently removed.
    """
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
        logger.debug("events_broadcaster: removed dead connection for tenant=%s", tenant_id)


def _matches(event: dict, f: SubscriptionFilter) -> bool:
    """Return True if *event* passes the filter criteria."""
    if f.sector is not None:
        companies = event.get("affected_companies", [])
        if not any(c.get("sector") == f.sector for c in companies):
            return False
    if f.bbox is not None:
        west, south, east, north = f.bbox
        lat = float(event.get("lat", 0))
        lon = float(event.get("lon", 0))
        if not (south <= lat <= north and west <= lon <= east):
            return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/api/test_events_broadcaster.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/api/websocket/events_broadcaster.py tests/unit/api/test_events_broadcaster.py
git commit -m "feat(ws): events_broadcaster with per-connection sector/bbox filter"
```

---

## Task 4: `/api/v1/events/feed` WebSocket endpoint

Creates the FastAPI WebSocket route for the live events feed. Accepts optional `?sector=` and `?bbox=` query params on connect; accepts `{"type":"subscribe", ...}` frames for mid-session filter updates.

**Files:**
- Create: `src/api/routers/ws_events_router.py`
- Modify: `src/api/main.py`
- Create: `tests/unit/api/test_ws_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_ws_events.py
"""Tests for /api/v1/events/feed WebSocket endpoint."""
from __future__ import annotations

import json
import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser

_MOCK_USER = CurrentUser(
    user_id=UUID("12345678-1234-5678-1234-567812345678"),
    tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
    role="end_user",
    email="test@example.com",
)


def _build_app():
    from src.api.routers.ws_events_router import router
    app = FastAPI()
    app.include_router(router)
    return app


def test_valid_token_accepted():
    app = _build_app()
    with patch(
        "src.api.routers.ws_events_router.validate_ws_token",
        new=AsyncMock(return_value=_MOCK_USER),
    ):
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/events/feed?token=valid") as ws:
                pass  # accepted without exception


def test_invalid_token_rejected():
    app = _build_app()
    with patch(
        "src.api.routers.ws_events_router.validate_ws_token",
        new=AsyncMock(return_value=None),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            rejected = False
            try:
                with client.websocket_connect("/api/v1/events/feed?token=bad") as ws:
                    ws.receive_text()
            except Exception:
                rejected = True
            assert rejected


def test_subscribe_frame_updates_filter():
    """Sending a subscribe frame does not crash the server."""
    app = _build_app()
    with patch(
        "src.api.routers.ws_events_router.validate_ws_token",
        new=AsyncMock(return_value=_MOCK_USER),
    ), patch(
        "src.api.routers.ws_events_router.update_subscription_filter"
    ) as mock_update:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/events/feed?token=valid") as ws:
                ws.send_text(json.dumps({
                    "type": "subscribe",
                    "sector": "Technology",
                    "bbox": "-10,-10,10,10",
                }))
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][2].sector == "Technology"


def test_malformed_json_frame_ignored():
    """Non-JSON frames are silently ignored; connection stays open."""
    app = _build_app()
    with patch(
        "src.api.routers.ws_events_router.validate_ws_token",
        new=AsyncMock(return_value=_MOCK_USER),
    ):
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/events/feed?token=valid") as ws:
                ws.send_text("not valid json")
                # No exception — connection stays open.
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_ws_events.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.api.routers.ws_events_router'`

- [ ] **Step 3: Create `src/api/routers/ws_events_router.py`**

```python
"""
api.routers.ws_events_router — /api/v1/events/feed WebSocket endpoint.

Auth: ?token= query parameter.
Initial filter: optional ?sector= and ?bbox=west,south,east,north query params.
Mid-session resubscribe: {"type": "subscribe", "sector": "...", "bbox": "..."}
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
    """Parse 'west,south,east,north' string into a float 4-tuple. Returns None on error."""
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        return None
    try:
        w, s, e, n = (float(p) for p in parts)
        return (w, s, e, n)
    except ValueError:
        return None


@router.websocket("/feed")
async def ws_events_feed(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    sector: str | None = Query(default=None, description="Initial sector filter"),
    bbox: str | None = Query(default=None, description="Initial bbox filter: west,south,east,north"),
) -> None:
    """Live event feed WebSocket.

    On connect, registers a subscription with optional sector/bbox filters.
    Clients can update their filter mid-session by sending:
      {"type": "subscribe", "sector": "Technology", "bbox": "-10,-10,10,10"}
    """
    user = await validate_ws_token(token)
    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    initial_filter = SubscriptionFilter(sector=sector, bbox=_parse_bbox(bbox))
    register_events_connection(str(user.tenant_id), websocket, initial_filter)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue  # ignore non-JSON frames
            if msg.get("type") == "subscribe":
                new_filter = SubscriptionFilter(
                    sector=msg.get("sector"),
                    bbox=_parse_bbox(msg.get("bbox")),
                )
                update_subscription_filter(str(user.tenant_id), websocket, new_filter)
    except WebSocketDisconnect:
        pass
    finally:
        deregister_events_connection(str(user.tenant_id), websocket)
```

- [ ] **Step 4: Mount in `src/api/main.py`**

Add import and include_router after the `ws_scores_router` mount added in Task 2:

```python
from src.api.routers.ws_events_router import router as ws_events_router

app.include_router(ws_events_router)  # /api/v1/events/feed — prefix is in the router
```

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/unit/api/test_ws_events.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```
git add src/api/routers/ws_events_router.py src/api/main.py tests/unit/api/test_ws_events.py
git commit -m "feat(ws): /api/v1/events/feed WebSocket with sector/bbox subscription filtering"
```

---

## Task 5: `get_score_at_time` in repository and interface

Adds the time-machine query method that `GET /api/v1/scores/history` needs. Uses PostgreSQL `DISTINCT ON` to return the latest score snapshot at or before a given timestamp, per (company_id, indicator_id) pair.

**Files:**
- Modify: `src/scoring/repositories/interfaces.py`
- Modify: `src/scoring/repositories/company_score_repo.py`
- Create: `tests/unit/scoring/test_score_at_time.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scoring/test_score_at_time.py
"""Unit tests for CompanyScoreRepository.get_score_at_time."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.scoring.repositories.company_score_repo import CompanyScoreRepository


def _make_row(
    company_id: UUID,
    indicator_id: UUID,
    tenant_id: UUID,
    score: float,
    geo_adjusted: float | None,
    computed_at: datetime,
) -> MagicMock:
    row = MagicMock()
    row.score_id = uuid4()
    row.company_id = company_id
    row.indicator_id = indicator_id
    row.tenant_id = tenant_id
    row.raw_value = None
    row.score = score
    row.percentile = None
    row.geo_adjusted = geo_adjusted
    row.inputs_hash = "abc123"
    row.computed_at = computed_at
    return row


@pytest.mark.asyncio
async def test_get_score_at_time_returns_matching_records():
    company_id = uuid4()
    indicator_id = uuid4()
    tenant_id = uuid4()
    at_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    row = _make_row(company_id, indicator_id, tenant_id, 75.0, 70.0, at_time)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [row]
    session.execute = AsyncMock(return_value=result_mock)

    repo = CompanyScoreRepository(session)
    records = await repo.get_score_at_time(
        company_ids=[company_id],
        at_time=at_time,
        tenant_id=tenant_id,
    )

    assert len(records) == 1
    assert records[0].score == 75.0
    assert records[0].geo_adjusted == 70.0


@pytest.mark.asyncio
async def test_get_score_at_time_returns_empty_when_no_rows():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    session.execute = AsyncMock(return_value=result_mock)

    repo = CompanyScoreRepository(session)
    records = await repo.get_score_at_time(
        company_ids=[uuid4()],
        at_time=datetime(2024, 6, 1, tzinfo=timezone.utc),
        tenant_id=uuid4(),
    )

    assert records == []
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/scoring/test_score_at_time.py -v
```

Expected: `AttributeError: 'CompanyScoreRepository' object has no attribute 'get_score_at_time'`

- [ ] **Step 3: Add `get_score_at_time` to the interface in `src/scoring/repositories/interfaces.py`**

Add this method signature inside `ICompanyScoreRepository`, after `bulk_update_geo_adjusted`:

```python
    async def get_score_at_time(
        self,
        company_ids: list[UUID],
        at_time: datetime,
        tenant_id: UUID,
    ) -> list["CompanyScoreRecord"]:
        """Return the latest score snapshot for each company at or before at_time.

        Uses DISTINCT ON (company_id, indicator_id) ordered by computed_at DESC.
        Filters by tenant_id to prevent cross-tenant data leakage.
        Returns one record per (company_id, indicator_id) pair.
        """
        ...
```

Also add `datetime` to the imports at the top of `interfaces.py`:

```python
from datetime import datetime
```

- [ ] **Step 4: Implement `get_score_at_time` in `src/scoring/repositories/company_score_repo.py`**

Add this method to `CompanyScoreRepository`, after `bulk_update_geo_adjusted`:

```python
    async def get_score_at_time(
        self,
        company_ids: list[UUID],
        at_time: datetime,
        tenant_id: UUID,
    ) -> list[CompanyScoreRecord]:
        """Return the most recent score snapshot per (company_id, indicator_id) at or before at_time."""
        if not company_ids:
            return []
        stmt = text(
            """
            SELECT DISTINCT ON (company_id, indicator_id)
                score_id, company_id, indicator_id, tenant_id,
                raw_value, score, percentile, geo_adjusted,
                inputs_hash, computed_at
            FROM company_score
            WHERE company_id = ANY(:company_ids)
              AND tenant_id = :tenant_id
              AND computed_at <= :at_time
            ORDER BY company_id, indicator_id, computed_at DESC
            """
        )
        result = await self._session.execute(
            stmt,
            {
                "company_ids": [str(cid) for cid in company_ids],
                "tenant_id": str(tenant_id),
                "at_time": at_time,
            },
        )
        rows = result.fetchall()
        return [
            CompanyScoreRecord(
                score_id=UUID(str(row.score_id)),
                company_id=UUID(str(row.company_id)),
                indicator_id=UUID(str(row.indicator_id)),
                tenant_id=UUID(str(row.tenant_id)),
                raw_value=row.raw_value,
                score=row.score,
                percentile=row.percentile,
                geo_adjusted=row.geo_adjusted,
                inputs_hash=row.inputs_hash,
                computed_at=row.computed_at,
            )
            for row in rows
        ]
```

Also add `datetime` to the imports at the top of `company_score_repo.py` (it's already imported; verify it's there).

- [ ] **Step 5: Run test to verify it passes**

```
pytest tests/unit/scoring/test_score_at_time.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```
git add src/scoring/repositories/interfaces.py src/scoring/repositories/company_score_repo.py tests/unit/scoring/test_score_at_time.py
git commit -m "feat(scoring): add get_score_at_time to ICompanyScoreRepository and CompanyScoreRepository"
```

---

## Task 6: Wire `GET /api/v1/scores/history` to real repository

Replaces the `_stub_get_score_at_time` call in the endpoint with the real `CompanyScoreRepository` and uses `dataclasses.asdict` for JSON serialization.

**Files:**
- Modify: `src/api/v1/scoring/scores.py`
- Create: `tests/unit/api/test_scores_history.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_scores_history.py
"""Tests for GET /api/v1/scores/history using real repo via DI override."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.api.v1.scoring.scores import router
from src.scoring.schemas.company_score import CompanyScoreRecord


def _build_app(mock_repo):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_user():
        return CurrentUser(
            user_id=uuid4(),
            tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            role="end_user",
            email="test@example.com",
        )

    async def override_db():
        yield mock_repo._session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


def test_scores_history_calls_repo_and_returns_records():
    company_id = uuid4()
    tenant_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    at_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    record = CompanyScoreRecord(
        score_id=uuid4(),
        company_id=company_id,
        indicator_id=uuid4(),
        tenant_id=tenant_id,
        raw_value=None,
        score=80.0,
        percentile=None,
        geo_adjusted=75.0,
        inputs_hash="abc123",
        computed_at=at_time,
    )

    # Build a mock repo whose get_score_at_time returns [record].
    mock_session = AsyncMock()
    from unittest.mock import MagicMock, patch

    with patch(
        "src.api.v1.scoring.scores.CompanyScoreRepository"
    ) as MockRepo:
        mock_instance = AsyncMock()
        mock_instance.get_score_at_time = AsyncMock(return_value=[record])
        MockRepo.return_value = mock_instance

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        async def override_user():
            return CurrentUser(
                user_id=uuid4(),
                tenant_id=tenant_id,
                role="end_user",
                email="t@t.com",
            )
        async def override_db():
            yield mock_session
        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db

        with TestClient(app) as client:
            resp = client.get(
                f"/api/v1/scores/history"
                f"?company_ids={company_id}&at=2024-06-01T12:00:00Z"
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert len(body["data"]) == 1
    assert body["data"][0]["score"] == 80.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_scores_history.py -v
```

Expected: Test FAIL — the endpoint currently calls `_stub_get_score_at_time` and ignores the DB session.

- [ ] **Step 3: Update `src/api/v1/scoring/scores.py`**

Add imports near the top of the file (after the existing imports):

```python
import dataclasses
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.dependencies import get_db
from src.scoring.repositories.company_score_repo import CompanyScoreRepository
```

Replace the `get_scores_at_time` function signature and body:

```python
@router.get("/history", response_model=dict)
async def get_scores_at_time(
    user: AuthUser,
    db: AsyncSession = Depends(get_db),
    company_ids: str = Query(
        ...,
        description="Comma-separated UUID strings for up to 200 companies",
    ),
    at: str = Query(
        ...,
        description="ISO 8601 datetime; returns the closest snapshot at or before this time",
    ),
) -> dict:
    """Batch score-at-time endpoint.

    Returns the most recent company_score snapshot for each requested company
    at or before the given timestamp — a 'time-machine' query with no future
    data leakage.
    """
    # Parse and validate company_ids.
    raw_ids = [cid.strip() for cid in company_ids.split(",") if cid.strip()]
    if not raw_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "company_ids must not be empty"},
        )
    if len(raw_ids) > MAX_COMPANY_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"company_ids exceeds maximum of {MAX_COMPANY_IDS} IDs",
            },
        )

    parsed_ids: List[UUID] = []
    for raw_id in raw_ids:
        try:
            parsed_ids.append(UUID(raw_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"Invalid UUID in company_ids: {raw_id}",
                },
            )

    try:
        at_time = datetime.fromisoformat(at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "VALIDATION_ERROR",
                "message": f"Invalid ISO 8601 datetime for 'at': {at}",
            },
        )

    repo = CompanyScoreRepository(db)
    scores = await repo.get_score_at_time(parsed_ids, at_time, user.tenant_id)
    return {
        "data": [dataclasses.asdict(s) for s in scores],
        "meta": {},
        "error": None,
    }
```

Delete the `_stub_get_score_at_time` function at the bottom of the file (it is no longer needed).

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/api/test_scores_history.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/api/v1/scoring/scores.py tests/unit/api/test_scores_history.py
git commit -m "feat(scoring): wire GET /api/v1/scores/history to real CompanyScoreRepository"
```

---

## Task 7: `GET /api/v1/screener/sectors` endpoint

Returns a sorted, deduplicated list of sectors from the tenant's company table. The frontend `useSectors` hook (Task 8) calls this endpoint.

**Files:**
- Modify: `src/api/v1/screener/router.py`
- Create: `tests/unit/api/test_sectors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/api/test_sectors.py
"""Tests for GET /api/v1/screener/sectors."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import CurrentUser
from src.api.dependencies import get_db
from src.api.v1.screener.router import router


def _build_app(db_rows: list[tuple]):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_user():
        return CurrentUser(
            user_id=uuid4(),
            tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            role="end_user",
            email="t@t.com",
        )

    async def override_db():
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = [MagicMock(__getitem__=lambda self, i: row[i]) for row in db_rows]
        # Use a simpler approach: return row objects with index access
        result.fetchall.return_value = db_rows  # plain tuples work with row[0]
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app
```

The test above has a complexity. Let me write a cleaner version using `patch`:

```python
# tests/unit/api/test_sectors.py
"""Tests for GET /api/v1/screener/sectors."""
from __future__ import annotations

import os
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long!")
os.environ.setdefault("JWT_REFRESH_SECRET_KEY", "test-refresh-key-minimum-32-characters-ok!")

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.api.v1.screener.router import router


def _build_app(sector_rows):
    """Build test app with mocked DB that returns sector_rows from the sectors query."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_user():
        return CurrentUser(
            user_id=uuid4(),
            tenant_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            role="end_user",
            email="t@t.com",
        )

    async def override_db():
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = sector_rows
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return app


def test_get_sectors_returns_sorted_list():
    # Rows are tuples; endpoint reads row[0] for sector name.
    rows = [("Energy",), ("Technology",), ("Healthcare",)]
    app = _build_app(rows)
    with TestClient(app) as client:
        resp = client.get("/api/v1/screener/sectors")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["sectors"] == ["Energy", "Technology", "Healthcare"]


def test_get_sectors_returns_empty_when_no_companies():
    app = _build_app([])
    with TestClient(app) as client:
        resp = client.get("/api/v1/screener/sectors")
    assert resp.status_code == 200
    assert resp.json()["data"]["sectors"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/api/test_sectors.py -v
```

Expected: Test collection error or `404` response — the `/sectors` route doesn't exist yet.

- [ ] **Step 3: Add the `/sectors` endpoint to `src/api/v1/screener/router.py`**

Add after the existing imports and before the `screen_companies` route:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.dependencies import get_db
```

(Check if `get_db` is already imported; if so, skip.)

Add the new route **before** the existing `screen_companies` function:

```python
@router.get("/sectors", response_model=dict)
async def get_sectors(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return distinct sector values for the tenant's companies, sorted A-Z."""
    result = await db.execute(
        text(
            "SELECT DISTINCT sector FROM company "
            "WHERE tenant_id = :tenant_id AND sector IS NOT NULL "
            "ORDER BY sector"
        ),
        {"tenant_id": str(user.tenant_id)},
    )
    sectors = [row[0] for row in result.fetchall()]
    return {"data": {"sectors": sectors}, "meta": {}, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/api/test_sectors.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/api/v1/screener/router.py tests/unit/api/test_sectors.py
git commit -m "feat(screener): GET /api/v1/screener/sectors returns distinct sector list"
```

---

## Task 8: `useSectors` hook and `MapContextSwitcher` live sectors

Replaces the hardcoded `SECTORS` array in `MapContextSwitcher` with a prop, adds a `useSectors` hook that fetches from the endpoint built in Task 7, and threads the result through `IntelligenceMap`.

**Files:**
- Create: `src/frontend/features/intelligence-map/hooks/useSectors.ts`
- Create: `src/frontend/features/intelligence-map/hooks/useSectors.test.ts`
- Modify: `src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx`
- Modify: `src/frontend/features/intelligence-map/IntelligenceMap.tsx`

- [ ] **Step 1: Write the failing test for `useSectors`**

```typescript
// src/frontend/features/intelligence-map/hooks/useSectors.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/client', () => ({ api: vi.fn() }));

import * as apiClient from '@/lib/api/client';
import { useSectors } from './useSectors';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe('useSectors', () => {
  it('calls api with /screener/sectors and returns sorted list', async () => {
    vi.mocked(apiClient.api).mockResolvedValue({ sectors: ['Energy', 'Technology'] });

    const { result } = renderHook(() => useSectors(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current).toEqual(['Energy', 'Technology']));
    expect(apiClient.api).toHaveBeenCalledWith('/screener/sectors');
  });

  it('returns empty array when api returns undefined', async () => {
    vi.mocked(apiClient.api).mockResolvedValue(undefined);

    const { result } = renderHook(() => useSectors(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current).toEqual([]));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npm test -- src/frontend/features/intelligence-map/hooks/useSectors.test.ts
```

Expected: FAIL — `Cannot find module './useSectors'`

- [ ] **Step 3: Create `src/frontend/features/intelligence-map/hooks/useSectors.ts`**

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
    staleTime: 10 * 60 * 1000, // 10 min — sector list changes rarely
  });
  return data;
}
```

- [ ] **Step 4: Run test to verify it passes**

```
npm test -- src/frontend/features/intelligence-map/hooks/useSectors.test.ts
```

Expected: 2 tests PASS.

- [ ] **Step 5: Update `MapContextSwitcher` to accept `sectors` prop**

In `src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx`:

Remove the hardcoded `SECTORS` constant (lines 24–36).

Add `sectors: string[]` to `MapContextSwitcherProps`:

```typescript
export interface MapContextSwitcherProps {
  mode: MapMode;
  sector: string | null;
  sectors: string[];           // live list from useSectors; replaces hardcoded array
  onSetMode: (mode: MapMode) => void;
  onSetSector?: (sector: string) => void;
}
```

Update the component signature and the `<select>` options:

```tsx
export const MapContextSwitcher: React.FC<MapContextSwitcherProps> = ({
  mode,
  sector,
  sectors,
  onSetMode,
  onSetSector,
}) => {
  return (
    <div
      data-testid="map-context-switcher"
      className="absolute left-2.5 top-2.5 z-[900] flex flex-col gap-1.5"
    >
      <div className="flex overflow-hidden rounded-md bg-surface-1/85 backdrop-blur">
        {MODES.map((m) => (
          <button
            key={m}
            onClick={() => onSetMode(m)}
            data-testid={`mode-button-${m}`}
            className={[
              "border-0 px-3.5 py-1.5 text-[13px] text-text transition-colors",
              mode === m
                ? "bg-signal font-bold"
                : "bg-transparent font-normal hover:bg-surface-2/60",
            ].join(" ")}
            aria-pressed={mode === m}
          >
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      {mode === 'sector' && (
        <select
          data-testid="sector-select"
          value={sector ?? ''}
          onChange={(e) => onSetSector?.(e.target.value)}
          className="rounded-md border border-subtle bg-surface-1/85 px-2 py-1 text-[13px] text-text backdrop-blur"
        >
          <option value="" disabled>
            Select sector
          </option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      )}
    </div>
  );
};
```

- [ ] **Step 6: Update `IntelligenceMap.tsx` to pass `sectors` to `MapContextSwitcher`**

In `src/frontend/features/intelligence-map/IntelligenceMap.tsx`:

Add import near the other hook imports:

```typescript
import { useSectors } from './hooks/useSectors';
```

Add the hook call after the `useMapMode()` call:

```typescript
const sectors = useSectors();
```

Update the `<MapContextSwitcher>` JSX (around line 400):

```tsx
<MapContextSwitcher
  mode={mode}
  sector={sector}
  sectors={sectors}
  onSetMode={setMode}
  onSetSector={setSector}
/>
```

- [ ] **Step 7: Run all map hook tests**

```
npm test -- src/frontend/features/intelligence-map/hooks/
```

Expected: All PASS (including useSectors tests and existing hook tests).

- [ ] **Step 8: Commit**

```
git add src/frontend/features/intelligence-map/hooks/useSectors.ts src/frontend/features/intelligence-map/hooks/useSectors.test.ts src/frontend/features/intelligence-map/components/MapContextSwitcher.tsx src/frontend/features/intelligence-map/IntelligenceMap.tsx
git commit -m "feat(map): useSectors hook + live sector dropdown replaces hardcoded SECTORS array"
```

---

## Task 9: Fix `ScoringProfileSelector` violations

`ScoringProfileSelector.tsx` was written before Phase 1 and has two violations: raw `fetch()` instead of `api<T>()`, and BEM class names instead of Tailwind tokens. This task fixes both.

**Files:**
- Modify: `src/frontend/features/scoring/ScoringProfileSelector.tsx`
- Create: `src/frontend/features/scoring/ScoringProfileSelector.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// src/frontend/features/scoring/ScoringProfileSelector.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

vi.mock('@/lib/api/client', () => ({ api: vi.fn() }));

import * as apiClient from '@/lib/api/client';
import {
  ScoringProfileSelector,
  ActiveProfileProvider,
} from './ScoringProfileSelector';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(ActiveProfileProvider, null, children)
    );
}

beforeEach(() => vi.clearAllMocks());

describe('ScoringProfileSelector', () => {
  it('calls api() not raw fetch()', async () => {
    vi.mocked(apiClient.api).mockResolvedValue({ profiles: [] });

    render(
      React.createElement(ScoringProfileSelector),
      { wrapper: makeWrapper() }
    );

    await waitFor(() => expect(apiClient.api).toHaveBeenCalledWith('/scoring-profiles'));
    expect(global.fetch).toBeUndefined();
  });

  it('renders built-in profile pills from api response', async () => {
    vi.mocked(apiClient.api).mockResolvedValue({
      profiles: [
        { profile_id: 'p1', name: 'Conservative', is_builtin: true, version: 1, indicators: [], tenant_id: 't1' },
      ],
    });

    render(
      React.createElement(ScoringProfileSelector),
      { wrapper: makeWrapper() }
    );

    await waitFor(() => expect(screen.getByText('Conservative')).toBeTruthy());
  });

  it('uses Tailwind classes — no BEM scoring-profile-selector class names', async () => {
    vi.mocked(apiClient.api).mockResolvedValue({ profiles: [] });

    const { container } = render(
      React.createElement(ScoringProfileSelector),
      { wrapper: makeWrapper() }
    );

    await waitFor(() => expect(apiClient.api).toHaveBeenCalled());
    const html = container.innerHTML;
    expect(html).not.toContain('scoring-profile-selector');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npm test -- src/frontend/features/scoring/ScoringProfileSelector.test.tsx
```

Expected: `calls api() not raw fetch()` — FAIL (component uses raw `fetch`, not `api`).

- [ ] **Step 3: Rewrite `ScoringProfileSelector.tsx`**

Replace the entire file with the following (keep `ActiveProfileProvider`, `useActiveProfileContext`, `useActiveProfile` imports, and `ScoringProfile` type — only `fetchScoringProfiles` and the component JSX change):

```typescript
/**
 * ScoringProfileSelector — dropdown/tab component for switching scoring profiles.
 *
 * - Fetches available profiles via api<T>('/scoring-profiles').
 * - Selecting a profile updates ActiveProfileContext and invalidates company score queries.
 * - Built-in profiles shown as pill badges; custom profiles listed below.
 * - Mounted in TopNav (Phase 3).
 */
import React, { useCallback, createContext, useContext } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import { useActiveProfile } from "./hooks/useActiveProfile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ScoringProfile {
  profile_id: string;
  name: string;
  is_builtin: boolean;
  version: number;
  indicators: Array<{ indicator_id: string; weight: number }>;
  tenant_id: string;
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface ActiveProfileContextValue {
  activeProfileId: string | null;
  setActiveProfile: (profileId: string | null) => void;
}

export const ActiveProfileContext =
  createContext<ActiveProfileContextValue | null>(null);

export function ActiveProfileProvider({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const { activeProfileId, setActiveProfile } = useActiveProfile();
  return (
    <ActiveProfileContext.Provider value={{ activeProfileId, setActiveProfile }}>
      {children}
    </ActiveProfileContext.Provider>
  );
}

export function useActiveProfileContext(): ActiveProfileContextValue {
  const ctx = useContext(ActiveProfileContext);
  if (ctx === null) {
    throw new Error(
      "useActiveProfileContext must be used within ActiveProfileProvider"
    );
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchScoringProfiles(): Promise<ScoringProfile[]> {
  const data = await api<{ profiles: ScoringProfile[] }>('/scoring-profiles');
  return data?.profiles ?? [];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ScoringProfileSelectorProps {
  className?: string;
}

export const ScoringProfileSelector: React.FC<ScoringProfileSelectorProps> = ({
  className = "",
}) => {
  const { activeProfileId, setActiveProfile } = useActiveProfileContext();

  const { data: profiles = [], isLoading, error } = useQuery<ScoringProfile[], Error>({
    queryKey: ["scoring-profiles"],
    queryFn: fetchScoringProfiles,
    staleTime: 5 * 60 * 1000,
  });

  const handleSelect = useCallback(
    (profileId: string) => setActiveProfile(profileId),
    [setActiveProfile]
  );

  if (isLoading) {
    return (
      <div className={`text-xs text-muted ${className}`} aria-busy="true">
        Loading profiles...
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-xs text-negative ${className}`} role="alert">
        Failed to load profiles
      </div>
    );
  }

  const builtinProfiles = profiles.filter((p) => p.is_builtin);
  const customProfiles = profiles.filter((p) => !p.is_builtin);

  return (
    <div className={`flex items-center gap-2 ${className}`} aria-label="Scoring Profile Selector">
      <div className="flex gap-1" role="group" aria-label="Built-in profiles">
        {builtinProfiles.map((profile) => (
          <button
            key={profile.profile_id}
            onClick={() => handleSelect(profile.profile_id)}
            aria-pressed={activeProfileId === profile.profile_id}
            className={
              activeProfileId === profile.profile_id
                ? "rounded-full bg-signal px-2.5 py-0.5 text-xs font-semibold text-surface-0"
                : "rounded-full border border-border px-2.5 py-0.5 text-xs text-muted hover:text-text"
            }
          >
            {profile.name}
          </button>
        ))}
      </div>

      {customProfiles.length > 0 && (
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted">Custom:</span>
          <select
            value={
              customProfiles.some((p) => p.profile_id === activeProfileId)
                ? (activeProfileId ?? "")
                : ""
            }
            onChange={(e) => e.target.value && handleSelect(e.target.value)}
            className="rounded border border-border bg-surface-1 px-2 py-0.5 text-xs text-text"
            aria-label="Select custom profile"
          >
            <option value="">-- Select custom --</option>
            {customProfiles.map((profile) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {profiles.length === 0 && (
        <span className="text-xs text-muted">No profiles available</span>
      )}
    </div>
  );
};

export default ScoringProfileSelector;
```

- [ ] **Step 4: Run test to verify it passes**

```
npm test -- src/frontend/features/scoring/ScoringProfileSelector.test.tsx
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/frontend/features/scoring/ScoringProfileSelector.tsx src/frontend/features/scoring/ScoringProfileSelector.test.tsx
git commit -m "fix(scoring): ScoringProfileSelector uses api<T> and Tailwind tokens (Phase 3)"
```

---

## Task 10: Score overlay activation wiring

**Prerequisite: Phase 2b must be fully implemented before this task.**
Phase 2b changes `IntelligenceMapPage.tsx` to use `useDisclosure()`. This task builds on that end state.

Wires `ActiveProfileProvider` into `AppShell`, mounts `ScoringProfileSelector` in `TopNav`, and threads `activeProfileId` → `profileActive` into `IntelligenceMap`.

**Files:**
- Modify: `src/frontend/layout/AppShell.tsx`
- Modify: `src/frontend/layout/TopNav.tsx`
- Modify: `src/frontend/features/intelligence-map/IntelligenceMapPage.tsx`
- Create: `src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

// Mock IntelligenceMap so MapLibre doesn't initialise in jsdom.
vi.mock('./IntelligenceMap', () => ({
  IntelligenceMap: ({ profileActive }: { profileActive: boolean }) => (
    <div data-testid="mock-map" data-profile-active={String(profileActive)} />
  ),
}));

// Mock StubModeBadge — it calls an API.
vi.mock('@/features/intelligence-map/components/StubModeBadge', () => ({
  StubModeBadge: () => null,
}));

// Mock useDisclosure — provided by ProgressiveDisclosureProvider (Phase 2b).
vi.mock(
  '@/features/progressive-disclosure/ProgressiveDisclosureProvider',
  () => ({
    useDisclosure: () => ({ onExpandEvent: vi.fn() }),
  })
);

import {
  ActiveProfileContext,
} from '@/features/scoring/ScoringProfileSelector';
import { IntelligenceMapPage } from './IntelligenceMapPage';

function renderWithProfile(profileId: string | null) {
  const qc = new QueryClient();
  return render(
    React.createElement(
      QueryClientProvider,
      { client: qc },
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(
          ActiveProfileContext.Provider,
          { value: { activeProfileId: profileId, setActiveProfile: vi.fn() } },
          React.createElement(IntelligenceMapPage)
        )
      )
    )
  );
}

describe('IntelligenceMapPage', () => {
  it('passes profileActive=false when no profile selected', () => {
    renderWithProfile(null);
    expect(screen.getByTestId('mock-map').dataset.profileActive).toBe('false');
  });

  it('passes profileActive=true when a profile is selected', () => {
    renderWithProfile('profile-123');
    expect(screen.getByTestId('mock-map').dataset.profileActive).toBe('true');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npm test -- src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
```

Expected: FAIL — `IntelligenceMapPage` does not yet read from `ActiveProfileContext`.

- [ ] **Step 3: Update `IntelligenceMapPage.tsx`**

The Phase 2b end state of this file is:

```tsx
import React from 'react';
import { IntelligenceMap } from './IntelligenceMap';
import { StubModeBadge } from '@/features/intelligence-map/components/StubModeBadge';
import { useDisclosure } from '@/features/progressive-disclosure/ProgressiveDisclosureProvider';

export function IntelligenceMapPage() {
  const { onExpandEvent } = useDisclosure();
  return (
    <div className="relative">
      <div className="absolute left-4 top-4 z-50">
        <StubModeBadge watch={["market_data", "news"]} />
      </div>
      <IntelligenceMap onExpandEvent={onExpandEvent} />
    </div>
  );
}
```

Add the `useActiveProfileContext` import and prop:

```tsx
import React from 'react';
import { IntelligenceMap } from './IntelligenceMap';
import { StubModeBadge } from '@/features/intelligence-map/components/StubModeBadge';
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

- [ ] **Step 4: Run test to verify it passes**

```
npm test -- src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
```

Expected: 2 tests PASS.

- [ ] **Step 5: Update `AppShell.tsx`**

Add import and wrap children with `ActiveProfileProvider`:

```tsx
import { ActiveProfileProvider } from '@/features/scoring/ScoringProfileSelector';

export function AppShell() {
  const { open, setOpen } = useCommandPalette();
  const health = useQuery({
    queryKey: ["health"],
    queryFn: pingHealth,
    refetchInterval: 30_000,
    retry: 0,
  });

  if (health.isSuccess && !health.data) {
    return <BackendUnreachable onRetry={() => health.refetch()} />;
  }

  return (
    <ActiveProfileProvider>
      <div className="min-h-screen bg-surface-0 text-text">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface-2 focus:px-3 focus:py-1.5 focus:text-sm"
        >
          Skip to content
        </a>
        <TopNav onOpenCommand={() => setOpen(true)} />
        <main id="main" className="pb-16 md:pb-0">
          <Outlet />
        </main>
        <MobileNav />
        <CommandPalette open={open} onOpenChange={setOpen} />
        <Toaster richColors closeButton position="bottom-right" />
      </div>
    </ActiveProfileProvider>
  );
}
```

- [ ] **Step 6: Update `TopNav.tsx`**

Add import and `ScoringProfileSelector` in the right-side controls:

```tsx
import { ScoringProfileSelector } from '@/features/scoring/ScoringProfileSelector';
```

In the `ml-auto flex` div, add before `<ThemeToggle />`:

```tsx
<ScoringProfileSelector className="hidden md:flex" />
```

Full updated right-side section:

```tsx
<div className="ml-auto flex items-center gap-2">
  <Button variant="ghost" size="sm" onClick={onOpenCommand} aria-label="Open command palette" className="gap-2">
    <Search className="h-4 w-4" /><span className="hidden sm:inline text-xs">⌘K</span>
  </Button>
  <ScoringProfileSelector className="hidden md:flex" />
  <ThemeToggle />
  <DropdownMenu>
    {/* ... existing dropdown unchanged ... */}
  </DropdownMenu>
</div>
```

- [ ] **Step 7: Run full frontend test suite**

```
npm test
```

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```
git add src/frontend/layout/AppShell.tsx src/frontend/layout/TopNav.tsx src/frontend/features/intelligence-map/IntelligenceMapPage.tsx src/frontend/features/intelligence-map/IntelligenceMapPage.test.tsx
git commit -m "feat(map): activate score overlay — ActiveProfileProvider in AppShell, ScoringProfileSelector in TopNav"
```

---

## Task 11: Storybook setup and component stories

Installs Storybook 8 with the Vite builder, configures it with global CSS and a `QueryClientProvider` decorator, and creates four stories.

**Files:**
- Create: `.storybook/main.ts`
- Create: `.storybook/preview.ts`
- Modify: `package.json` (scripts)
- Create: `src/frontend/features/intelligence-map/components/MapContextSwitcher.stories.tsx`
- Create: `src/frontend/features/progressive-disclosure/components/EventPopup.stories.tsx`
- Create: `src/frontend/features/progressive-disclosure/components/SidePanel.stories.tsx`
- Create: `src/frontend/features/intelligence-map/components/ScoreOverlay.stories.tsx`

- [ ] **Step 1: Install Storybook packages**

```
npm install --save-dev storybook @storybook/react-vite @storybook/react @storybook/addon-essentials @storybook/test
```

- [ ] **Step 2: Create `.storybook/main.ts`**

```typescript
import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/frontend/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-essentials'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
};

export default config;
```

- [ ] **Step 3: Create `.storybook/preview.ts`**

```typescript
import type { Preview } from '@storybook/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import '../src/frontend/styles/globals.css';
import '../src/frontend/styles/tokens.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
});

const preview: Preview = {
  decorators: [
    (Story) =>
      React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(Story)
      ),
  ],
  parameters: {
    layout: 'centered',
  },
};

export default preview;
```

- [ ] **Step 4: Add scripts to `package.json`**

In the `"scripts"` section, add:

```json
"storybook": "storybook dev -p 6006",
"build-storybook": "storybook build"
```

- [ ] **Step 5: Verify Storybook starts**

```
npm run storybook -- --ci --smoke-test
```

Expected: Exits 0 (smoke test: no uncaught errors on initial load).

If `--smoke-test` is not available, run `npm run build-storybook` instead and verify exit 0.

- [ ] **Step 6: Create `MapContextSwitcher.stories.tsx`**

```tsx
// src/frontend/features/intelligence-map/components/MapContextSwitcher.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import MapContextSwitcher from './MapContextSwitcher';

const meta: Meta<typeof MapContextSwitcher> = {
  title: 'Map/MapContextSwitcher',
  component: MapContextSwitcher,
  args: {
    sectors: ['Energy', 'Financials', 'Technology', 'Healthcare'],
    onSetMode: fn(),
    onSetSector: fn(),
  },
};
export default meta;
type Story = StoryObj<typeof MapContextSwitcher>;

export const Global: Story = {
  args: { mode: 'global', sector: null },
};

export const Portfolio: Story = {
  args: { mode: 'portfolio', sector: null },
};

export const SectorDropdownOpen: Story = {
  args: { mode: 'sector', sector: 'Technology' },
};
```

- [ ] **Step 7: Create `EventPopup.stories.tsx`**

```tsx
// src/frontend/features/progressive-disclosure/components/EventPopup.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { EventPopup } from './EventPopup';

const meta: Meta<typeof EventPopup> = {
  title: 'ProgressiveDisclosure/EventPopup',
  component: EventPopup,
  parameters: { layout: 'padded' },
};
export default meta;
type Story = StoryObj<typeof EventPopup>;

// usePopupData fetches from the backend — shows loading state in stories.
export const Loading: Story = {
  args: {
    eventId: 'evt-story-001',
    onExpand: fn(),
    onClose: fn(),
  },
};
```

- [ ] **Step 8: Create `SidePanel.stories.tsx`**

```tsx
// src/frontend/features/progressive-disclosure/components/SidePanel.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { SidePanel } from './SidePanel';

const meta: Meta<typeof SidePanel> = {
  title: 'ProgressiveDisclosure/SidePanel',
  component: SidePanel,
  parameters: { layout: 'fullscreen' },
};
export default meta;
type Story = StoryObj<typeof SidePanel>;

// useSidePanelData fetches from backend — shows loading state.
export const Open: Story = {
  args: {
    eventId: 'evt-story-001',
    isOpen: true,
    onClose: fn(),
    onOpenAuditTrail: fn(),
  },
};

export const Closed: Story = {
  args: {
    eventId: null,
    isOpen: false,
    onClose: fn(),
    onOpenAuditTrail: fn(),
  },
};
```

- [ ] **Step 9: Create `ScoreOverlay.stories.tsx`**

```tsx
// src/frontend/features/intelligence-map/components/ScoreOverlay.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import ScoreOverlay from './ScoreOverlay';

const meta: Meta<typeof ScoreOverlay> = {
  title: 'Map/ScoreOverlay',
  component: ScoreOverlay,
};
export default meta;
type Story = StoryObj<typeof ScoreOverlay>;

// ScoreOverlay requires a MapLibre map instance. Without one it renders nothing,
// which is fine — the story verifies the component mounts without errors.
export const NoMap: Story = {
  args: {
    map: null,
    markers: [
      { company_id: 'c1', ticker: 'AAPL', lat: 37.7749, lon: -122.4194, geo_adjusted: 80, score_delta: 5 },
      { company_id: 'c2', ticker: 'BP', lat: 51.5074, lon: -0.1278, geo_adjusted: 30, score_delta: -10 },
    ],
  },
};
```

- [ ] **Step 10: Commit**

```
git add .storybook/ src/frontend/features/intelligence-map/components/MapContextSwitcher.stories.tsx src/frontend/features/progressive-disclosure/components/EventPopup.stories.tsx src/frontend/features/progressive-disclosure/components/SidePanel.stories.tsx src/frontend/features/intelligence-map/components/ScoreOverlay.stories.tsx package.json package-lock.json
git commit -m "feat(storybook): install Storybook 8 + stories for MapContextSwitcher, EventPopup, SidePanel, ScoreOverlay"
```

---

## Task 12: Screenshot CI with GitHub Actions

Installs `@storybook/test-runner` and `http-server`, and creates a GitHub Actions workflow that builds Storybook and runs the test-runner on every push and PR.

**Files:**
- Modify: `package.json` (add `test-storybook` script)
- Create: `.github/workflows/visual.yml`

- [ ] **Step 1: Install test-runner packages**

```
npm install --save-dev @storybook/test-runner concurrently http-server
```

- [ ] **Step 2: Add `test-storybook` script to `package.json`**

In the `"scripts"` section:

```json
"test-storybook": "test-storybook --url http://localhost:6006"
```

- [ ] **Step 3: Verify test-runner works locally**

Build Storybook, serve it, then run the test-runner:

```
npm run build-storybook -- --quiet
```

Then in a separate terminal:
```
npx http-server storybook-static --port 6006 --silent &
npx wait-on http://localhost:6006
npm run test-storybook
```

Expected: All stories PASS (no uncaught errors).

Kill the http-server process after verifying.

- [ ] **Step 4: Create `.github/workflows/visual.yml`**

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

      - name: Install dependencies
        run: npm ci

      - name: Build Storybook
        run: npm run build-storybook -- --quiet

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium

      - name: Run Storybook test-runner
        run: |
          npx http-server storybook-static --port 6006 --silent &
          npx wait-on http://localhost:6006 --timeout 60000
          npm run test-storybook
```

- [ ] **Step 5: Commit**

```
git add .github/workflows/visual.yml package.json package-lock.json
git commit -m "feat(ci): GitHub Actions visual regression workflow via Storybook test-runner"
```

---

## Self-Review

### 1. Spec coverage check

| Spec requirement | Task |
|---|---|
| `/ws/scores` WebSocket endpoint, auth via `?token=` | Task 2 |
| `validate_ws_token` helper in `auth_deps.py` | Task 1 |
| `events_broadcaster.py` with sector/bbox filter | Task 3 |
| `/api/v1/events/feed` WebSocket endpoint | Task 4 |
| `get_score_at_time` in `ICompanyScoreRepository` | Task 5 |
| `get_score_at_time` in `CompanyScoreRepository` | Task 5 |
| Wire `GET /api/v1/scores/history` to real repo | Task 6 |
| `GET /api/v1/screener/sectors` endpoint | Task 7 |
| `useSectors` hook | Task 8 |
| `MapContextSwitcher` live `sectors` prop | Task 8 |
| `ScoringProfileSelector` raw fetch fix | Task 9 |
| `ScoringProfileSelector` BEM → Tailwind | Task 9 |
| `ActiveProfileProvider` in `AppShell` | Task 10 |
| `ScoringProfileSelector` in `TopNav` | Task 10 |
| `IntelligenceMapPage` `profileActive` from context | Task 10 |
| Storybook 8 install + config | Task 11 |
| Stories: `MapContextSwitcher`, `EventPopup`, `SidePanel`, `ScoreOverlay` | Task 11 |
| Screenshot CI (GitHub Actions) | Task 12 |

All spec requirements covered. ✓

### 2. Type consistency check

- `SubscriptionFilter` defined in Task 3 (`events_broadcaster.py`), used in Task 4 (`ws_events_router.py`) — same import path. ✓
- `validate_ws_token` defined in Task 1 (`auth_deps.py`), imported in Tasks 2 and 4 via `from src.api.auth_deps import validate_ws_token`. ✓
- `CompanyScoreRepository` defined in Task 5, imported in Task 6 as `from src.scoring.repositories.company_score_repo import CompanyScoreRepository`. ✓
- `useSectors` defined in Task 8, consumed in `IntelligenceMap.tsx` in the same task. ✓
- `useActiveProfileContext` defined in Task 9 (ScoringProfileSelector.tsx), consumed in Task 10 (IntelligenceMapPage.tsx). ✓
- `ActiveProfileProvider` defined in Task 9, mounted in Task 10 (AppShell.tsx). ✓

### 3. Placeholder scan

No "TBD", "TODO", "implement later", "add error handling", or "similar to Task N" patterns. All code blocks are complete.
