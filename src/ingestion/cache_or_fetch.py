"""CacheOrFetch — three-tier cache cascade: Redis -> PostgreSQL -> fetch_fn.

The abstract base class defines the cascade logic and key-building.
The concrete DataCacheOrFetch class wires it to RedisCacheLayer and
CacheEntryRepository via constructor injection.

Two-tier cache key format
--------------------------
Shared data types (PRICE_BAR, PRICE_BAR_HISTORICAL, FUNDAMENTALS, MACRO,
EVENT_EMBEDDING — see config.ttl_defaults.SHARED_DATA_TYPES):
    "{data_type}:{entity_id}:{params_hash}"
    NO user_id or tenant_id in the key.
    Rationale: user A's price bar fetch is served from the cache to user B —
               the flat-API-bill invariant (Principle 2) depends on this.

User-specific data types (portfolio, watchlist — NOT in SHARED_DATA_TYPES):
    "{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash}"
    Each user has their own isolated cache entry.

If user_id or tenant_id is passed to _build_key() for a shared type,
those parameters are ignored and a DEBUG-level warning is logged.

params_hash = sha256(sorted(params.items())).hexdigest()[:8]

When the caller already has a complete cache_key, they pass it directly
and bypass key construction.

Serialization: msgpack (compact binary; avoids JSON float precision issues).
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import msgpack

from ingestion.cache_telemetry import (
    CacheEvent,
    CacheOutcome,
    CacheTelemetry,
    CacheTier,
    NullCacheTelemetry,
)
from ingestion.ttl_policy import (
    DEFAULT_TTL_REGISTRY,
    DataType,
    TTLPolicy,
)

logger = logging.getLogger(__name__)

# Imported lazily to avoid a circular import (config imports ingestion types).
# Resolved at first call to _build_key via _get_shared_data_types().
_SHARED_DATA_TYPES: frozenset[DataType] | None = None


def _get_shared_data_types() -> frozenset[DataType]:
    """Lazily load SHARED_DATA_TYPES from config to avoid circular imports."""
    global _SHARED_DATA_TYPES
    if _SHARED_DATA_TYPES is None:
        from config.ttl_defaults import SHARED_DATA_TYPES  # noqa: PLC0415
        _SHARED_DATA_TYPES = SHARED_DATA_TYPES
    return _SHARED_DATA_TYPES

T = TypeVar("T")


def build_cache_key(
    data_type: DataType | str,
    entity_id: str,
    params: dict[str, Any] | None = None,
    user_id: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """Build a deterministic cache key.

    For shared data types (PRICE_BAR, PRICE_BAR_HISTORICAL, FUNDAMENTALS,
    MACRO, EVENT_EMBEDDING):
        Format: ``"{data_type}:{entity_id}:{params_hash[:8]}"``
        user_id and tenant_id are ignored (with a DEBUG-level log warning if
        provided, since passing them for shared types is a caller error).

    For user-specific data types:
        Format: ``"{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash[:8]}"``

    Args:
        data_type: The data type (DataType enum or plain string).
        entity_id: The entity identifier (e.g. ticker symbol, event ID).
        params: Optional extra parameters that disambiguate variants of the
            same entity (e.g. date range, resolution). Defaults to empty dict.
        user_id: User identifier — ignored for shared data types.
        tenant_id: Tenant identifier — ignored for shared data types.

    Returns:
        A collision-resistant cache key string.
    """
    params = params or {}
    params_str = str(sorted(params.items()))
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:8]

    shared_types = _get_shared_data_types()
    is_shared = (
        isinstance(data_type, DataType) and data_type in shared_types
        or str(data_type) in {str(t) for t in shared_types}
    )

    if is_shared:
        if user_id is not None or tenant_id is not None:
            logger.debug(
                "build_cache_key: user_id/tenant_id ignored for shared data type %r "
                "(shared types use global keys — no user scoping)",
                data_type,
            )
        return f"{data_type}:{entity_id}:{params_hash}"

    # User-specific types require user_id and tenant_id
    return f"{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash}"


class CacheOrFetch(ABC):
    """Abstract three-tier cache cascade.

    Subclasses implement the four abstract IO methods; the public
    ``cache_or_fetch`` method orchestrates the cascade and serialization.

    Cascade order:
        1. Redis GET  → hit → deserialize → return
        2. Redis miss → PostgreSQL SELECT → hit → write-back to Redis → return
        3. PG miss    → call fetch_fn → store both layers → return

    Error handling:
        - Redis failure → log warning, fall through to PG.
        - PG failure    → log error, fall through to fetch_fn.
        The system always returns data; availability > consistency on errors.
    """

    def __init__(
        self,
        ttl_registry: dict[DataType, TTLPolicy] | None = None,
        telemetry: CacheTelemetry | None = None,
    ) -> None:
        self._ttl_registry = ttl_registry if ttl_registry is not None else DEFAULT_TTL_REGISTRY
        self._telemetry: CacheTelemetry = telemetry if telemetry is not None else NullCacheTelemetry()

    # ------------------------------------------------------------------
    # Abstract IO methods — implemented by DataCacheOrFetch
    # ------------------------------------------------------------------

    @abstractmethod
    async def _redis_get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def _redis_set(
        self, key: str, value: bytes, ttl_seconds: int | None, data_type: DataType | None = None
    ) -> None: ...

    @abstractmethod
    async def _pg_get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def _pg_set(
        self, key: str, data_type: str, value: bytes, ttl_seconds: int | None
    ) -> None: ...

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize(value: Any) -> bytes:
        return msgpack.packb(value, use_bin_type=True)

    @staticmethod
    def _deserialize(data: bytes) -> Any:
        return msgpack.unpackb(data, raw=False)

    # ------------------------------------------------------------------
    # Public cascade entry point
    # ------------------------------------------------------------------

    async def cache_or_fetch(
        self,
        key: str,
        data_type: DataType,
        fetch_fn: Callable[[], Awaitable[T]],
        request_id: str | None = None,
    ) -> T:
        """Execute the three-tier cache cascade and return a value.

        Args:
            key: Pre-built cache key. Use ``build_cache_key()`` to construct it.
            data_type: The data type — used to look up the ``TTLPolicy``.
            fetch_fn: Async callable that fetches the value from the external
                API when both cache layers miss.
            request_id: Optional request ID for log correlation. Propagated from
                FastAPI middleware; None when called outside an HTTP context.

        Returns:
            The cached or freshly fetched value, deserialized.
        """
        policy = self._ttl_registry.get(data_type)
        redis_ttl = policy.redis_ttl_seconds if policy else None
        pg_ttl = policy.pg_ttl_seconds if policy else None

        # --- Tier 1: Redis ---
        redis_bytes: bytes | None = None
        redis_error = False
        try:
            redis_bytes = await self._redis_get(key)
        except Exception as exc:
            logger.warning("Redis GET error for key %r: %s", key, exc)
            redis_error = True

        if redis_bytes is not None:
            self._telemetry.record(CacheEvent(
                cache_key=key,
                data_type=str(data_type),
                tier=CacheTier.REDIS,
                outcome=CacheOutcome.HIT,
                request_id=request_id,
            ))
            return self._deserialize(redis_bytes)  # type: ignore[return-value]

        if not redis_error:
            self._telemetry.record(CacheEvent(
                cache_key=key,
                data_type=str(data_type),
                tier=CacheTier.REDIS,
                outcome=CacheOutcome.MISS,
                request_id=request_id,
            ))

        # --- Tier 2: PostgreSQL ---
        pg_bytes: bytes | None = None
        pg_error = False
        try:
            pg_bytes = await self._pg_get(key)
        except Exception as exc:
            logger.error("PostgreSQL GET error for key %r: %s", key, exc)
            pg_error = True

        if pg_bytes is not None:
            self._telemetry.record(CacheEvent(
                cache_key=key,
                data_type=str(data_type),
                tier=CacheTier.POSTGRES,
                outcome=CacheOutcome.HIT,
                request_id=request_id,
            ))
            # Write-back to Redis hot cache
            try:
                await self._redis_set(key, pg_bytes, redis_ttl, data_type)
            except Exception as exc:
                logger.warning("Redis write-back failed for key %r: %s", key, exc)
            return self._deserialize(pg_bytes)  # type: ignore[return-value]

        if not pg_error:
            self._telemetry.record(CacheEvent(
                cache_key=key,
                data_type=str(data_type),
                tier=CacheTier.POSTGRES,
                outcome=CacheOutcome.MISS,
                request_id=request_id,
            ))

        # --- Tier 3: External API ---
        self._telemetry.record(CacheEvent(
            cache_key=key,
            data_type=str(data_type),
            tier=CacheTier.PROVIDER,
            outcome=CacheOutcome.MISS,
            request_id=request_id,
        ))
        value: T = await fetch_fn()
        serialized = self._serialize(value)

        try:
            await self._redis_set(key, serialized, redis_ttl, data_type)
        except Exception as exc:
            logger.warning("Redis SET failed after fetch for key %r: %s", key, exc)

        try:
            await self._pg_set(key, str(data_type), serialized, pg_ttl)
        except Exception as exc:
            logger.error("PostgreSQL SET failed after fetch for key %r: %s", key, exc)

        return value


class DataCacheOrFetch(CacheOrFetch):
    """Concrete cache-or-fetch implementation.

    Wires the abstract IO methods to ``RedisCacheLayer`` and
    ``CacheEntryRepository``, both injected via constructor.

    Args:
        redis_layer: An instance of ``RedisCacheLayer``.
        pg_repo: An instance of ``CacheEntryRepository``.
        ttl_registry: Optional TTL registry; defaults to ``DEFAULT_TTL_REGISTRY``.
    """

    def __init__(
        self,
        redis_layer: Any,
        pg_repo: Any,
        ttl_registry: dict[DataType, TTLPolicy] | None = None,
        telemetry: CacheTelemetry | None = None,
    ) -> None:
        super().__init__(ttl_registry=ttl_registry, telemetry=telemetry)
        self._redis_layer = redis_layer
        self._pg_repo = pg_repo

    async def _redis_get(self, key: str) -> bytes | None:
        return await self._redis_layer.get(key)

    async def _redis_set(
        self, key: str, value: bytes, ttl_seconds: int | None, data_type: DataType | None = None
    ) -> None:
        await self._redis_layer.set(key, value, ttl_seconds, data_type)

    async def _pg_get(self, key: str) -> bytes | None:
        return await self._pg_repo.get(key)

    async def _pg_set(
        self, key: str, data_type: str, value: bytes, ttl_seconds: int | None
    ) -> None:
        await self._pg_repo.set(key, data_type, value, ttl_seconds)
