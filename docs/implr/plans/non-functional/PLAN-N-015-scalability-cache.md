---
plan_id: PLAN-N-015
slug: scalability-cache
title: Cache-Driven Sublinear API Cost Scalability
linked_requirement: REQ-N-015
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-032, reason: "Cache layer is the mechanism delivering this property; all cache-or-fetch infrastructure (RedisCacheLayer, CacheEntryRepository, CacheOrFetch base class, TTLPolicy registry) must exist before load tests can exercise and verify it" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-015 — Cache-Driven Sublinear API Cost Scalability

## Linked Requirement
**REQ-N-015** — Cache-Driven Sublinear API Cost Scalability
Status: approved | Jira:

## Objective
Verify and enforce the scalability property delivered by the cache-or-fetch mechanism (PLAN-F-032): that external API call volume grows sublinearly with user count. The plan introduces three complementary mechanisms:

1. **Global cache key strategy** for shared data types (price bars, fundamentals, macro, embeddings) — ensuring data fetched by user A is served from cache to users B through N without an additional external call.
2. **Per-request hit/miss telemetry** logged in structured JSON — making the cache hit rate observable at every layer so that deviations are detectable in production.
3. **Automated load tests** asserting the two core invariants from REQ-N-015: 100 sequential chart views produce exactly 1 external API call within one TTL window; and external API call growth is sublinear as concurrent user count scales from 1 to 10 to 100.

After this plan is complete, the system has demonstrated — via reproducible automated tests that run on every release — that the $100/month API budget holds at multi-user scale.

## Architecture Context

This plan operates entirely within **Layer 2 — Ingestion & Cache** (ARCHITECTURE §4) and the `ingestion` module (§5). It adds no new modules; it hardens and verifies the `src/ingestion/` infrastructure introduced by PLAN-F-032.

Key references:

- **Principle 2 — Local-First Data** (§2): monthly API bill is flat regardless of how many times the same data is queried. This plan proves that invariant holds.
- **Layer 2 — Cache-or-Fetch** (§4): the Redis → PostgreSQL → API cascade is the mechanism; this plan adds a telemetry wrapper around the cascade and runs concurrency load tests against it.
- **Decision D12** (§3): AI + infrastructure cost must remain under $100/month. Sublinear API call growth is a direct prerequisite for that budget to hold at any meaningful user count.
- **Section 12.6 — Cost Governance** (§12.6): cost must be monitored and enforced at runtime. Cache hit rate logging (TASK-002) is the per-request instrument that feeds this governance goal.
- **Section 12.4 — Observability** (§12.4): structured JSON logs with `request_id` propagation; every request logged with method, path, status, duration. Cache hit/miss events extend this standard with a `cache_tier` field.
- **Technology** (§13): Redis 7 hot cache; PostgreSQL 16 persistent cache; pytest + asyncio for tests; `fakeredis.aioredis` for unit-speed load simulations.

The `ingestion` module (`src/ingestion/`) is the only production code path touched. Test files live under `tests/`.

## Component Design

### New Components

```
tests/
  load/
    test_sublinear_api_calls.py      — load test: 100-view / 1-call invariant (AC-001)
    test_concurrent_user_scaling.py  — load test: 1/10/100 concurrent users (AC-002, AC-003)

src/ingestion/
  cache_telemetry.py                 — CacheTelemetry class; logs hit/miss/tier per request
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ingestion/cache_or_fetch.py` | Inject `CacheTelemetry`; emit hit/miss event after each tier lookup | All cache hits and misses become observable without coupling telemetry to business logic |
| `src/ingestion/__init__.py` | Export `CacheTelemetry` | Public surface consistency |
| `src/config/ttl_defaults.py` | Add `SHARED_DATA_TYPES` constant listing data types with global (non-user-scoped) cache keys | Documents which data types must never carry a user_id in their cache key |

### Interfaces and Contracts

```python
# src/ingestion/cache_telemetry.py

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("ingestion.cache")

class CacheTier(StrEnum):
    REDIS = "redis"
    POSTGRES = "postgres"
    PROVIDER = "provider"   # external API call

class CacheOutcome(StrEnum):
    HIT = "hit"
    MISS = "miss"

@dataclass(frozen=True)
class CacheEvent:
    cache_key: str
    data_type: str
    tier: CacheTier
    outcome: CacheOutcome
    request_id: str | None = None   # propagated from FastAPI middleware

class CacheTelemetry:
    """
    Single-responsibility: emit one structured log line per cache lookup.
    Injected into CacheOrFetch. No knowledge of Redis or PostgreSQL internals.
    Never raises — logging failures must not propagate to callers.
    """

    def record(self, event: CacheEvent) -> None:
        """
        Emits a structured JSON log entry at INFO level.
        Fields: cache_key, data_type, tier, outcome, request_id.
        Downstream log aggregators can GROUP BY tier, outcome to compute hit rates.
        """
        try:
            logger.info(
                "cache_lookup",
                extra={
                    "cache_key": event.cache_key,
                    "data_type": event.data_type,
                    "tier": event.tier,
                    "outcome": event.outcome,
                    "request_id": event.request_id,
                },
            )
        except Exception:
            pass  # telemetry must never break the request path
```

```python
# src/config/ttl_defaults.py  (addition)

from src.ingestion.ttl_policy import DataType

# Data types whose cache keys must NOT include user_id or tenant_id.
# Shared globally; one fetch serves all users within the TTL window.
SHARED_DATA_TYPES: frozenset[DataType] = frozenset({
    DataType.PRICE_BAR,
    DataType.PRICE_BAR_HISTORICAL,
    DataType.FUNDAMENTALS,
    DataType.MACRO,
    DataType.EVENT_EMBEDDING,
})
```

```python
# Cache key strategy contract (enforced by CacheOrFetch.cache_or_fetch)
#
# Shared data types (in SHARED_DATA_TYPES):
#   key = "{data_type}:{entity_id}:{params_hash}"
#   NO user_id or tenant_id in the key.
#   Rationale: user A's price bar fetch is served to user B from cache —
#              the flat-API-bill invariant depends on this.
#
# User-specific data types (portfolio, watchlist — not in SHARED_DATA_TYPES):
#   key = "{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash}"
#   Each user has their own cache entry.
#
# This contract is documented here; enforcement is in CacheOrFetch._build_key().
```

## Implementation Tasks

### TASK-001: Global cache key strategy — enforce shared key format for shared data types · S/no-TDD · src/ingestion/cache_or_fetch.py, src/config/ttl_defaults.py, src/ingestion/__init__.py

Audit the `CacheOrFetch._build_key()` method (from PLAN-F-032 TASK-004). Confirm that for all data types in `SHARED_DATA_TYPES`, the key does not include `user_id` or `tenant_id`. If `_build_key()` currently accepts optional `user_id` and `tenant_id` parameters, enforce that they are ignored (with a `DEBUG`-level log warning) for shared types. Add `SHARED_DATA_TYPES` to `src/config/ttl_defaults.py` as a `frozenset[DataType]`. Export from `src/ingestion/__init__.py`.

Document the two-tier key format in a module-level docstring in `cache_or_fetch.py`:
- Shared: `"{data_type}:{entity_id}:{params_hash}"` — no user scope
- User-specific: `"{data_type}:{tenant_id}:{user_id}:{entity_id}:{params_hash}"`

This task is the design anchor for AC-001 and AC-002: without global keys for price bars and fundamentals, different users would receive separate cache misses for identical data.

**AC covered**: AC-001 (price chart TTL window shared across users), AC-002 (fundamentals TTL window shared across users)

---

### TASK-002: CacheTelemetry — per-request hit/miss structured logging · S/no-TDD · src/ingestion/cache_telemetry.py, src/ingestion/cache_or_fetch.py, src/ingestion/__init__.py

Implement `CacheTelemetry` per the interface contract above. Inject it into `CacheOrFetch.__init__` as an optional parameter (default: `NullCacheTelemetry` that silently no-ops, keeping the hot path zero-overhead when telemetry is disabled in tests that do not need it).

Instrument `CacheOrFetch.cache_or_fetch` to call `telemetry.record()` at each tier lookup:
- After Redis GET: record `(tier=REDIS, outcome=HIT)` on success or `(tier=REDIS, outcome=MISS)` on None/failure.
- After PostgreSQL GET: record `(tier=POSTGRES, outcome=HIT)` or `(tier=POSTGRES, outcome=MISS)`.
- After `fetch_fn` call: record `(tier=PROVIDER, outcome=MISS)` — the external API was invoked.

The three `CacheTier.PROVIDER` log lines in a load test run are the observable measure of AC-001's "exactly 1 external API call" assertion.

Export `CacheTelemetry`, `CacheTier`, `CacheOutcome`, `CacheEvent` from `src/ingestion/__init__.py`.

**AC covered**: AC-001 (hit rate measurable per request), AC-002 (hit rate measurable per request), AC-003 (hit rate measurable; ratio of PROVIDER events to total requests)

---

### TASK-003: Load test — 100 sequential views produce exactly 1 external API call · M/TDD · tests/load/test_sublinear_api_calls.py

**Tests to write first (TDD)**:
- `test_100_sequential_price_chart_requests_produce_1_external_call` — use `fakeredis.aioredis` for Redis; `AsyncMock` for PG session; a `MagicMock` `fetch_fn` as the stand-in external API. Invoke `cache_or_fetch` 100 times with identical `(data_type=PRICE_BAR, entity_id="AAPL", params={})`. Assert `fetch_fn.call_count == 1`. Assert `CacheTelemetry` recorded exactly 1 `(PROVIDER, MISS)` event and 99 `(REDIS, HIT)` events.
- `test_100_sequential_requests_different_entity_produce_100_external_calls` — sanity inverse: 100 different `entity_id` values → 100 external calls. Confirms the test harness is not falsely passing due to a mock misconfiguration.
- `test_99_requests_after_ttl_expiry_each_produce_1_external_call` — simulate TTL expiry by calling `fakeredis.expire(key, 0)` between iteration 1 and iteration 2. Assert `fetch_fn.call_count == 2` (once for the initial miss, once after expiry). Validates that TTL enforcement does not silently break the "exactly 1 call" guarantee.
- `test_fundamentals_100_views_produce_1_external_call` — same pattern for `DataType.FUNDAMENTALS` with 86400s TTL. Assert `fetch_fn.call_count == 1`.

Use `pytest-asyncio`. The test file must import from `src/ingestion` only — no FastAPI, no DB connections. The load is simulated at the `CacheOrFetch` layer, not at the HTTP layer, keeping the test fast (milliseconds, not seconds).

**AC covered**: AC-001 (price chart 100 views / 1 call), AC-002 (fundamentals 10 users / 1 call — subsumed by 100-view variant)

---

### TASK-004: Load test — sublinear API call growth with 1, 10, 100 concurrent users · M/TDD · tests/load/test_concurrent_user_scaling.py

**Tests to write first (TDD)**:
- `test_1_user_50_screener_requests_external_call_ratio` — 1 simulated user, 50 `asyncio.gather` requests for the same screener company set. Assert `fetch_fn.call_count / 50 < 0.05` (cache hit rate ≥ 95%). Screener data uses `PRICE_BAR` and `FUNDAMENTALS` types, both in `SHARED_DATA_TYPES`.
- `test_10_concurrent_users_same_company_data_ratio` — 10 `asyncio.Task` coroutines, each making 5 requests for the same company set. Total: 50 requests. Assert `fetch_fn.call_count <= 2` (at most 2 real calls: one per data type that cold-misses before the cache warms, then all subsequent from cache). Assert ratio `fetch_fn.call_count / 50 < 0.05`.
- `test_100_concurrent_users_same_company_data_ratio` — 100 tasks, each making 1 request. Assert `fetch_fn.call_count / 100 < 0.05`. This is the core AC-003 assertion.
- `test_api_call_growth_is_sublinear_across_scales` — run the 1/10/100 user scenarios in sequence with a fresh cache per scenario. Capture `fetch_fn.call_count` for each. Assert that the count at 10 users is less than 10× the count at 1 user, and at 100 users less than 10× the count at 10 users (sublinear: each order-of-magnitude user increase does not produce an order-of-magnitude API call increase).
- `test_thundering_herd_single_key_concurrent_miss` — 20 concurrent coroutines all miss the same key simultaneously (empty cache). Assert `fetch_fn.call_count >= 1` (at least one call), and `fetch_fn.call_count <= 3` (near-miss concurrency window; not 20 calls). Documents the known advisory-lock limitation from PLAN-F-032 Risks; asserts the practical upper bound.

All tests use `fakeredis.aioredis` and `AsyncMock` for the PG layer. `asyncio.gather` provides true concurrent coroutine scheduling. No real threads, no real HTTP.

**AC covered**: AC-003 (50 concurrent users / <0.05 ratio), AC-001 and AC-002 (subsumed by the broader scaling assertion)

---

### TASK-005: Cache hit rate admin endpoint · S/no-TDD · src/api/routers/admin/cache_stats.py, tests/unit/api/test_cache_stats.py

Add a read-only admin endpoint `GET /api/v1/admin/cache/stats` that returns the aggregate cache hit rate from the structured logs (or from Redis counters if available). The endpoint is gated by `role == "admin"` (D2).

The simplest correct implementation: `CacheTelemetry.record()` increments two Redis counters — `cache_stats:hits:{tier}` and `cache_stats:misses:{tier}` — using `INCR` on every call. The admin endpoint reads these counters and returns:

```json
{
  "data": {
    "redis": { "hits": 9901, "misses": 99, "hit_rate_pct": 99.0 },
    "postgres": { "hits": 54, "misses": 45, "hit_rate_pct": 54.5 },
    "provider_calls_total": 45
  },
  "meta": { "since": "service_start" },
  "error": null
}
```

This satisfies the "measurable" requirement from REQ-N-015 §NFR-Specific Fields without requiring a log-aggregation stack in MVP. The counters reset on service restart; they are operational indicators, not durable audit data.

Test: mock Redis counter reads; assert response shape; assert 403 for non-admin callers.

**AC covered**: AC-001 (observable hit rate confirms 99/100 hits), AC-002 (observable hit rate confirms shared data served from cache), AC-003 (ratio metric directly computable from the response)

## Acceptance Criteria Coverage

- AC-001: Given 100 sequential requests for the same company's price chart within one 15-minute TTL window, external price API called exactly once → TASK-001, TASK-003
- AC-002: Given 10 users each requesting the same company's fundamentals within a 24-hour TTL window, external fundamentals API called exactly once → TASK-001, TASK-003, TASK-004
- AC-003: Given 50 concurrent users accessing the screener with different sort/filter combinations but same underlying company data, external API call ratio < 0.05 → TASK-002, TASK-004, TASK-005

## Acceptance Notes

The load tests in TASK-003 and TASK-004 simulate concurrency at the `CacheOrFetch` layer using `asyncio.gather` and `fakeredis`. They do not require a running Redis or PostgreSQL instance and execute in milliseconds. A full integration load test against a live Redis instance is recommended as a release-gate step for production readiness verification but is not a CI gate in this plan.

The thundering-herd test in TASK-004 (`test_thundering_herd_single_key_concurrent_miss`) documents an accepted limitation: up to ~3 concurrent first-fetches may occur for the same key under extreme cold-start concurrency. This does not violate the 95% hit rate target in steady state (after the first TTL window). If this becomes a measured problem, the solution is a Redis Lua atomic lock as noted in PLAN-F-032 Risks.

## Risks and Notes

- **Counter atomicity in TASK-005**: `INCR` on Redis is atomic per call, but `CacheTelemetry.record()` must not block the request path. Use fire-and-forget `asyncio.create_task(redis.incr(...))` or accept occasional missed increments under high concurrency. The stats endpoint is operational, not financial — a small percentage of missed increments is acceptable.
- **Shared key safety for multi-tenancy**: `SHARED_DATA_TYPES` keys have no `tenant_id`. This is correct for global market data (price bars, fundamentals, macro). The architecture's multi-tenant activation (ARCHITECTURE §12.3) defers full tenant isolation. When activated, the key strategy must be revisited for any data type that becomes tenant-scoped. This plan documents the current intentional design; future migration is a known forward dependency.
- **`fakeredis` concurrency model**: `fakeredis.aioredis` is single-threaded and does not model true Redis network latency. The concurrency tests in TASK-004 validate the correctness of the cache key sharing logic, not network-level race conditions. Production concurrency behaviour should be validated in a staging environment with a real Redis instance before the first multi-user deployment.
- **Test file location**: `tests/load/` is a new directory. The `pytest.ini` or `pyproject.toml` test configuration must include `tests/load/` in the `testpaths`. The executor should add this if it is not already present.
