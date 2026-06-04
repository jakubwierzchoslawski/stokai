---
req_id: REQ-F-031
slug: cold-start-data-seeding
title: Cold-Start Historical Data Seeding
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - system-description-digest.md
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "event-embedding-and-analogy-search: Analogy search depends on historical embeddings being seeded" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, data, seeding, gdelt]
  story_points:
  components: [data-ingestion, cold-start]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Cold-Start Historical Data Seeding

## Domain Context
The analogy engine cannot produce meaningful results at launch without historical event data and paired price outcomes. GDELT historical archive (1979+) must be ingested and paired with historical prices before system go-live. ACLED is designated as the backup if GDELT commercial license is denied.

## Summary
The system must provide a one-time cold-start seeding process that ingests the GDELT historical event archive (1979+), pairs events with historical prices, generates embeddings for each event, and stores all data in the production database before system go-live so the analogy engine is functional at launch.

## Detailed Description
As specified in system-description-digest.md business rule 22 and architectural-considerations-digest.md architecture signals, the cold-start seeding is an architectural requirement. Without it the pgvector HNSW analogy search returns empty results for all new events.

The seeding process must:
1. Verify GDELT commercial license status before production use (system-description-digest.md business rule 20); if denied, use ACLED as backup
2. Fetch GDELT historical archive batch (from 1979 or configurable start date)
3. Parse, classify, and store events as geo_event rows
4. Fetch corresponding historical price data (OHLCV) for tracked companies for the same date range
5. Compute price_change_t1d for each (event, company) pair → populate event_exposure.price_change_t1d
6. Generate OpenAI text-embedding-3-small embeddings for each event → store in event_embedding
7. Build/rebuild the HNSW index on the event_embedding table

The process is idempotent: re-running detects already-seeded events by event_id and skips them.

Historical data (past prices, embeddings) has infinite TTL and is never re-fetched (immutable past rule).

## Desired Outcome
At system go-live, the analogy engine can return semantically similar historical events with market outcome statistics for any new incoming event, enabling the recommendation system to cite evidence from the historical archive.

## Acceptance Criteria
- [ ] AC-001: Given the cold-start seeding script is run, it ingests GDELT events from the configured start date, generates embeddings, and stores event_embedding rows; a subsequent analogy search on a new event returns at least one historical result with a valid price_change_t1d value.
- [ ] AC-002: Given the seeding script is run a second time (idempotency check), no duplicate geo_event or event_embedding rows are created; already-seeded events are detected and skipped.
- [ ] AC-003: Given GDELT commercial license is denied, the seeding script can be configured to use the ACLED data source instead with equivalent output format.
- [ ] AC-004: Given seeding is complete, the HNSW index on event_embedding is built and the pgvector cosine search returns results in under 2 seconds for any 1536-dimensional query vector.
- [ ] AC-005: Given historical price data exists in the price_bar table for the same date range, event_exposure.price_change_t1d is populated for each (event, company) pair within the seeded dataset.

## Out of Scope
- Ongoing GDELT ingestion (live polling is a separate Mode A trigger)
- Historical seeding for markets other than US NYSE + NASDAQ in MVP

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | Has the GDELT commercial license been verified for MVP production use? The source documents say "verify before launch" but do not confirm current status. If denied, what is the ACLED coverage scope for geopolitical events? | system-description-digest.md business rule 20; root-synthesis Ambiguities Detected | 2026-06-02 | ☐ |

## Data Models
```
geo_event (seeded from GDELT):
  event_id: UUID
  occurred_at: timestamp
  detected_at: timestamp (seeding time)
  category: string[]
  intensity: int
  title: string
  summary: text
  lat: float
  lon: float
  geo_regions: string[]
  affected_sectors: string[]
  sentiment: float
  cameo_code: string
  source_provider: gdelt | acled
  tenant_id: UUID (system seed tenant)

event_embedding:
  event_id: UUID
  embedding: VECTOR(1536)

event_exposure (seeded with historical price_change_t1d):
  event_id: UUID
  company_id: UUID
  price_change_t1d: float  -- from historical OHLCV lookup
```

## Process Sequence
1. Verify GDELT license status (or fallback: configure ACLED)
2. Fetch GDELT historical archive batch
3. Parse events → classify → store as geo_event rows (idempotent check on event_id)
4. Fetch historical OHLCV for all tracked companies for the same date range
5. For each (event, company): compute price_change_t1d → store in event_exposure
6. For each event: call OpenAI text-embedding-3-small → store in event_embedding
7. Rebuild HNSW index on event_embedding table
8. Run validation query: verify analogy search returns results

## Subtasks
- [ ] ST-001: Implement GDELT historical archive batch fetcher — complexity: L
- [ ] ST-002: Implement ACLED fallback fetcher with equivalent output format — complexity: M
- [ ] ST-003: Implement idempotent seeding logic (skip already-seeded events) — complexity: S
- [ ] ST-004: Implement historical OHLCV fetch and price_change_t1d computation — complexity: M
- [ ] ST-005: Implement batch embedding generation (OpenAI text-embedding-3-small) — complexity: M
- [ ] ST-006: Implement HNSW index build/rebuild after seeding — complexity: S
- [ ] ST-007: Implement seeding validation and progress reporting — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Business Rules 20, 22; Architecture Signals | GDELT cold-start requirement, ACLED fallback, immutable past rule |
| architectural-considerations-digest.md | Architecture Signals | GDELT historical archive seed as cold-start architectural requirement |
