"""src/ingestion — Cache-or-Fetch data access layer.

Public surface: import from here, not from sub-modules directly.

Exports:
    CacheOrFetch          — Abstract three-tier cache cascade base class.
    DataCacheOrFetch      — Concrete implementation (inject RedisCacheLayer + CacheEntryRepository).
    DataType              — Enum of all cacheable data types.
    TTLPolicy             — Per-data-type TTL configuration.
    DEFAULT_TTL_REGISTRY  — Mapping of DataType -> TTLPolicy with REQ-F-032 values.
    RedisCacheLayer       — Redis hot-cache wrapper (GET/SET/DELETE/SCAN).
    CacheEntryRepository  — PostgreSQL persistent-cache repository.
    PerSourceRateLimiter  — Redis sliding-window rate limiter.
    RateLimitExceeded     — Exception raised when rate limit is exceeded.
    ScoreCacheInvalidator — Event-driven cache invalidator for company scores.
    PriceModeSelector     — Config-driven price freshness TTL resolver.
    PriceFreshnessMode    — Constants for price freshness mode values.
    build_cache_key       — Helper to build deterministic cache keys.
    TTLValidator          — Write-time TTL enforcement; raises MissingTTLError.
    MissingTTLError       — Raised when non-immutable data written without TTL.
    CacheTelemetry        — Per-request hit/miss structured logging.
    NullCacheTelemetry    — No-op telemetry for tests and disabled paths.
    CacheTier             — Enum of cache tiers (REDIS, POSTGRES, PROVIDER).
    CacheOutcome          — Enum of cache outcomes (HIT, MISS).
    CacheEvent            — Immutable record of a single cache lookup event.
    SHARED_DATA_TYPES     — frozenset of DataType values with global (non-user-scoped) keys.
"""

from ingestion.cache_or_fetch import (
    CacheOrFetch,
    DataCacheOrFetch,
    build_cache_key,
)
from ingestion.cache_telemetry import (
    CacheEvent,
    CacheOutcome,
    CacheTelemetry,
    CacheTier,
    NullCacheTelemetry,
)
from ingestion.invalidation import ScoreCacheInvalidator
from ingestion.pg_cache_repository import CacheEntryRepository
from ingestion.price_mode_selector import PriceFreshnessMode, PriceModeSelector
from ingestion.rate_limiter import PerSourceRateLimiter, RateLimitExceeded
from ingestion.redis_cache import RedisCacheLayer
from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType, TTLPolicy
from ingestion.ttl_validator import MissingTTLError, TTLValidator

# Re-export SHARED_DATA_TYPES from config to keep ingestion as the single import surface.
from config.ttl_defaults import SHARED_DATA_TYPES

__all__ = [
    "CacheOrFetch",
    "DataCacheOrFetch",
    "DataType",
    "TTLPolicy",
    "DEFAULT_TTL_REGISTRY",
    "RedisCacheLayer",
    "CacheEntryRepository",
    "PerSourceRateLimiter",
    "RateLimitExceeded",
    "ScoreCacheInvalidator",
    "PriceModeSelector",
    "PriceFreshnessMode",
    "build_cache_key",
    "TTLValidator",
    "MissingTTLError",
    "CacheTelemetry",
    "NullCacheTelemetry",
    "CacheTier",
    "CacheOutcome",
    "CacheEvent",
    "SHARED_DATA_TYPES",
]
