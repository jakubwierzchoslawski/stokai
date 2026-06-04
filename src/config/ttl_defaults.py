"""Environment-variable overrides for per-data-type TTL values.

Usage:
    from config.ttl_defaults import get_ttl_registry

    registry = get_ttl_registry()

Each environment variable, when set, overrides the corresponding
DEFAULT_TTL_REGISTRY value for that data type. If the env var is not set,
the DEFAULT_TTL_REGISTRY value is used unchanged.

Supported env vars (all optional, value is seconds as integer):
    PRICE_BAR_TTL_SECONDS
    FUNDAMENTALS_TTL_SECONDS
    NEWS_EVENT_TTL_SECONDS
    MACRO_TTL_SECONDS

Immutable and event-driven types (PRICE_BAR_HISTORICAL, EVENT_EMBEDDING,
COMPANY_SCORE) are intentionally not overridable — their semantics are
defined by the data contract, not by configuration.

Cache key strategy
------------------
Data types in SHARED_DATA_TYPES use a global (non-user-scoped) cache key:
    "{data_type}:{entity_id}:{params_hash}"

This ensures that a price bar or fundamentals record fetched for user A is
served from the cache to users B through N — the flat-API-bill invariant from
Principle 2 (Local-First Data) depends on this property.

Data types NOT in SHARED_DATA_TYPES (e.g. portfolio, watchlist) use a
user-scoped key:
    "{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash}"
"""

from __future__ import annotations

import os

from ingestion.ttl_policy import (
    DEFAULT_TTL_REGISTRY,
    DataType,
    TTLPolicy,
)

# ---------------------------------------------------------------------------
# Shared data type registry
# ---------------------------------------------------------------------------

# Data types whose cache keys must NOT include user_id or tenant_id.
# These represent global market data: one fetch serves all users within the TTL window.
# If user_id or tenant_id is passed to CacheOrFetch._build_key() for any of these
# types, those parameters are silently ignored (with a DEBUG-level log warning).
SHARED_DATA_TYPES: frozenset[DataType] = frozenset({
    DataType.PRICE_BAR,
    DataType.PRICE_BAR_HISTORICAL,
    DataType.FUNDAMENTALS,
    DataType.MACRO,
    DataType.EVENT_EMBEDDING,
})


def _read_int_env(name: str) -> int | None:
    """Read an integer from an environment variable; return None if unset or invalid."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def get_ttl_registry() -> dict[DataType, TTLPolicy]:
    """Return the effective TTL registry, with env-var overrides applied.

    Returns a new dict — does not mutate DEFAULT_TTL_REGISTRY.
    """
    registry = dict(DEFAULT_TTL_REGISTRY)

    overridable: list[tuple[DataType, str]] = [
        (DataType.PRICE_BAR, "PRICE_BAR_TTL_SECONDS"),
        (DataType.FUNDAMENTALS, "FUNDAMENTALS_TTL_SECONDS"),
        (DataType.NEWS_EVENT, "NEWS_EVENT_TTL_SECONDS"),
        (DataType.MACRO, "MACRO_TTL_SECONDS"),
    ]

    for data_type, env_var in overridable:
        ttl = _read_int_env(env_var)
        if ttl is not None:
            base = registry[data_type]
            registry[data_type] = TTLPolicy(
                data_type=base.data_type,
                redis_ttl_seconds=ttl,
                pg_ttl_seconds=ttl,
                invalidation=base.invalidation,
            )

    return registry
