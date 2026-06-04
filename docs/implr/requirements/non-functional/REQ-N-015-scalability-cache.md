---
req_id: REQ-N-015
slug: n-scalability-cache
title: Cache-Driven Sublinear API Cost Scalability
type: non-functional
nfr_category: Scalability
status: approved
complexity: M
tdd_required: true
source_docs:
  - system-description-digest.md
dependencies:
  - { id: "", reason: "cache-or-fetch-data-access: Cache layer is the mechanism delivering this property" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [backend, scalability, caching, cost]
  story_points:
  components: [data-access, caching, scalability]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Cache-Driven Sublinear API Cost Scalability

## Domain Context
Adding users must not proportionally increase external API costs. The cache-or-fetch pattern ensures data fetched for one user is served to all subsequent users within the TTL window, making marginal API cost approach zero as user count grows.

## Summary
Adding users must cause external API call volume to grow sublinearly (approaching constant), not linearly. Viewing a price chart 100 times must incur exactly 0 additional external API calls after the first fetch within the TTL window.

## Detailed Description
As specified in system-description-digest.md non-functional signals:

**Sublinear growth:** If 1 user triggers 10 external API calls/day, 100 users should not trigger 1,000 external API calls/day. Because data is cached in Redis/PostgreSQL with TTL, the marginal cost of an additional user accessing the same data within the TTL window is zero external API calls.

**Zero-additional-call chart viewing:** Price chart for company X loaded by user A at 10:00 is cached. User B loading the same chart at 10:14 (within 15-min TTL) hits the Redis cache; external API call count for company X price data = 1 for that TTL window, regardless of how many users viewed it.

**Mechanism:** The cache-or-fetch pattern with tenant-level (or global) cache keys for shared data types (price bars, fundamentals, embeddings) ensures data shared across users is fetched once. User-specific data (portfolio, scores) is fetched per-user but still cached across repeated accesses by the same user.

**Test assertion:** A load test simulating 100 sequential views of the same price chart must produce exactly 1 external price API call.

## Desired Outcome
The system's external API costs remain approximately constant as user count increases within an order of magnitude, making the cost model sustainable for multi-user deployment.

## Acceptance Criteria
- [ ] AC-001: Given 100 sequential requests for the same company's price chart within a single 15-minute TTL window, the external price API is called exactly once; the remaining 99 requests are served from Redis or PostgreSQL.
- [ ] AC-002: Given 10 users each requesting the same company's fundamentals within a 24-hour TTL window, the external fundamentals API is called exactly once; all 10 users receive the cached data.
- [ ] AC-003: Given a load test simulating 50 concurrent users accessing the screener with different sort/filter combinations (but same underlying company data), external API calls do not scale linearly with user count; the ratio of external calls to user requests is < 0.05 (95% cache hit rate target).

## Out of Scope
- User-specific data caching optimizations (portfolio, watchlist are user-specific and must be fetched per user)
- Redis cluster scaling for very high concurrency (MVP is single-node Redis)

## NFR-Specific Fields

### Measurable Target
- Price chart viewed 100× in one TTL window: exactly 1 external price API call (0 additional after first)
- Cache hit rate for shared data types (price bars, fundamentals, macro data): ≥95% in steady state
- External API call growth vs user count: sublinear (verified by load test with 1, 10, 100 concurrent users)

### Verification Method
- Method: Load test monitoring external API call count vs request count ratio
- Tool/Process: pytest + requests-mock to count actual provider adapter calls; Redis hit/miss logging; load test with varying concurrency
- Frequency: Per release (load test); continuous (cache hit rate monitoring in production)
- Owner: QA / DevOps

### Category Rationale
Scalability NFR because the $100/month budget constraint only holds if API costs grow sublinearly with users. Linear growth would exhaust the budget at a small user count, making the business model unviable.

## Subtasks
- [ ] ST-001: Implement cache key strategy for shared data types (tenant-level or global) — complexity: S
- [ ] ST-002: Implement Redis hit/miss rate tracking and admin dashboard metric — complexity: S
- [ ] ST-003: Load test asserting 100-view / 1-API-call property — complexity: M
- [ ] ST-004: Load test asserting sublinear API call growth with 1, 10, 100 concurrent users — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Non-Functional Signals | Local-first cache ensures data cost grows sublinearly; viewing a chart 100× incurs 0 additional API calls |
