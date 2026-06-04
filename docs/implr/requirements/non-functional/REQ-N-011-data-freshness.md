---
req_id: REQ-N-011
slug: n-data-freshness
title: Data Freshness and TTL Enforcement
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "cache-or-fetch-data-access: TTL enforcement is part of the cache-or-fetch layer" }
  - { id: "", reason: "four-layer-memory-subsystem: Semantic fact 6-month decay is part of this NFR" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [backend, data, freshness, ttl]
  story_points:
  components: [data-access, memory-subsystem]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Data Freshness and TTL Enforcement

## Domain Context
Stale data leads to misleading analysis. Per-data-type TTL ensures price data is not outdated, semantic facts do not persist indefinitely without evidence, and Redis/PostgreSQL caches do not serve expired data.

## Summary
Semantic facts must decay after 6 months unconfirmed; Redis TTL and PostgreSQL TTL must be enforced per data type; price freshness default is 15-minute delay (real-time via config only); historical data and embeddings have infinite TTL.

## Detailed Description
As specified in architectural-considerations-digest.md business rules 40, 45–48:

**Semantic fact decay:** Any semantic_fact with last_confirmed > 6 months ago is marked decayed (flagged, not deleted) by the weekly hygiene job. Decayed facts are excluded from tool query results.

**Redis TTL enforcement:** Every cached value written to Redis includes an explicit TTL. Values without TTL must fail validation. The TTL is set from the per-data-type TTL configuration.

**Price freshness:** Default 15-minute delay (Finnhub REST delayed tier). Real-time switch (≤5 s via WebSocket stream) activated only by configuration parameter change, not code change.

**Infinite TTL for immutable data:** Historical price bars (past close prices), event embeddings — these are never written to Redis with a TTL; they are fetched once and stored permanently in PostgreSQL.

**TTL by data type (reference):**
- Current price bars: 15 min (delayed mode) / 5 s (real-time mode)
- Fundamentals: 24 hours
- News events: 1 hour
- Macro data: 24 hours
- Historical price bars: infinite (immutable past)
- Event embeddings: infinite (immutable past)
- Computed scores: no TTL; event-driven invalidation

## Desired Outcome
Users always receive data that is fresh within the defined TTL windows; stale semantic facts do not distort AI analysis; the system never serves expired embeddings or historical prices because those are immutable.

## Acceptance Criteria
- [ ] AC-001: Given a semantic_fact with last_confirmed = 7 months ago, the weekly hygiene job marks it decayed and subsequent tool queries for that entity do not include the decayed fact.
- [ ] AC-002: Given a price bar is written to Redis, the TTL is explicitly set to 15 minutes (delayed mode) or 5 seconds (real-time mode); attempting to write a Redis entry without TTL for price data raises a validation error.
- [ ] AC-003: Given a historical price bar is fetched from an external API and stored in PostgreSQL, no Redis TTL is set; it is permanently available in PostgreSQL without re-fetching.
- [ ] AC-004: Given the price freshness mode is changed from "delayed" to "real-time" via admin feature flag, the next price fetch uses the real-time provider (≤5 s WebSocket) without any code changes.

## Out of Scope
- Automated deletion of decayed semantic facts (marked inactive, not deleted)
- Dynamic TTL adjustment based on market volatility

## NFR-Specific Fields

### Measurable Target
- Semantic fact decay: facts unconfirmed >6 months are marked inactive within 7 days of the weekly hygiene job run
- Price data freshness: current price bars ≤15 minutes stale in delayed mode; ≤5 seconds in real-time mode
- Infinite TTL compliance: 0 historical price bars or event embeddings re-fetched from external API after first fetch (verified by external API call count)

### Verification Method
- Method: Automated tests for TTL expiry, decay job execution, and Redis TTL validation; API call count monitoring
- Tool/Process: pytest unit tests for TTL logic; Redis TTL inspection; external API call counter in admin cost monitor
- Frequency: Per release (tests); weekly (decay job); continuous (Redis TTL validation)
- Owner: QA / DevOps

### Category Rationale
Reliability NFR because stale data produces incorrect exposure analysis and misleading recommendations. Data freshness is a correctness requirement for the AI recommendation quality.

## Subtasks
- [ ] ST-001: Implement Redis TTL validation (reject writes without TTL for non-infinite types) — complexity: S
- [ ] ST-002: Implement semantic fact decay flagging in weekly hygiene job — complexity: S
- [ ] ST-003: Implement infinite TTL classification for historical prices and embeddings — complexity: S
- [ ] ST-004: Automated tests for TTL enforcement per data type — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rules 40, 45-48; Non-Functional Signals | Semantic decay 6 months, per-type TTL, immutable past, event-driven invalidation |
| system-description-digest.md | Business Rules 8, 13 | Price freshness 15-min, real-time switch via config, immutable past |
