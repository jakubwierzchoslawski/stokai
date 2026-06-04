---
plan_id: PLAN-N-011
slug: data-freshness
title: Data Freshness and TTL Enforcement
linked_requirement: REQ-N-011
type: non-functional
status: done
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs: []
dependencies:
  - { id: PLAN-F-032, reason: "TTL enforcement is part of the cache-or-fetch layer; Redis and PostgreSQL TTL mechanics are implemented there" }
  - { id: PLAN-F-015, reason: "Semantic fact 6-month confidence decay is implemented in SemanticHygieneService; this plan adds NFR-level verification on top of it" }
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-011 — Data Freshness and TTL Enforcement

## Linked Requirement
**REQ-N-011** — Data Freshness and TTL Enforcement
Status: approved | Jira:

## Objective

Verify and harden the per-data-type TTL and decay mechanisms built by PLAN-F-032 (cache-or-fetch layer) and PLAN-F-015 (four-layer memory subsystem) so that the system reliably satisfies all data freshness guarantees at the NFR level. The plan introduces: a write-time TTL validator that raises a `MissingTTLError` when any non-immutable, non-event-driven data type is written to Redis without an explicit TTL; an acceptance test suite that inspects Redis key TTLs at the integration level (not just at the unit-mock level); contract-level documentation of the TTL table embedded in the source code; and a configuration-path verification test for the price-freshness mode switch. After this plan is complete, every TTL claim in REQ-N-011 is covered by at least one automated test that fails if the contract is violated, and any developer who writes a Redis cache entry without a TTL for a time-bounded data type gets an immediate validation error.

## Architecture Context

This plan lives across two layers of the Six-Layer System Model (ARCHITECTURE §4):

- **Layer 2 — Ingestion & Cache**: The TTL validator is an enforcement point added to `src/ingestion/redis_cache.py` (PLAN-F-032). It wraps the existing `RedisCacheLayer.set()` method with a type-aware guard that consults the `TTLPolicy` registry before accepting a write.
- **Layer 4 — Processing / Memory Subsystem**: The semantic decay acceptance test exercises `SemanticHygieneService.run_decay_pass()` (PLAN-F-015, TASK-013) end-to-end using real PostgreSQL fixtures.

Key references:
- **Principle 2 — Local-First Data** (ARCHITECTURE §2): TTL is the primary freshness guarantee; historical data and embeddings are fetched once with no TTL.
- **Architecture §4 — Layer 2 components**: `Cache-or-Fetch` and `Ingestion Scheduler` are the owners of TTL enforcement.
- **Architecture §7.4 — Memory Subsystem**: `SemanticHygieneService` owns semantic fact decay; `decayed_at` column, not deletion.
- **Architecture §14 — Integration Catalogue**: TTL reference values are sourced from here (price bar 15-min / 5-sec, fundamentals 24h, news event 1h, macro 24h, infinite for historical price bars and event embeddings, event-driven for computed scores).

No new DB tables are required. No new modules are introduced. All new files are either additions to existing `src/ingestion/` and `src/ai/memory/` modules or test files.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-011 (self) | Semantic decay within 7 days of weekly hygiene run; price freshness ≤15 min delayed / ≤5 sec real-time; zero re-fetches of historical data after first fetch | Every AC is covered by an automated test that fails on contract violation; TTL validator prevents silent contract breaches at write time |

## Component Design

### New Components

```
Module: ingestion  (src/ingestion/)
  └── ttl_validator.py   — TTLValidator: raise MissingTTLError if a non-immutable
                           data type is written to Redis without a ttl_seconds value

Tests:
  tests/unit/ingestion/test_ttl_validator.py
      — unit tests for MissingTTLError guard per data type
  tests/integration/ingestion/test_ttl_enforcement_integration.py
      — integration tests: fakeredis + real TTL inspection via redis.ttl()
  tests/integration/memory/test_semantic_decay_acceptance.py
      — acceptance test for 6-month decay using a real PostgreSQL test DB
  tests/integration/ingestion/test_price_mode_switch_acceptance.py
      — acceptance test for price freshness mode switch via source_config
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ingestion/redis_cache.py` | Call `TTLValidator.validate(data_type, ttl_seconds)` inside `set()` before writing to Redis | Enforce TTL contract at write time, not only in tests |
| `src/ingestion/__init__.py` | Export `TTLValidator`, `MissingTTLError` | Public surface for dependent modules |

### Interfaces and Contracts

```python
# src/ingestion/ttl_validator.py

from src.ingestion.ttl_policy import DataType, TTLPolicy, DEFAULT_TTL_REGISTRY

class MissingTTLError(ValueError):
    """
    Raised when a Redis write is attempted for a time-bounded data type
    without an explicit TTL. Immutable and event-driven data types are exempt.
    """
    def __init__(self, data_type: DataType, policy: TTLPolicy) -> None:
        super().__init__(
            f"Redis write for data_type={data_type!r} requires an explicit TTL "
            f"(policy.invalidation={policy.invalidation!r}), but ttl_seconds=None was passed. "
            f"Set ttl_seconds from TTLPolicy.redis_ttl_seconds for this data type."
        )
        self.data_type = data_type
        self.policy = policy


class TTLValidator:
    """
    Validates that Redis write calls include an explicit TTL for any data type
    whose invalidation strategy is 'time_based'. Immutable and event_driven
    data types are explicitly allowed to have ttl_seconds=None.

    Consulted by RedisCacheLayer.set() before every Redis write.
    Inject the TTL registry to allow override in tests.
    """

    def __init__(self, registry: dict[DataType, TTLPolicy] | None = None) -> None:
        self._registry = registry or DEFAULT_TTL_REGISTRY

    def validate(self, data_type: DataType, ttl_seconds: int | None) -> None:
        """
        Raises MissingTTLError if data_type has invalidation='time_based'
        and ttl_seconds is None. No-op for 'immutable' and 'event_driven' types.
        """
        policy = self._registry.get(data_type)
        if policy is None:
            # Unknown data types are rejected conservatively
            raise MissingTTLError(data_type, TTLPolicy(data_type, None, None, "unknown"))
        if policy.invalidation == "time_based" and ttl_seconds is None:
            raise MissingTTLError(data_type, policy)
```

The updated `RedisCacheLayer.set()` signature (added `data_type` parameter):

```python
# src/ingestion/redis_cache.py  (modified method signature only)

async def set(
    self,
    key: str,
    value: bytes,
    ttl_seconds: int | None,
    data_type: DataType | None = None,  # NEW — required for validation
) -> None:
    """
    Validates TTL contract before writing.
    If data_type is provided, calls TTLValidator.validate(data_type, ttl_seconds)
    before the Redis SET. Raises MissingTTLError on contract violation.
    Sets key with EX=ttl_seconds when ttl_seconds is not None;
    persists indefinitely when ttl_seconds is None.
    """
```

## Implementation Tasks

### TASK-001: TTLValidator class and MissingTTLError · S/no-TDD · src/ingestion/ttl_validator.py, src/ingestion/__init__.py

Implement `TTLValidator` and `MissingTTLError` per the interface contract above. The validator is a pure function-holder with no I/O; it only inspects the `TTLPolicy.invalidation` field and raises when the contract is violated. Allowed exemptions are exactly: `invalidation == "immutable"` (PRICE_BAR_HISTORICAL, EVENT_EMBEDDING) and `invalidation == "event_driven"` (COMPANY_SCORE). All other data types are subject to the mandatory-TTL rule. Export both symbols from `src/ingestion/__init__.py`.

**AC covered**: AC-002 (validation error on missing TTL for price data)

---

### TASK-002: Integrate TTLValidator into RedisCacheLayer.set() · S/no-TDD · src/ingestion/redis_cache.py

Add the `data_type: DataType | None = None` parameter to `RedisCacheLayer.set()`. When `data_type` is provided (which it always is when called via `CacheOrFetch.cache_or_fetch`), call `self._validator.validate(data_type, ttl_seconds)` before the Redis SET. Inject `TTLValidator` into `RedisCacheLayer.__init__` as an optional parameter defaulting to `TTLValidator()`. This follows the Dependency Inversion principle — the validator is injectable for test override. Update every call site in `CacheOrFetch` to pass `data_type` through.

All existing unit tests for `RedisCacheLayer` must continue to pass after this change. The `data_type` parameter defaults to `None` so that callers who do not supply a data type bypass validation (backward-compatible; log a warning at DEBUG level when data_type is None).

**AC covered**: AC-002 (raises MissingTTLError before any Redis write for time-bounded types)

---

### TASK-003: Unit tests for TTLValidator — all data-type branches · M/TDD · tests/unit/ingestion/test_ttl_validator.py

**Tests to write first (TDD)**:
- `test_price_bar_without_ttl_raises_missing_ttl_error` — call `TTLValidator().validate(DataType.PRICE_BAR, None)`; assert `MissingTTLError` is raised
- `test_price_bar_with_ttl_does_not_raise` — call `validate(DataType.PRICE_BAR, 900)`; assert no exception
- `test_fundamentals_without_ttl_raises` — call `validate(DataType.FUNDAMENTALS, None)`; assert `MissingTTLError`
- `test_news_event_without_ttl_raises` — call `validate(DataType.NEWS_EVENT, None)`; assert `MissingTTLError`
- `test_macro_without_ttl_raises` — call `validate(DataType.MACRO, None)`; assert `MissingTTLError`
- `test_historical_price_bar_with_none_ttl_does_not_raise` — PRICE_BAR_HISTORICAL is immutable; `validate(DataType.PRICE_BAR_HISTORICAL, None)` must not raise
- `test_event_embedding_with_none_ttl_does_not_raise` — EVENT_EMBEDDING is immutable; `validate(DataType.EVENT_EMBEDDING, None)` must not raise
- `test_company_score_with_none_ttl_does_not_raise` — COMPANY_SCORE is event-driven; `validate(DataType.COMPANY_SCORE, None)` must not raise
- `test_missing_ttl_error_carries_data_type_and_policy` — assert `MissingTTLError.data_type == DataType.PRICE_BAR` and `error.policy.invalidation == "time_based"`
- `test_unknown_data_type_raises_conservatively` — pass a `DataType` value absent from the registry; assert `MissingTTLError` raised

**AC covered**: AC-002

---

### TASK-004: Integration test — Redis TTL values inspected at runtime · M/TDD · tests/integration/ingestion/test_ttl_enforcement_integration.py

**Tests to write first (TDD)**:
- `test_price_bar_cached_entry_has_ttl_of_900_seconds` — write a PRICE_BAR entry through the full `CacheOrFetch` stack (with `fakeredis.aioredis`); call `fake_redis.ttl(key)` and assert the returned value is between 895 and 900 (allowing for sub-second execution time)
- `test_fundamentals_cached_entry_has_ttl_of_86400_seconds` — same pattern for FUNDAMENTALS; assert TTL ≈ 86400
- `test_news_event_cached_entry_has_ttl_of_3600_seconds` — assert TTL ≈ 3600
- `test_historical_price_bar_cached_entry_has_no_expiry` — write PRICE_BAR_HISTORICAL; call `fake_redis.ttl(key)`; assert returned value is -1 (no expiry in Redis)
- `test_event_embedding_cached_entry_has_no_expiry` — same for EVENT_EMBEDDING; assert TTL == -1
- `test_company_score_cached_entry_has_no_expiry` — COMPANY_SCORE; assert TTL == -1 (event-driven; no time-based expiry)
- `test_redis_set_without_ttl_for_price_bar_raises_before_write` — call `RedisCacheLayer.set(key, value, ttl_seconds=None, data_type=DataType.PRICE_BAR)`; assert `MissingTTLError` is raised; assert the key does NOT exist in fakeredis afterward
- `test_real_time_price_bar_ttl_is_5_seconds` — configure `PriceModeSelector` to return `"realtime"`; write a PRICE_BAR entry; assert `fake_redis.ttl(key)` is between 1 and 5

Use `fakeredis[aioredis]` for all Redis interaction. Use `unittest.mock.AsyncMock` for the PostgreSQL layer (not needed in the hot path for these tests). All tests use `pytest-asyncio`.

**AC covered**: AC-002, AC-003

---

### TASK-005: Acceptance test — semantic fact 6-month decay · M/TDD · tests/integration/memory/test_semantic_decay_acceptance.py

**Tests to write first (TDD)**:
- `test_fact_unconfirmed_7_months_is_marked_decayed` — insert a `semantic_fact` row with `last_confirmed = now() - 7 months` (via SQLAlchemy `AsyncSession` against a test PostgreSQL instance); call `SemanticHygieneService.run_decay_pass()`; assert the row's `decayed_at` is now set (not NULL)
- `test_fact_unconfirmed_5_months_is_not_decayed` — insert a fact with `last_confirmed = now() - 5 months`; run decay pass; assert `decayed_at IS NULL`
- `test_decayed_fact_excluded_from_tool_query_results` — use the same 7-month-old decayed fact; call `SemanticRepository.query_facts(embedding=..., exclude_decayed=True)`; assert the fact does not appear in the result set
- `test_decayed_fact_accessible_when_exclusion_disabled` — same fact; call `query_facts(exclude_decayed=False)`; assert the fact appears
- `test_decay_does_not_delete_fact` — after `run_decay_pass()`, assert the row still exists in `semantic_fact` (SELECT COUNT(*) > 0 for the fact_id); deletion is explicitly out of scope
- `test_decay_pass_returns_correct_count` — insert 3 facts older than 6 months and 2 recent facts; run decay pass; assert `DecayPassResult.facts_decayed == 3`

These tests require a real PostgreSQL instance with pgvector enabled. Use `pytest-asyncio` and a `test_db` fixture that creates all Layer 2 tables (via Alembic in test mode) and tears them down after each test. Embeddings in test data can be zero-vectors of dimension 1536.

**AC covered**: AC-001

---

### TASK-006: Acceptance test — price freshness mode switch via config · M/TDD · tests/integration/ingestion/test_price_mode_switch_acceptance.py

**Tests to write first (TDD)**:
- `test_delayed_mode_applies_900_second_ttl` — configure `source_config` mock to return `{"price_freshness_mode": "delayed"}`; call `PriceModeSelector.get_price_ttl()`; assert return value is 900; write a PRICE_BAR entry; assert `fake_redis.ttl(key)` ≈ 900
- `test_realtime_mode_applies_5_second_ttl` — configure mock to return `{"price_freshness_mode": "realtime"}`; call `get_price_ttl()`; assert 5; write entry; assert TTL ≈ 5
- `test_mode_switch_requires_no_code_change` — simulate toggle: call once with `"delayed"` (assert 900), then update the mock return value to `"realtime"` and call again within the same test (assert 5); no module reload, no constructor reinitialisation; confirm `PriceModeSelector.get_price_ttl()` reads config on every call
- `test_unknown_mode_defaults_to_delayed` — configure mock to return `{"price_freshness_mode": "unknown_value"}`; assert `get_price_ttl()` returns 900 (safe default) without raising

Use `unittest.mock.AsyncMock` for the `get_source_config` callable injected into `PriceModeSelector`. Use `fakeredis[aioredis]` for Redis writes. `pytest-asyncio`.

**AC covered**: AC-004

---

### TASK-007: TTL contract constants module and inline documentation · S/no-TDD · src/ingestion/ttl_contract.py

Create `src/ingestion/ttl_contract.py` as the single authoritative reference for all TTL values stated in REQ-N-011. This is a constants module — no logic, no I/O. It is imported by `DEFAULT_TTL_REGISTRY` in `ttl_policy.py` (replacing raw integer literals) so that the documented value and the enforced value are the same symbol.

```python
# src/ingestion/ttl_contract.py
"""
Authoritative TTL contract values per REQ-N-011.

Changes to these constants immediately affect all cache-or-fetch behaviour
and all TTL-enforcement tests. Never duplicate these values elsewhere.
"""

# Time-bounded (seconds)
PRICE_BAR_DELAYED_TTL_S: int = 900          # 15 minutes — Finnhub delayed tier
PRICE_BAR_REALTIME_TTL_S: int = 5           # ≤5 seconds — WebSocket real-time mode
FUNDAMENTALS_TTL_S: int = 86_400            # 24 hours
NEWS_EVENT_TTL_S: int = 3_600              # 1 hour
MACRO_TTL_S: int = 86_400                  # 24 hours (calendar-based next-release logic is future)

# Immutable (infinite) — fetched once, stored permanently in PostgreSQL; never given a Redis TTL
HISTORICAL_PRICE_BAR_TTL_S: None = None    # past close prices — immutable
EVENT_EMBEDDING_TTL_S: None = None         # pgvector embeddings — immutable

# Event-driven invalidation — no time-based TTL; invalidated by ScoreCacheInvalidator
COMPANY_SCORE_TTL_S: None = None

# Semantic fact decay — not a Redis TTL; enforced by SemanticHygieneService
SEMANTIC_FACT_DECAY_MONTHS: int = 6
```

Update `src/ingestion/ttl_policy.py` `DEFAULT_TTL_REGISTRY` to import from this module instead of using inline integer literals.

**AC covered**: enables AC-002, AC-003 (constants used by TTLValidator and integration tests)

## Acceptance Criteria Coverage

- AC-001: Given a semantic_fact with last_confirmed = 7 months ago, the weekly hygiene job marks it decayed and subsequent tool queries exclude it → TASK-005
- AC-002: Given a price bar is written to Redis, TTL is explicitly set to 15 min (delayed) or 5 sec (real-time); attempting to write without TTL raises MissingTTLError → TASK-001, TASK-002, TASK-003, TASK-004, TASK-006
- AC-003: Given a historical price bar stored in PostgreSQL, no Redis TTL is set; permanently available without re-fetching → TASK-004, TASK-007
- AC-004: Given price freshness mode changed via admin feature flag, next fetch uses the configured TTL without any code change → TASK-006

## Risks and Notes

- **Test PostgreSQL requirement for TASK-005**: The semantic decay acceptance test must run against a real PostgreSQL instance with pgvector enabled. CI must provide this service. If the CI environment does not include a PostgreSQL service container, TASK-005 tests are skipped in unit-only runs and gated behind the `integration` pytest marker.
- **fakeredis TTL resolution**: `fakeredis` TTL values are returned in whole seconds. The assertion `895 <= ttl <= 900` is a pragmatic tolerance window for sub-second test execution. If the CI host is slow, the lower bound may need widening to 890.
- **Backward compatibility of RedisCacheLayer.set()**: Adding `data_type` as a keyword argument with default `None` is backward-compatible. However, all internal call sites inside `CacheOrFetch.cache_or_fetch()` must pass `data_type` explicitly — the `None` default exists only for callers outside the ingestion module (e.g., tests of other layers that stub the cache). Log a DEBUG warning when `data_type=None` to surface any missed call sites during development.
- **TTL contract constants update propagation**: When `ttl_contract.py` constants are changed, the matching test assertions in TASK-004 must be updated manually. This is intentional — the test assertions are the proof that the constant change was deliberate, not accidental.
- **Macro data TTL is 24h by default, not calendar-based**: REQ-N-011 notes that macro data uses a calendar-based approach (next release date). The default 24h TTL in `MACRO_TTL_S` is the MVP fallback; calendar-based TTL computation is deferred to a future plan. TASK-007 must include a comment in `ttl_contract.py` making this distinction explicit.
- **PLAN-F-032 TASK-005 overlap**: PLAN-F-032 TASK-005 already contains unit-level TTL assertions using mocked Redis. This plan's TASK-004 adds integration-level assertions using `fakeredis` with real TTL inspection via `redis.ttl()`. Both test layers are intentional — mocks verify the logic, `fakeredis` verifies that the correct Redis command (`SET key value EX n`) was actually issued.
