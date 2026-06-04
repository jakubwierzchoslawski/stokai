---
req_id: REQ-F-001
slug: reactive-pipeline-ingestion
title: Reactive Pipeline Ingestion (Mode A)
type: functional
status: approved
complexity: XL
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, pipeline, mode-a]
  story_points:
  components: [event-pipeline]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Reactive Pipeline Ingestion (Mode A)

## Domain Context
Mode A is the deterministic, fixed-step Reactive Pipeline that converts real-time external events (tweets, GDELT polls, SEC EDGAR filings, price anomalies) into user alerts within 90 seconds. It is the system's primary edge-delivery mechanism with a strict cost ceiling of $0.05 per event.

## Summary
The system must execute a 12-step fixed-sequence pipeline from event arrival to user alert dispatch, completing end-to-end in ≤90 seconds at a cost ceiling of $0.05 per event, with no tools, no loops, and no decision branches.

## Detailed Description
As described in architectural-considerations-digest.md §System Behaviours Required and §Business Rules items 2 and 18, Mode A is triggered by four external sources: Twitter/X Filtered Stream, GDELT poll, SEC EDGAR filing, and price anomaly. The pipeline is strictly sequential with 12 numbered steps and no branching. Each step has a defined latency budget.

The 12 steps are:
1. Receive/detect external event (0–15 s window)
2. Persist raw event to database
3. Classify event — Haiku 4.5, ≤5 s (category[], intensity, sentiment, regions[], sectors[], CAMEO code)
4. Extract tickers — Haiku 4.5, ≤3 s
5. Compute exposure map against company geo_revenue (JSONB) and sector fields
6. Persist geo_event record and event_exposure rows
7. Embed event text — OpenAI text-embedding-3-small, ≤2 s, stored as VECTOR(1536)
8. Find historical analogies — pgvector HNSW cosine top-K search
9. Generate alert text — Sonnet 4.6, ~80 words, ≤8 s
10. Evaluate alert rules (per-user rules, anti-fatigue controls)
11. Dispatch alert or log silent (based on rule outcome)
12. Enqueue Mode B deep-dive job if event intensity ≥ 4 or portfolio match detected

Twitter/X is off by default (C-006 resolved). When Twitter/X is disabled or rate-limited, the pipeline continues using remaining sources with graceful degradation.

The total LLM budget for the pipeline is ~60 s. Steps that produce no alert still complete steps 1–11 (logging silent); step 12 conditional enqueueing applies regardless of alert outcome.

## Desired Outcome
A geopolitical event detected from any active source is classified, matched to affected portfolio companies, and delivered as a user alert within 90 seconds, at a cost not exceeding $0.05, giving the user a 20–90 minute information edge over the average retail investor.

## Acceptance Criteria
- [ ] AC-001: Given an external event arrives from GDELT, SEC EDGAR, or a price anomaly source, the system completes all 12 pipeline steps and produces a persisted geo_event row, event_exposure rows, event_embedding row, and an alert or silent-log record within 90 seconds of event arrival.
- [ ] AC-002: Given a high-intensity event (intensity 4 or 5) matching at least one portfolio company, a Mode B deep-dive job is enqueued at step 12 within the 90-second window.
- [ ] AC-003: Given classification by Haiku 4.5, the geo_event record carries populated category[], intensity, sentiment, geo_regions[], affected_sectors[], and cameo_code fields within 5 seconds of classification start.
- [ ] AC-004: Given event text is embedded (step 7), the embedding is stored as a VECTOR(1536) in the event_embedding table and the pgvector HNSW top-K search returns analogy results within the 60-second total LLM budget.
- [ ] AC-005: Given Twitter/X is toggled off by admin, the pipeline completes successfully using remaining sources (GDELT, EDGAR, price anomaly) without errors or degraded output quality.
- [ ] AC-006: Given any single pipeline run, the total LLM and API cost is recorded and does not exceed $0.05 per event.

## Out of Scope
- Mode B deliberative workflow execution (separate requirements)
- Real-time price streaming provider selection (covered by cache-or-fetch NFR)
- User-facing UI for alert display (covered by alerts-center requirement)
- Broker integration or trade execution

## Data Models
```
geo_event: event_id, occurred_at, detected_at, category[], intensity(1-5), title, summary,
           lat, lon, geo_regions[], affected_sectors[], sentiment, cameo_code,
           source_provider, tenant_id

event_exposure: (event_id, company_id) PK, exposure_type, direction, magnitude(0-1),
                price_change_t1d

event_embedding: event_id, embedding VECTOR(1536), hnsw index

alert: alert_id, event_id, user_id, tenant_id, rule_id, dispatched_at, channel, status,
       cost_usd
```

## Process Sequence
1. External source adapter detects event and pushes to ingestion queue
2. Pipeline executor picks up event, persists raw event record (step 2)
3. Haiku 4.5 classifies event (step 3, ≤5 s)
4. Haiku 4.5 extracts tickers (step 4, ≤3 s)
5. Exposure engine cross-references geo_regions + affected_sectors against company table (step 5)
6. geo_event and event_exposure rows committed to DB (step 6)
7. OpenAI embedding API called, VECTOR(1536) stored (step 7, ≤2 s)
8. pgvector HNSW cosine search returns top-K historical analogies (step 8)
9. Sonnet 4.6 generates ~80-word alert text (step 9, ≤8 s)
10. Alert rules evaluated against per-user config and anti-fatigue controls (step 10)
11. Alert dispatched via SendGrid or logged silent (step 11)
12. Conditional: if intensity ≥ 4 or portfolio match → enqueue deep-dive Mode B job (step 12)

## Subtasks
- [ ] ST-001: Implement ingestion queue consumer and raw event persistence — complexity: M
- [ ] ST-002: Implement Haiku 4.5 classify_event call with structured output (category[], intensity, sentiment, regions[], sectors[], CAMEO) — complexity: M
- [ ] ST-003: Implement Haiku 4.5 extract_tickers call with ≤3 s target — complexity: S
- [ ] ST-004: Implement exposure mapping engine (geo_revenue JSONB cross-reference) — complexity: M
- [ ] ST-005: Implement OpenAI text-embedding-3-small integration and event_embedding table write — complexity: M
- [ ] ST-006: Implement pgvector HNSW cosine top-K search for historical analogies — complexity: M
- [ ] ST-007: Implement Sonnet 4.6 generate_alert_text call (~80 words, ≤8 s) — complexity: M
- [ ] ST-008: Implement alert rule evaluation and dispatch/log-silent branching — complexity: M
- [ ] ST-009: Implement Mode B deep-dive conditional enqueue (step 12) — complexity: S
- [ ] ST-010: Implement per-pipeline cost tracking and $0.05 ceiling enforcement — complexity: S
- [ ] ST-011: Implement graceful degradation when Twitter/X is off or rate-limited — complexity: S
- [ ] ST-012: Integration test for full 12-step pipeline end-to-end within 90 s — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 2, 18, 19; §System Behaviours Required | 12-step sequence, latency targets, cost ceiling, conditional deep-dive enqueue |
| system-description-digest.md | §System Behaviours Required; §Non-Functional Signals | Stage-gate latency breakdown (15 s increments), $0.05 ceiling, tweet ≤30 s |
| architectural-considerations-digest.md | §Integration Points | Haiku 4.5 classify/extract, Sonnet 4.6 alert text, OpenAI embedding, pgvector |
