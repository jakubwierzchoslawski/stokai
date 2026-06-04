---
req_id: REQ-F-032
slug: cache-or-fetch-data-access
title: Cache-or-Fetch Data Access Pattern
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - system-description-digest.md
  - architectural-considerations-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, data, caching, infrastructure]
  story_points:
  components: [data-access, caching]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Cache-or-Fetch Data Access Pattern

## Domain Context
The universal data access strategy is Redis → PostgreSQL → external API (only on cache miss). Per-data-type TTL policy. Historical data and embeddings have infinite TTL (immutable past). Computed scores are invalidated event-driven. This ensures API cost grows sublinearly with user count.

## Summary
The system must implement a three-tier cache-or-fetch pattern (Redis → PostgreSQL → external API on cache miss) with per-data-type TTL enforcement; historical data and embeddings at infinite TTL (never re-fetched); and event-driven invalidation for computed scores only.

## Detailed Description
As specified in system-description-digest.md business rules 8, 12–14 and architecture signals; architectural-considerations-digest.md business rules 45–48:

**Cache-or-Fetch Sequence:**
1. Check Redis for cached value (hot cache)
2. On Redis miss: check PostgreSQL (warm storage)
3. On PostgreSQL miss: fetch from external API; store in PostgreSQL + Redis with TTL; return

**TTL Policy by Data Type:**
- Price bars (OHLCV): 15-minute TTL (delayed mode); 5-second TTL (real-time mode, config switch only)
- Fundamentals data: 24-hour TTL
- GDELT/news events: 1-hour TTL
- Macro data (FRED): 24-hour TTL
- Historical price bars (past close): infinite TTL (never re-fetched; immutable past)
- Event embeddings: infinite TTL (immutable past)
- Computed scores: no TTL; invalidated event-driven only

**Price Freshness Mode Switch:**
- Controlled by a configuration parameter only (not a code change)
- Admin panel feature flag changes the provider registry selection
- Default: 15-minute delayed (free tier); real-time switch available via config

**Key invariant:** Viewing a price chart 100 times incurs 0 additional external API calls (all hits served from Redis or PostgreSQL after the first fetch).

## Desired Outcome
External API calls are minimized to the absolute necessary set; historical data is fetched exactly once and served from local storage forever; API cost grows sublinearly with user count because data is shared across all users in the same tenant.

## Acceptance Criteria
- [ ] AC-001: Given a price bar request for a company that has been fetched within the TTL window, the system returns the cached value from Redis or PostgreSQL without calling the external API; external API call count for that company is 0.
- [ ] AC-002: Given a request for a historical price bar (any date in the past that has previously been fetched), the system returns it from PostgreSQL with no Redis TTL expiry; the bar is never re-fetched from the external API.
- [ ] AC-003: Given an event embedding is stored, it persists with no TTL and is never invalidated; re-fetching the embedding from OpenAI is not triggered for past events.
- [ ] AC-004: Given a computed company_score, it is not re-computed on a schedule but only when a geo_event triggers event-driven invalidation for that company; the score retains its value between events.
- [ ] AC-005: Given the price freshness mode is changed from "delayed" to "real-time" in the admin panel feature flag, the provider registry selects the real-time price source without any code changes or service restart.

## Out of Scope
- Multi-tenant Redis namespace isolation (single tenant MVP; multi-tenant Phase 5)
- Cache warm-up strategies beyond the first real user request

## Data Models
```
TTLPolicy (configuration):
  data_type: string
  redis_ttl_seconds: int | null  -- null = infinite
  pg_ttl_seconds: int | null     -- null = infinite
  invalidation: enum(time_based, event_driven, immutable)

CacheEntry (conceptual):
  cache_key: string  -- {data_type}:{entity_id}:{params_hash}
  value: bytes
  fetched_at: timestamp
  expires_at: timestamp | null
```

## Process Sequence
1. Data access request received (tool call or direct)
2. Generate cache_key from data_type + entity_id + params
3. Redis GET → cache hit → return value
4. Redis miss → PostgreSQL SELECT → cache hit → write back to Redis with TTL → return value
5. PostgreSQL miss → call external API via provider adapter
6. Store result in PostgreSQL (with pg_ttl) + Redis (with redis_ttl)
7. Return value to caller

## Subtasks
- [ ] ST-001: Implement cache-or-fetch base class with Redis → PostgreSQL → API chain — complexity: M
- [ ] ST-002: Implement per-data-type TTL configuration — complexity: S
- [ ] ST-003: Implement infinite TTL for historical prices and embeddings — complexity: S
- [ ] ST-004: Implement event-driven cache invalidation for computed scores — complexity: M
- [ ] ST-005: Implement price freshness mode config switch (no code change) — complexity: S
- [ ] ST-006: Unit tests for cache hit/miss paths, TTL enforcement, event-driven invalidation — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Business Rules 8, 12-14; Architecture Signals | Cache-or-fetch sequence, TTL policy, immutable past, event-driven invalidation, price freshness switch |
| architectural-considerations-digest.md | Business Rules 45-48 | Redis → PostgreSQL → API cascade, per-data-type TTL, immutable past |
