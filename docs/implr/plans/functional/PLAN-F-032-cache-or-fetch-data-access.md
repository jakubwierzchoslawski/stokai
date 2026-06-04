---
plan_id: PLAN-F-032
slug: cache-or-fetch-data-access
title: Cache-or-Fetch Data Access Pattern
linked_requirement: REQ-F-032
type: functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
  - { id: REQ-N-011, reason: "TTL enforcement is the primary freshness guarantee for every data type; compliance tested in TASK-005" }
  - { id: REQ-N-015, reason: "Flat API bill at scale relies entirely on this cache layer preventing repeat external calls; validated via hit-path unit tests in TASK-005" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-032 — Cache-or-Fetch Data Access Pattern

## Linked Requirement
**REQ-F-032** — Cache-or-Fetch Data Access Pattern
Status: approved | Jira:

## Objective
Build the three-tier data access infrastructure that sits between every provider adapter and the rest of the application. The plan introduces: a `CacheOrFetch` protocol (Python abstract base) that any provider adapter wraps; a Redis hot-cache layer (TTL-enforced); a PostgreSQL persistent-cache layer (via the `CacheEntryRepository`); a per-data-type `TTLPolicy` configuration registry; a Redis-backed per-source rate limiter; and event-driven cache invalidation for computed scores. After this plan is complete, every downstream module — ingestion, scoring, agents, tools — calls `cache_or_fetch(key, fetch_fn)` and the machinery handles all three tiers automatically, ensuring historical data and event embeddings are fetched exactly once in the system's lifetime and that viewing the same price chart one hundred times incurs zero additional external API calls.

## Architecture Context
This plan exclusively implements **Layer 2 — Ingestion & Cache** (ARCHITECTURE §4) and the `ingestion` module (§5). It touches no business logic in Layer 4 (scoring/events/ai). All external-API access lives in the `data_providers` module (§5 Principle 1); this plan only wraps those adapters with a caching decorator — it does not replace them.

Key architecture references:
- **Principle 2 — Local-First Data** (§2): Redis → PostgreSQL → API on miss; historical + embedding data at infinite TTL.
- **Layer 2 components** (§4): Provider Adapters, Cache-or-Fetch, Rate Limiter, Ingestion Scheduler.
- **Decision D1** (§3): `source_config` table drives per-source TTL and credentials at runtime; no code change needed.
- **Decision D3** (§3): Credentials resolved at runtime from `source_config.credentials_ref`; secrets never in code.
- **Technology** (§13): Redis 7 (hot cache + Celery broker dual role), PostgreSQL 16 / SQLAlchemy 2.0 async, Pydantic v2.

New module path: `src/ingestion/` — all new files are placed here. The `data_providers` module is referenced but not modified by this plan.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-011 | Per-data-type freshness guarantee; stale data must not be returned after TTL expiry | `TTLPolicy` table with `redis_ttl_seconds` and `pg_ttl_seconds` per data type; Redis keys set with `EX`; PostgreSQL rows filtered by `expires_at`; tested in TASK-005 |
| REQ-N-015 | Flat monthly API bill regardless of query frequency; cache hit rate must make repeated queries cost-free | Redis and PostgreSQL hit paths short-circuit before any provider call; TASK-005 asserts zero external calls on cache-hit paths; immutable-TTL types (historical, embeddings) tested for permanent persistence |

## Component Design

### New Components
```
Module: ingestion  (src/ingestion/)
  ├── cache_or_fetch.py       — CacheOrFetch abstract base class + decorator factory
  ├── ttl_policy.py           — TTLPolicy dataclass; DataType enum; TTL registry loader
  ├── redis_cache.py          — RedisCacheLayer (hot cache; GET/SET/DELETE; TTL-aware)
  ├── pg_cache_repository.py  — CacheEntryRepository (SQLAlchemy 2.0 async)
  ├── rate_limiter.py         — PerSourceRateLimiter (Redis sliding-window counters)
  ├── invalidation.py         — ScoreCacheInvalidator (event-driven; no time-based)
  ├── price_mode_selector.py  — PriceFreshnessMode resolver from source_config at runtime
  └── __init__.py             — public surface: cache_or_fetch decorator, TTL registry

DB migration:
  alembic/versions/XXXX_add_cache_entry_table.py
    cache_entry (cache_key PK, data_type, entity_id, params_hash,
                 value BYTEA, fetched_at TIMESTAMPTZ, expires_at TIMESTAMPTZ)
    Index: (data_type, entity_id, expires_at)

Config:
  src/config/ttl_defaults.py  — default TTLPolicy values per DataType (env-overridable)
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/config/settings.py` | Add `REDIS_URL`, `PRICE_FRESHNESS_MODE` env vars | Cache layer needs Redis connection; price mode is config-driven (AC-005) |
| `src/storage/__init__.py` | Export `CacheEntryRepository` | Storage module owns all repository implementations per architecture §5 |

### Interfaces and Contracts

```python
# src/ingestion/ttl_policy.py

from enum import StrEnum
from dataclasses import dataclass

class DataType(StrEnum):
    PRICE_BAR = "price_bar"
    PRICE_BAR_HISTORICAL = "price_bar_historical"  # past close — immutable
    FUNDAMENTALS = "fundamentals"
    NEWS_EVENT = "news_event"
    MACRO = "macro"
    EVENT_EMBEDDING = "event_embedding"             # immutable
    COMPANY_SCORE = "company_score"                 # event-driven invalidation only

@dataclass(frozen=True)
class TTLPolicy:
    data_type: DataType
    redis_ttl_seconds: int | None   # None = no expiry (infinite)
    pg_ttl_seconds: int | None      # None = no expiry (infinite)
    invalidation: str               # "time_based" | "event_driven" | "immutable"

# Default registry (overridable via source_config table at runtime)
DEFAULT_TTL_REGISTRY: dict[DataType, TTLPolicy] = {
    DataType.PRICE_BAR:             TTLPolicy(DataType.PRICE_BAR,            900,  900,  "time_based"),
    DataType.PRICE_BAR_HISTORICAL:  TTLPolicy(DataType.PRICE_BAR_HISTORICAL,  None, None, "immutable"),
    DataType.FUNDAMENTALS:          TTLPolicy(DataType.FUNDAMENTALS,          86400, 86400, "time_based"),
    DataType.NEWS_EVENT:            TTLPolicy(DataType.NEWS_EVENT,            3600, 3600,  "time_based"),
    DataType.MACRO:                 TTLPolicy(DataType.MACRO,                 86400, 86400, "time_based"),
    DataType.EVENT_EMBEDDING:       TTLPolicy(DataType.EVENT_EMBEDDING,       None, None, "immutable"),
    DataType.COMPANY_SCORE:         TTLPolicy(DataType.COMPANY_SCORE,         None, None, "event_driven"),
}
```

```python
# src/ingestion/cache_or_fetch.py

from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable
from typing import Any, TypeVar

T = TypeVar("T")

class CacheOrFetch(ABC):
    """
    Abstract base. Subclasses supply _serialize / _deserialize.
    The public entry point is cache_or_fetch(key, data_type, fetch_fn).
    No business logic lives here — only the three-tier cascade.
    """

    @abstractmethod
    async def _redis_get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def _redis_set(self, key: str, value: bytes, ttl_seconds: int | None) -> None: ...

    @abstractmethod
    async def _pg_get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def _pg_set(self, key: str, data_type: str, value: bytes, ttl_seconds: int | None) -> None: ...

    async def cache_or_fetch(
        self,
        key: str,
        data_type: DataType,
        fetch_fn: Callable[[], Awaitable[T]],
    ) -> T:
        """
        1. Redis GET → hit → deserialize → return
        2. Redis miss → PostgreSQL SELECT → hit → write-back to Redis → return
        3. PostgreSQL miss → call fetch_fn → store both layers → return
        """
        ...
```

```python
# src/ingestion/pg_cache_repository.py

from sqlalchemy.ext.asyncio import AsyncSession

class CacheEntryRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def get(self, cache_key: str) -> bytes | None:
        """Returns raw bytes or None if miss or expired."""

    async def set(
        self,
        cache_key: str,
        data_type: str,
        value: bytes,
        ttl_seconds: int | None,
    ) -> None:
        """Upsert. Sets expires_at = now() + ttl_seconds; None → NULL (infinite)."""

    async def delete(self, cache_key: str) -> None:
        """Hard delete for event-driven invalidation."""

    async def delete_by_prefix(self, prefix: str) -> int:
        """Bulk invalidation by key prefix. Returns count deleted."""
```

```python
# src/ingestion/rate_limiter.py

class PerSourceRateLimiter:
    """
    Sliding-window counter in Redis. One key per (source_id, window_start_minute).
    Raises RateLimitExceeded if the configured window limit is reached.
    Does NOT block — caller decides whether to delay or skip.
    """

    async def check_and_increment(self, source_id: str) -> None:
        """Raises RateLimitExceeded if limit reached; else increments counter."""

    async def remaining(self, source_id: str) -> int:
        """Returns calls remaining in current window."""
```

```python
# src/ingestion/invalidation.py

class ScoreCacheInvalidator:
    """
    Event-driven invalidation only — no TTL on company_score cache entries.
    Called by the scoring engine when a geo_event triggers score recomputation.
    """

    async def invalidate_company_score(self, company_id: str) -> None:
        """Delete Redis key and PostgreSQL row for this company's score."""

    async def invalidate_scores_for_event(self, event_id: str, company_ids: list[str]) -> None:
        """Bulk invalidation for all companies exposed to a given event."""
```

```python
# src/ingestion/price_mode_selector.py

class PriceFreshnessMode:
    DELAYED = "delayed"   # 15-min TTL; default
    REALTIME = "realtime" # 5-second TTL

class PriceModeSelector:
    """
    Reads PRICE_FRESHNESS_MODE from source_config (admin feature flag) at call time.
    No restart required. Returns the TTLPolicy appropriate for the current mode.
    """
    async def get_price_ttl(self) -> int:
        """Returns 900 (delayed) or 5 (real-time) from source_config without code change."""
```

## Implementation Tasks

### TASK-001: TTLPolicy dataclass, DataType enum, and default TTL registry · S/no-TDD · src/ingestion/ttl_policy.py, src/ingestion/__init__.py, src/config/ttl_defaults.py

Define the `DataType` string enum and the `TTLPolicy` frozen dataclass as the authoritative type contracts for the entire caching subsystem. Populate `DEFAULT_TTL_REGISTRY` with the exact values from REQ-F-032 — PRICE_BAR 900s, PRICE_BAR_HISTORICAL infinite, FUNDAMENTALS 86400s, NEWS_EVENT 3600s, MACRO 86400s, EVENT_EMBEDDING infinite, COMPANY_SCORE event-driven (None TTL). Export from `src/ingestion/__init__.py`.

`src/config/ttl_defaults.py` reads from environment variables so that TTLs are overridable in test environments without a DB row.

**AC covered**: AC-001 (TTL basis for price freshness), AC-002 (infinite TTL for historical price), AC-003 (infinite TTL for embeddings), AC-004 (event-driven policy for scores)

---

### TASK-002: RedisCacheLayer — hot cache with TTL-aware GET/SET/DELETE · S/no-TDD · src/ingestion/redis_cache.py

Implement `RedisCacheLayer` using the `redis.asyncio` client. Constructor accepts `redis.asyncio.Redis` (injected, never `new`). Implement:
- `get(key) -> bytes | None` — returns `None` on miss or if Redis is unavailable (graceful degradation; log warning, do not raise)
- `set(key, value, ttl_seconds)` — uses `SET key value EX ttl_seconds`; if `ttl_seconds` is `None`, use `SET key value` with no expiry
- `delete(key) -> None`
- `delete_by_pattern(pattern) -> int` — uses `SCAN` + `DEL`; returns count

No business logic. No knowledge of `DataType`. Serialization is the caller's responsibility.

**AC covered**: AC-001 (Redis hit path), AC-002 (no-expiry SET for historical), AC-003 (no-expiry SET for embeddings)

---

### TASK-003: CacheEntryRepository — PostgreSQL persistent cache layer · S/no-TDD · src/ingestion/pg_cache_repository.py, alembic/versions/XXXX_add_cache_entry_table.py

Create the `cache_entry` table via an Alembic migration:

```sql
CREATE TABLE cache_entry (
    cache_key     TEXT PRIMARY KEY,
    data_type     TEXT NOT NULL,
    entity_id     TEXT,
    params_hash   TEXT,
    value         BYTEA NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ          -- NULL = infinite
);
CREATE INDEX ix_cache_entry_data_type_entity ON cache_entry (data_type, entity_id, expires_at);
```

Implement `CacheEntryRepository` (SQLAlchemy 2.0 async, injected `AsyncSession`):
- `get(cache_key)` — `WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > now())`; returns raw `bytes` or `None`
- `set(cache_key, data_type, value, ttl_seconds)` — upsert via `INSERT ... ON CONFLICT DO UPDATE`; `expires_at = now() + interval '? seconds'` when `ttl_seconds` is not None, else `NULL`
- `delete(cache_key)` — hard delete for invalidation
- `delete_by_prefix(prefix)` — `WHERE cache_key LIKE ?||'%'`; returns count

Parameterised queries only. No raw SQL interpolation.

**AC covered**: AC-001 (PostgreSQL hit path), AC-002 (NULL expires_at for historical), AC-003 (NULL expires_at for embeddings)

---

### TASK-004: CacheOrFetch base class and cache_key builder · M/TDD · src/ingestion/cache_or_fetch.py

**Tests to write first (TDD)**:
- `test_redis_hit_returns_value_without_pg_or_api_call` — mock Redis returns bytes; assert PostgreSQL and fetch_fn are never called
- `test_redis_miss_pg_hit_writes_back_to_redis_and_returns_value` — mock Redis returns None; mock PG returns bytes; assert Redis.set is called with correct TTL; fetch_fn is not called
- `test_redis_miss_pg_miss_calls_fetch_fn_stores_both_layers` — both mocks return None; fetch_fn returns value; assert both Redis.set and PG.set called; value returned equals fetch_fn result
- `test_immutable_data_type_stored_with_no_expiry_in_both_layers` — PRICE_BAR_HISTORICAL data type; assert `ttl_seconds=None` passed to both Redis and PG set methods
- `test_event_driven_data_type_stored_with_no_expiry` — COMPANY_SCORE; same assertion as above

Implement `CacheOrFetch` abstract base class per the interface contract above. The `cache_or_fetch` method generates a deterministic `cache_key` as `"{data_type}:{entity_id}:{sha256(sorted(params.items()))[:8]}"`. Resolve the `TTLPolicy` from the injected registry. Serialize with `msgpack` (compact binary; faster than JSON; avoids float precision issues in prices). On any Redis failure, log a warning and fall through to PostgreSQL; on any PostgreSQL failure, log an error and fall through to the API call — the system degrades gracefully but always returns data.

**AC covered**: AC-001 (full three-tier cascade), AC-002 (immutable historical), AC-003 (immutable embeddings), AC-004 (no-TTL for scores)

---

### TASK-005: Unit tests for all cache hit/miss paths and TTL enforcement · M/TDD · tests/unit/ingestion/test_cache_or_fetch.py, tests/unit/ingestion/test_ttl_policy.py, tests/unit/ingestion/test_redis_cache.py, tests/unit/ingestion/test_pg_cache_repository.py

**Tests to write first (TDD)**:
- `test_price_bar_ttl_is_900_seconds` — assert DEFAULT_TTL_REGISTRY[PRICE_BAR].redis_ttl_seconds == 900
- `test_historical_price_bar_ttl_is_none` — assert both redis and pg TTLs are None
- `test_event_embedding_ttl_is_none` — assert both redis and pg TTLs are None
- `test_company_score_invalidation_type_is_event_driven` — assert policy.invalidation == "event_driven"
- `test_redis_set_with_none_ttl_does_not_set_expiry` — assert `redis.set` called without `ex` parameter
- `test_redis_set_with_ttl_uses_ex_parameter` — assert `redis.set` called with `ex=900`
- `test_pg_get_excludes_expired_rows` — verify the WHERE clause excludes `expires_at < now()`
- `test_external_api_not_called_on_redis_hit` — zero-additional-call invariant (REQ-F-032 key invariant)
- `test_external_api_not_called_on_pg_hit` — same invariant for warm storage tier
- `test_100_identical_queries_result_in_1_external_api_call` — integration-style unit test; mock fetch_fn call counter; assert called exactly once after 100 `cache_or_fetch` invocations with the same key

All tests use `pytest-asyncio`. Mock Redis via `fakeredis.aioredis`. Mock PostgreSQL session via `unittest.mock.AsyncMock`.

**AC covered**: AC-001 (zero-call invariant), AC-002 (infinite TTL for historical), AC-003 (infinite TTL for embeddings), AC-004 (event-driven policy)

---

### TASK-006: PerSourceRateLimiter — Redis sliding-window counter · S/no-TDD · src/ingestion/rate_limiter.py

Implement `PerSourceRateLimiter` with injected `redis.asyncio.Redis`. Use a 60-second sliding window keyed as `"rate_limit:{source_id}:{unix_minute}"`. Each call increments the counter and sets a 120-second expiry (two windows, safe cleanup). If counter exceeds the source's `requests_per_minute` (loaded from `source_config` table via an injected callable), raise `RateLimitExceeded(source_id, limit, current_count)`. The `RateLimitExceeded` exception carries enough context for callers to implement exponential back-off without accessing Redis again.

**AC covered**: enables AC-001 (prevents redundant API calls caused by thundering-herd concurrency)

---

### TASK-007: ScoreCacheInvalidator — event-driven invalidation for computed scores · M/TDD · src/ingestion/invalidation.py

**Tests to write first (TDD)**:
- `test_invalidate_company_score_deletes_redis_and_pg_entries` — assert Redis.delete and PGRepo.delete both called with the correct cache key
- `test_invalidate_scores_for_event_deletes_all_exposed_companies` — given 3 company_ids, assert 3 Redis.delete and 3 PGRepo.delete calls
- `test_score_is_not_invalidated_by_time` — assert no TTL is set when a company_score is stored; invalidation happens only via explicit `invalidate_company_score` call
- `test_score_retains_value_between_events` — store score via cache layer; no event fires; assert same value returned on second read without hitting fetch_fn

Implement `ScoreCacheInvalidator` with injected `RedisCacheLayer` and `CacheEntryRepository`. The key format for a score is `"company_score:{company_id}:latest"`. `invalidate_scores_for_event` calls `invalidate_company_score` for each company_id in the exposed list — no bulk Redis operations needed for MVP scale.

**AC covered**: AC-004 (event-driven invalidation, score retained between events)

---

### TASK-008: PriceModeSelector — config-driven price freshness switch · S/no-TDD · src/ingestion/price_mode_selector.py

Implement `PriceModeSelector` with an injected async `get_source_config` callable (returns a dict of config values for a given `source_id`). On each call to `get_price_ttl()`, read the `price_freshness_mode` key from the `source_config` row for the active price provider. Return `900` if `"delayed"` (default), `5` if `"realtime"`. No cached value — always reads current config so that an admin panel toggle takes effect on the next request without a restart. The `CacheOrFetch` decorator for price bar data calls `PriceModeSelector.get_price_ttl()` rather than using the static registry TTL.

This is the mechanism that satisfies AC-005: no code change, no restart — only a `source_config` row update from the admin panel.

**AC covered**: AC-005 (price freshness mode switch via config only)

---

### TASK-009: Ingestion module public surface and integration smoke test · S/no-TDD · src/ingestion/__init__.py, tests/integration/ingestion/test_cache_integration.py

Wire the public surface of `src/ingestion/__init__.py`:
- Export: `CacheOrFetch`, `DataType`, `TTLPolicy`, `DEFAULT_TTL_REGISTRY`, `RedisCacheLayer`, `CacheEntryRepository`, `PerSourceRateLimiter`, `ScoreCacheInvalidator`, `PriceModeSelector`

Write one integration smoke test in `tests/integration/ingestion/test_cache_integration.py` using `fakeredis.aioredis` for Redis and an in-memory SQLite engine (via SQLAlchemy async) for the PG layer. The test exercises the full three-tier cascade end-to-end:
1. First call: Redis miss → PG miss → fetch_fn called → both layers populated
2. Second call: same key → Redis hit → fetch_fn NOT called
3. Force-expire the Redis key → third call: PG hit → Redis refreshed → fetch_fn NOT called
4. Invalidate via `ScoreCacheInvalidator` → fourth call: fetch_fn called again

This smoke test documents the expected runtime behaviour for the dev-executor of downstream plans (REQ-F-001 ingestion, REQ-F-017 scoring, etc.).

**AC covered**: AC-001, AC-002, AC-003, AC-004 (end-to-end cascade validation)

## Acceptance Criteria Coverage

- AC-001: Given a price bar request within TTL — TASK-004, TASK-005, TASK-009
- AC-002: Given a historical price bar previously fetched — TASK-001, TASK-003, TASK-004, TASK-005, TASK-009
- AC-003: Given an event embedding stored — TASK-001, TASK-003, TASK-004, TASK-005, TASK-009
- AC-004: Given a computed company_score — TASK-001, TASK-007, TASK-005, TASK-009
- AC-005: Given price freshness mode changed in admin panel — TASK-008

## Risks and Notes

- **msgpack dependency**: `msgpack` is not in the base stack; it must be added to `pyproject.toml`. If any downstream consumer already serialises with JSON, a migration step or dual-format read is needed. The executor should add `msgpack>=1.0` to the project dependencies.
- **Graceful Redis degradation**: `RedisCacheLayer` must not raise on Redis connection failure — it returns `None` and the request falls through to PostgreSQL. If PostgreSQL also fails, the fetch_fn is called. This means Redis becoming unavailable causes a latency spike but never a service outage.
- **`fakeredis` for tests**: Use `fakeredis[aioredis]` package in test dependencies for fast, in-process Redis simulation. Do not start a real Redis in unit tests.
- **SQLite for integration tests**: SQLite does not support `TIMESTAMPTZ`; use `DATETIME` in the SQLAlchemy model when running under SQLite (dialect-specific type). The production model uses `TIMESTAMPTZ` on PostgreSQL. Use `sa.DateTime(timezone=True)` — SQLAlchemy handles the dialect difference.
- **Key namespace collision**: The `cache_key` format `"{data_type}:{entity_id}:{params_hash}"` must be unique across data types. Callers must pass `entity_id` (e.g., `company_id`, `event_id`) and not rely on positional uniqueness alone.
- **Price mode selector reads source_config on every call**: This is intentional for admin-panel responsiveness (AC-005). At the ingestion scheduler's poll frequency (15 minutes for GDELT, 5s for real-time prices), the extra DB read is negligible. If profiling shows it is hot, a 30-second in-memory TTL on the mode value is an acceptable optimisation — but do not add it until measured.
- **Rate limiter is advisory, not a lock**: Two concurrent coroutines can both pass the rate limit check before either increments. Under the expected load of 1–3 concurrent ingestion workers this is acceptable. A Redis Lua atomic increment resolves this if needed at scale.
