"""Unit tests for GET /api/v1/admin/cache/stats endpoint.

Tests:
- Response shape is correct when Redis counters have data
- 403 returned for non-admin callers
- Zero counters (first boot) return 0 hit rate gracefully
- hit_rate_pct calculation is correct
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.admin.cache_stats import (
    admin_cache_router,
    get_redis_client,
    require_admin,
)


# ---------------------------------------------------------------------------
# Test app setup
# ---------------------------------------------------------------------------


def _build_test_app(
    redis_mock: MagicMock | None = None,
    admin_override: bool = True,
) -> FastAPI:
    """Build a minimal FastAPI test app with the cache stats router.

    Args:
        redis_mock: Mock Redis client to inject. If None a zero-counter mock is used.
        admin_override: If True, bypass role check (caller is admin).
                        If False, leave require_admin to raise 403.
    """
    app = FastAPI()
    app.include_router(admin_cache_router, prefix="/api/v1")

    if admin_override:
        async def override_require_admin():
            return {"role": "admin"}
        app.dependency_overrides[require_admin] = override_require_admin

    if redis_mock is not None:
        async def override_redis():
            return redis_mock
        app.dependency_overrides[get_redis_client] = override_redis

    return app


def _make_redis_mock(counters: dict[str, int]) -> MagicMock:
    """Build a mock Redis client whose GET returns values from `counters` dict."""
    redis = MagicMock()

    async def mock_get(key: str) -> bytes | None:
        val = counters.get(key)
        return str(val).encode() if val is not None else None

    redis.get = mock_get
    return redis


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cache_stats_response_shape_with_data():
    """GET /stats with non-zero counters returns correct shape and values."""
    counters = {
        "cache_stats:hits:redis": 9901,
        "cache_stats:misses:redis": 99,
        "cache_stats:hits:postgres": 54,
        "cache_stats:misses:postgres": 45,
        "cache_stats:misses:provider": 45,
    }
    redis_mock = _make_redis_mock(counters)
    app = _build_test_app(redis_mock=redis_mock, admin_override=True)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/cache/stats")

    assert response.status_code == 200
    body = response.json()

    assert body["error"] is None
    assert body["meta"]["since"] == "service_start"

    data = body["data"]
    assert data["redis"]["hits"] == 9901
    assert data["redis"]["misses"] == 99
    assert data["redis"]["hit_rate_pct"] == pytest.approx(99.0, abs=0.1)

    assert data["postgres"]["hits"] == 54
    assert data["postgres"]["misses"] == 45
    assert data["postgres"]["hit_rate_pct"] == pytest.approx(54.5, abs=0.1)

    assert data["provider_calls_total"] == 45


def test_cache_stats_zero_counters_return_zero_hit_rate():
    """GET /stats when Redis has no counters returns 0.0 hit_rate_pct."""
    redis_mock = _make_redis_mock({})  # all counters absent
    app = _build_test_app(redis_mock=redis_mock, admin_override=True)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/cache/stats")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["redis"]["hits"] == 0
    assert data["redis"]["misses"] == 0
    assert data["redis"]["hit_rate_pct"] == 0.0
    assert data["provider_calls_total"] == 0


def test_cache_stats_returns_403_for_non_admin():
    """GET /stats without admin role returns 403."""
    redis_mock = _make_redis_mock({})
    # admin_override=False: leave require_admin to raise 403
    app = _build_test_app(redis_mock=redis_mock, admin_override=False)

    # Also override get_redis_client so the endpoint doesn't fail on that first
    async def override_redis():
        return redis_mock
    app.dependency_overrides[get_redis_client] = override_redis

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/admin/cache/stats")

    assert response.status_code == 403


def test_cache_stats_hit_rate_pct_100_percent():
    """Hit rate is 100.0% when there are no misses."""
    counters = {
        "cache_stats:hits:redis": 1000,
        # no misses key → treated as 0
    }
    redis_mock = _make_redis_mock(counters)
    app = _build_test_app(redis_mock=redis_mock, admin_override=True)

    with TestClient(app) as client:
        response = client.get("/api/v1/admin/cache/stats")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["redis"]["hit_rate_pct"] == pytest.approx(100.0, abs=0.01)
