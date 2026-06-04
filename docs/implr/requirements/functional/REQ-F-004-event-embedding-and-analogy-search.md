---
req_id: REQ-F-004
slug: event-embedding-and-analogy-search
title: Event Embedding and Historical Analogy Search
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "cold-start-data-seeding: Historical event embeddings must exist before analogy search can return meaningful results" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, vector-search, mode-a]
  story_points:
  components: [event-pipeline, vector-search]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Event Embedding and Historical Analogy Search

## Domain Context
Steps 7 and 8 of the Mode A Reactive Pipeline. Converts event text to a semantic vector and retrieves historically similar events with their market outcome statistics, forming the evidence base for the alert recommendation.

## Summary
The system must embed the classified event text using OpenAI text-embedding-3-small (≤2 s), store the VECTOR(1536) in the event_embedding table, then execute a pgvector HNSW cosine top-K search to retrieve historical analogies with associated market statistics.

## Detailed Description
As specified in architectural-considerations-digest.md §Integration Points and §System Behaviours Required, event embedding uses OpenAI text-embedding-3-small, which produces a 1536-dimensional vector. The embedding is stored in the event_embedding table with an HNSW index to enable sub-second similarity search.

The HNSW cosine top-K search returns the most semantically similar historical events. Each returned analogy includes:
- Historical event metadata (title, date, intensity, category)
- Associated market outcome statistics (price_change_t1d from event_exposure records)
- sample_size count used for disclaimer threshold checking

When sample_size < 5 (fewer than 5 historical analogies with valid outcome data), the result set is flagged and a disclaimer must accompany any recommendation generated from it (per business rule 16 in root-synthesis).

Historical data (past embeddings) has infinite TTL; the embedding computed for the current event is persisted permanently as it becomes part of the historical archive.

## Desired Outcome
Every new event is embedded and matched against the historical archive within the pipeline's 60–75 second cumulative stage window, returning a ranked set of analogous events with market outcome statistics that the recommendation step can cite as evidence.

## Acceptance Criteria
- [ ] AC-001: Given event text, the system calls OpenAI text-embedding-3-small, receives a VECTOR(1536) response, stores it in the event_embedding table with the event_id, and completes within 2 seconds.
- [ ] AC-002: Given the embedding is stored, a pgvector HNSW cosine search returns at least the top-K historical event IDs (K configurable, default ≥ 5) sorted by similarity score in descending order.
- [ ] AC-003: Given the search returns fewer than 5 historical events with valid price_change_t1d outcome data, the analogy result is flagged with low_sample=true and sample_size is recorded accurately.
- [ ] AC-004: Given the HNSW index is populated with the cold-start historical dataset, similarity search on a 1536-dimensional vector completes within the pipeline's stage-gate budget.
- [ ] AC-005: Given a newly processed event's embedding is stored, the same embedding is retrievable by future events as a historical analogy without re-fetching from the API (immutable past / infinite TTL rule).

## Out of Scope
- Alert text generation using the analogies (covered by alert-dispatch-anti-fatigue requirement)
- GDELT historical archive seeding (covered by cold-start-data-seeding requirement)
- Alternative embedding models beyond OpenAI text-embedding-3-small in MVP

## Data Models
```
event_embedding:
  event_id: UUID (FK → geo_event)
  embedding: VECTOR(1536)
  created_at: timestamp
  INDEX: HNSW (cosine)

AnalogSearchResult:
  event_id: UUID
  similarity_score: float
  event_title: string
  event_date: timestamp
  intensity: int
  category: string[]
  price_change_t1d: float | null
  sample_size: int
  low_sample: bool
```

## Process Sequence
1. Pipeline executor calls OpenAI text-embedding-3-small with event text
2. VECTOR(1536) response stored in event_embedding table
3. pgvector HNSW cosine search executed against event_embedding table
4. Top-K results retrieved with associated event_exposure.price_change_t1d statistics
5. sample_size computed; low_sample flag set if < 5 valid outcomes
6. Analogy result set returned to pipeline state for step 9 (alert text generation)

## Subtasks
- [ ] ST-001: Implement OpenAI text-embedding-3-small API call and VECTOR(1536) storage — complexity: M
- [ ] ST-002: Implement pgvector HNSW cosine top-K search with configurable K — complexity: M
- [ ] ST-003: Implement sample_size computation and low_sample flag logic — complexity: S
- [ ] ST-004: Ensure event_embedding rows have infinite TTL (no expiry) in the cache/TTL system — complexity: S
- [ ] ST-005: Unit tests for embedding storage, search result ranking, and low-sample flag — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Integration Points (OpenAI embedding, pgvector); §System Behaviours Required | ≤2 s embedding, HNSW cosine search, historical analogy retrieval |
| system-description-digest.md | §Data Entities (event_embedding, event_exposure); §Architecture Signals | VECTOR(1536), HNSW index, immutable past / infinite TTL rule |
| system-description-digest.md | §Business Rules item 5 | Disclaimer when sample_size < 5 |
