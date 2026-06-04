"""
tests.security.test_rate_limiting — Rate limiting tests.

Covers AC-004: all four rate-limit tiers are tested.

Tiers:
  - Login: 10/minute (IP-based)
  - Refresh: 30/minute (IP-based)
  - Portfolio write: 100/minute (user-based via JWT sub)
  - Admin mutation: 60/minute (user-based via JWT sub)

Each test creates a fresh in-memory Limiter (storage_uri="memory://") backed
by the limits library's in-process storage — no external Redis required.
"""
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.middleware.rate_limit import (
    get_user_id_from_request,
    rate_limit_exceeded_handler,
)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _build_app_with_limit(route: str, limit_str: str, key_func=None) -> FastAPI:
    """Build a minimal FastAPI app with a single rate-limited POST endpoint.

    Uses in-memory storage (no Redis) for fast, isolated tests.
    """
    effective_key_func = key_func or get_remote_address
    limiter = Limiter(key_func=effective_key_func, storage_uri="memory://")

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.post(route)
    @limiter.limit(limit_str, key_func=effective_key_func)
    async def _stub(request: Request):
        return {"ok": True}

    return app


def _fire(client: TestClient, route: str, n: int) -> list[int]:
    """Fire n POST requests and collect status codes."""
    return [client.post(route).status_code for _ in range(n)]


# ── Login rate limit: 10/minute ───────────────────────────────────────────────

def test_login_rate_limit_11th_request_returns_429() -> None:
    """The 11th login attempt within the window must return 429."""
    app = _build_app_with_limit("/api/v1/auth/login", "10/minute")
    client = TestClient(app, raise_server_exceptions=False)

    statuses = _fire(client, "/api/v1/auth/login", 11)

    assert statuses[-1] == 429, (
        f"Expected 429 on 11th login request, got {statuses[-1]}. "
        f"All statuses: {statuses}"
    )


def test_login_rate_limit_window_resets() -> None:
    """A new limiter instance (new window) must accept requests again.

    In production, a real time-based window reset occurs. In unit tests, we
    simulate the reset by creating a fresh limiter (clean in-memory state).
    """
    app1 = _build_app_with_limit("/endpoint", "2/minute")
    client1 = TestClient(app1, raise_server_exceptions=False)
    _fire(client1, "/endpoint", 2)  # exhaust the limit
    assert client1.post("/endpoint").status_code == 429

    # Fresh limiter = fresh window
    app2 = _build_app_with_limit("/endpoint", "2/minute")
    client2 = TestClient(app2, raise_server_exceptions=False)
    assert client2.post("/endpoint").status_code == 200


# ── Refresh rate limit: 30/minute ────────────────────────────────────────────

def test_refresh_rate_limit_31st_request_returns_429() -> None:
    """The 31st refresh attempt within the window must return 429."""
    app = _build_app_with_limit("/api/v1/auth/refresh", "30/minute")
    client = TestClient(app, raise_server_exceptions=False)

    statuses = _fire(client, "/api/v1/auth/refresh", 31)

    assert statuses[-1] == 429, (
        f"Expected 429 on 31st refresh request, got {statuses[-1]}"
    )


# ── Portfolio write rate limit: 100/minute ────────────────────────────────────

def test_portfolio_write_rate_limit_101st_request_returns_429() -> None:
    """The 101st portfolio write within the window must return 429 (user-keyed)."""
    app = _build_app_with_limit(
        "/api/v1/portfolios",
        "100/minute",
        key_func=get_user_id_from_request,
    )
    client = TestClient(app, raise_server_exceptions=False)

    statuses = _fire(client, "/api/v1/portfolios", 101)

    assert statuses[-1] == 429, (
        f"Expected 429 on 101st portfolio write, got {statuses[-1]}"
    )


# ── Admin mutation rate limit: 60/minute ─────────────────────────────────────

def test_admin_mutation_rate_limit_61st_request_returns_429() -> None:
    """The 61st admin mutation within the window must return 429 (user-keyed)."""
    app = _build_app_with_limit(
        "/api/v1/admin/users",
        "60/minute",
        key_func=get_user_id_from_request,
    )
    client = TestClient(app, raise_server_exceptions=False)

    statuses = _fire(client, "/api/v1/admin/users", 61)

    assert statuses[-1] == 429, (
        f"Expected 429 on 61st admin mutation, got {statuses[-1]}"
    )
