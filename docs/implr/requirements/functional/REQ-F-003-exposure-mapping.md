---
req_id: REQ-F-003
slug: exposure-mapping
title: Event Exposure Mapping
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "event-classification-and-extraction: geo_regions[] and affected_sectors[] must be populated before exposure can be computed" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, scoring, mode-a]
  story_points:
  components: [event-pipeline, scoring]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Event Exposure Mapping

## Domain Context
Step 5 of the Mode A Reactive Pipeline. Computes which companies in the tracked universe are affected by the event, based on geographic revenue distribution (geo_revenue JSONB) and sector classification. Results are persisted as event_exposure rows.

## Summary
The system must compute a set of affected companies for each classified event by cross-referencing the event's geo_regions[] and affected_sectors[] against the company table's geo_revenue JSONB and sector fields, then persist event_exposure rows with magnitude and direction for each match.

## Detailed Description
As described in system-description-digest.md §Data Entities, each company record holds a geo_revenue JSONB field representing revenue by region as proportional weights. The exposure engine cross-references this against the event's geo_regions[] to compute a geographic exposure magnitude (0–1). Sector exposure is computed by matching the company's sector_internal and sector_gics fields against the event's affected_sectors[].

The resulting event_exposure row captures:
- exposure_type: geo | sector | combined
- direction: positive | negative (derived from event sentiment and sector impact model)
- magnitude: 0.0–1.0 (weighted combination of geo and sector exposure)

Companies with magnitude below a configurable threshold (e.g. 0.05) are excluded to avoid noise. The entire computation is DB-driven, operating on the tracked company universe (~100–200 companies) without external API calls. This step runs within the 45–60 s window of the pipeline stage gate.

Step 6 persists the geo_event record and all event_exposure rows atomically after this computation.

## Desired Outcome
Every classified event produces a set of event_exposure rows covering all materially affected companies (magnitude ≥ threshold) within the pipeline's 60-second cumulative stage window, enabling accurate alert targeting and portfolio match detection.

## Acceptance Criteria
- [ ] AC-001: Given a classified event with geo_regions=["Middle East"] and affected_sectors=["energy"], companies with geo_revenue JSONB containing "Middle East" > 0 and sector matching "energy" receive event_exposure rows with magnitude > 0 and appropriate exposure_type.
- [ ] AC-002: Given a company with zero revenue in the event's geo_regions and no sector match, no event_exposure row is created for that company.
- [ ] AC-003: Given the event is persisted (step 6), the geo_event row and all event_exposure rows are committed in a single atomic transaction; partial writes are not permitted.
- [ ] AC-004: Given the full tracked company universe (~200 companies), the exposure computation and DB write complete within the 15-second stage-gate budget allocated to steps 5–6.

## Out of Scope
- Real-time geo_revenue data updates (company data is managed separately)
- Portfolio score recalculation (covered by portfolio-scoring-and-geo-modifier requirement)
- Companies not in the tracked universe (on-demand lookups are separate)

## Data Models
```
event_exposure:
  event_id: UUID (FK → geo_event)
  company_id: UUID (FK → company)
  exposure_type: enum(geo, sector, combined)
  direction: enum(positive, negative, neutral)
  magnitude: float (0.0 – 1.0)
  price_change_t1d: float (null at creation, filled by Tier-3 calibration)

company (relevant fields):
  company_id: UUID
  sector_internal: string
  sector_gics: string
  geo_revenue: JSONB  -- e.g. {"US": 0.6, "Middle East": 0.3, "Europe": 0.1}
```

## Process Sequence
1. Exposure engine receives classified event (geo_regions[], affected_sectors[], sentiment)
2. Query company table for all is_tracked = true companies
3. For each company, compute geo exposure weight from geo_revenue JSONB × event geo_regions[]
4. For each company, compute sector match against affected_sectors[]
5. Combine into magnitude score; apply direction from sentiment × sector impact model
6. Filter out companies below exposure threshold
7. Atomically persist geo_event row + all event_exposure rows (step 6 of pipeline)

## Subtasks
- [ ] ST-001: Implement geo exposure calculation from geo_revenue JSONB × event geo_regions — complexity: M
- [ ] ST-002: Implement sector exposure match logic — complexity: S
- [ ] ST-003: Implement combined magnitude and direction computation — complexity: S
- [ ] ST-004: Implement atomic persistence of geo_event + event_exposure rows — complexity: S
- [ ] ST-005: Unit tests for exposure calculation with varied geo_revenue distributions and sector configurations — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | §Data Entities (company, event_exposure, geo_event) | Field definitions for geo_revenue JSONB, exposure_type, magnitude |
| architectural-considerations-digest.md | §System Behaviours Required | Stage-gate latency target for steps 5-6, pipeline step description |
