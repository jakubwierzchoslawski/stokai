---
req_id: REQ-F-002
slug: event-classification-and-extraction
title: Event Classification and Ticker Extraction
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "reactive-pipeline-ingestion: Classification and extraction are steps 3-4 of the pipeline" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, mode-a, classification]
  story_points:
  components: [event-pipeline, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Event Classification and Ticker Extraction

## Domain Context
Steps 3 and 4 of the Mode A Reactive Pipeline. Claude Haiku 4.5 is the sole model for these high-volume, latency-sensitive tasks. Anthropic-only in MVP (C-003 resolved).

## Summary
The system must classify raw event text using Haiku 4.5 (≤5 s), producing a structured output of category[], intensity, sentiment, geo_regions[], affected_sectors[], and CAMEO code; then extract relevant ticker symbols from the same text (≤3 s).

## Detailed Description
As described in architectural-considerations-digest.md §Integration Points and §System Behaviours Required, classification and extraction are deterministic LLM calls with structured outputs. Haiku 4.5 is chosen for its speed and cost characteristics for high-volume classification. The resolved contradiction C-003 mandates Anthropic-only models for MVP: Haiku 4.5 for classification/extraction, Sonnet 4.6 for analysis/filtering, Opus 4.7 for reasoning-heavy outputs.

Classification output schema:
- category[]: array of event categories (e.g. ["conflict", "sanctions"])
- intensity: integer 1–5
- sentiment: float –1.0 to +1.0
- geo_regions[]: affected geographic regions
- affected_sectors[]: impacted industry sectors
- cameo_code: CAMEO event ontology code

Ticker extraction produces a list of ticker symbols mentioned or implied by the event text relative to the US market (NYSE + NASDAQ).

Each call runs as a distinct step within the pipeline, constrained by the pipeline's per-agent limits (max_input_tokens, timeout_seconds, cost_ceiling_usd) defined in the agent YAML.

## Desired Outcome
Every raw event text produces a fully populated classification record within 5 seconds and a ticker list within 3 seconds, enabling the downstream exposure mapping and alert generation steps to proceed with structured data.

## Acceptance Criteria
- [ ] AC-001: Given raw event text input, Haiku 4.5 returns a valid classification JSON with non-null category[], intensity in range 1–5, sentiment in range –1.0 to +1.0, geo_regions[], affected_sectors[], and cameo_code within 5 seconds.
- [ ] AC-002: Given raw event text input, Haiku 4.5 returns a ticker extraction result (empty list permitted when no tickers are mentioned) within 3 seconds.
- [ ] AC-003: Given an event with no mentions of specific companies, the extract_tickers call returns an empty list without error, and the pipeline continues.
- [ ] AC-004: Given the agent YAML defines max_input_tokens and cost_ceiling_usd for the classification agent, the system enforces these limits and returns a structured error if exceeded rather than producing a truncated or overrun result.

## Out of Scope
- Exposure magnitude calculation (covered by exposure-mapping requirement)
- Historical analogy search (covered by event-embedding-and-analogy-search requirement)
- Use of any model other than Haiku 4.5 for classification/extraction in MVP

## Data Models
```
ClassificationOutput:
  category: string[]
  intensity: int (1-5)
  sentiment: float (-1.0 to 1.0)
  geo_regions: string[]
  affected_sectors: string[]
  cameo_code: string

TickerExtractionOutput:
  tickers: string[]   # may be empty
```

## Process Sequence
1. Pipeline executor passes raw event text to classify_event agent call (Haiku 4.5)
2. Structured classification JSON returned and validated against ClassificationOutput schema
3. Pipeline executor passes raw event text to extract_tickers agent call (Haiku 4.5)
4. Ticker list returned and validated
5. Both outputs stored on the pipeline state for downstream steps

## Subtasks
- [ ] ST-001: Define and implement classify_event agent YAML with Haiku 4.5, output_schema, limits — complexity: S
- [ ] ST-002: Implement classify_event LLM call with structured output parsing and schema validation — complexity: M
- [ ] ST-003: Define and implement extract_tickers agent YAML with Haiku 4.5, output_schema, limits — complexity: S
- [ ] ST-004: Implement extract_tickers LLM call with output validation — complexity: S
- [ ] ST-005: Unit tests for classification and extraction with varied event texts including edge cases (empty text, no tickers, ambiguous categories) — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Integration Points (Haiku 4.5); §System Behaviours Required | ≤5 s classify, ≤3 s extract, structured output fields |
| system-description-digest.md | §Data Entities (geo_event schema) | category[], intensity, cameo_code field definitions |
