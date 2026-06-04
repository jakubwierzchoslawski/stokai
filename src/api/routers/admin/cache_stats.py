"""GET /api/v1/admin/cache/stats — aggregate cache hit rate endpoint.

Returns Redis-tier, PostgreSQL-tier, and provider (external API) call counts
accumulated since service start via Redis INCR counters set by CacheTelemetry.

Access control: role == "admin" (D2).

Response shape:
    {
      "data": {
        "redis":    {"hits": int, "misses": int, "hit_rate_pct": float},
        "postgres": {"hits": int, "misses": int, "hit_rate_pct": float},
        "provider_calls_total": int
      },
      "meta":  {"since": "service_start"},
      "error": null
    }

Counter keys in Redis (set by CacheTelemetry.record):
    cache_stats:hits:redis
    cache_stats:misses:redis
    cache_stats:hits:postgres
    cache_stats:misses:postgres
    cache_stats:misses:provider   (provider MISS == provider call)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ingestion.cache_telemetry import CacheTier

admin_cache_router = APIRouter(prefix="/admin/cache", tags=["admin"])


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _success_envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {"data": data, "meta": {"since": "service_start"}, "error": None}


def _error_envelope(code: str, message: str) -> dict[str, Any]:
    return {"data": None, "error": {"code": code, "message": message}}


def _hit_rate_pct(hits: int, misses: int) -> float:
    total = hits + misses
    if total == 0:
        return 0.0
    return round(hits / total * 100, 1)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_redis_client() -> Any:
    """Provide the Redis client.

    In production override this dependency with a real aioredis client.
    In tests override via app.dependency_overrides.
    """
    raise NotImplementedError(
        "get_redis_client must be overridden with a configured async Redis client."
    )


async def require_admin(
    authorization: str | None = None,
) -> dict[str, Any]:
    """Dependency placeholder — verify caller has role == 'admin'.

    In production this is fulfilled by the JWT middleware extracting claims
    from the Authorization header and checking role == "admin".
    In tests override via app.dependency_overrides.

    Raises HTTPException 403 if role is not admin.
    """
    # This default implementation always rejects unless overridden.
    # The real implementation is injected at app-wiring time.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role required",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@admin_cache_router.get("/stats")
async def get_cache_stats(
    _admin: dict[str, Any] = Depends(require_admin),
    redis: Any = Depends(get_redis_client),
) -> JSONResponse:
    """Return aggregate cache hit/miss counts per tier since service start.

    Reads counters set by CacheTelemetry.record() via Redis INCR:
        cache_stats:hits:{tier}
        cache_stats:misses:{tier}

    Returns:
        200 with tier-level hit rate statistics.
        403 if caller is not an admin (enforced by require_admin dependency).
    """
    async def _get_counter(key: str) -> int:
        """Read a Redis counter; return 0 if key does not exist."""
        try:
            value = await redis.get(key)
            return int(value) if value is not None else 0
        except Exception:
            return 0

    redis_hits = await _get_counter(f"cache_stats:hits:{CacheTier.REDIS}")
    redis_misses = await _get_counter(f"cache_stats:misses:{CacheTier.REDIS}")
    pg_hits = await _get_counter(f"cache_stats:hits:{CacheTier.POSTGRES}")
    pg_misses = await _get_counter(f"cache_stats:misses:{CacheTier.POSTGRES}")
    provider_calls = await _get_counter(f"cache_stats:misses:{CacheTier.PROVIDER}")

    data = {
        "redis": {
            "hits": redis_hits,
            "misses": redis_misses,
            "hit_rate_pct": _hit_rate_pct(redis_hits, redis_misses),
        },
        "postgres": {
            "hits": pg_hits,
            "misses": pg_misses,
            "hit_rate_pct": _hit_rate_pct(pg_hits, pg_misses),
        },
        "provider_calls_total": provider_calls,
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_success_envelope(data),
    )
