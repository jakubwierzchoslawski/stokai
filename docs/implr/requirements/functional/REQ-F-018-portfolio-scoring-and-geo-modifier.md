---
req_id: REQ-F-018
slug: portfolio-scoring-and-geo-modifier
title: Portfolio Scoring and Real-Time Geo-Modifier
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - system-description-digest.md
dependencies:
  - { id: "", reason: "scoring-engine-and-indicator-builder: Base scoring engine must exist" }
  - { id: "", reason: "exposure-mapping: event_exposure rows required for geo-modifier inputs" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, scoring, real-time]
  story_points:
  components: [scoring]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Portfolio Scoring and Real-Time Geo-Modifier

## Domain Context
When a geopolitical event fires, affected companies' scores must be updated in real-time via geo-modifier without requiring full recalculation. This is the mechanism that makes the Intelligence Map colors change in response to events.

## Summary
The system must apply a real-time geo-modifier when a geopolitical event fires: geo_revenue × sector_exposure × event_intensity → magnitude_adjustment applied to affected company_score rows, propagated to the map via WebSocket, without triggering full score recalculation.

## Detailed Description
As described in system-description-digest.md §Business Rules item 14 and §Architecture Signals, computed scores are invalidated event-driven. The geo-modifier is the mechanism: instead of recomputing the full DSL formula from scratch, the geo-adjustment is applied as a multiplicative modifier to the existing base score.

Formula: `geo_adjusted = base_score × (1 + geo_weight × magnitude × direction_sign)`

Where:
- `base_score`: current company_score.score before geo-modification
- `geo_weight`: indicator.geo_weight field
- `magnitude`: event_exposure.magnitude (0–1) for the (event, company) pair
- `direction_sign`: +1 for positive events on company, -1 for negative events

The updated geo_adjusted field in company_score is written. A WebSocket push notifies subscribed map clients of the score change, triggering map color updates for affected companies.

Score invalidation is selective: only company_score rows for companies in the event_exposure result are updated. All other companies' scores remain unchanged.

## Desired Outcome
Within seconds of a geopolitical event being processed, the Intelligence Map reflects updated company scores for affected holdings, giving users an immediate visual signal of which positions are impacted.

## Acceptance Criteria
- [ ] AC-001: Given a geo_event is persisted with associated event_exposure rows, company_score.geo_adjusted is updated for all exposed companies within 5 seconds, without triggering a full DSL formula recalculation.
- [ ] AC-002: Given the geo_adjusted scores are updated, a WebSocket message is sent to subscribed clients with the updated score values for affected companies, causing map marker colors to update.
- [ ] AC-003: Given companies not in the event_exposure set, their company_score rows are not touched or re-computed during the geo-modifier application.
- [ ] AC-004: Given event intensity is 5 and geo_weight is 1.0, the geo_adjusted score change is measurable and visually distinct on the map from an intensity-1 event.
- [ ] AC-005: Given the scoring profile changes, the geo-modifier is reapplied using the new profile's geo_weight values without requiring a new event.

## Out of Scope
- Full DSL formula recalculation (only geo-modifier applied in real-time; full recalc is separate)
- Historical score recalculation for past events

## Data Models
```
company_score (relevant fields):
  company_id: UUID
  indicator_id: UUID
  score: float          -- base score (from DSL evaluation)
  geo_adjusted: float   -- score after geo-modifier applied
  inputs_hash: string
  computed_at: timestamp

GeoModifierPayload (WebSocket):
  event_id: UUID
  affected_companies: list[{company_id, ticker, new_geo_adjusted, score_delta}]
```

## Process Sequence
1. geo_event persisted; event_exposure rows available
2. Geo-modifier worker retrieves event_exposure rows for this event
3. For each (company, exposure): load company_score.score and indicator.geo_weight
4. Compute geo_adjusted = base_score × (1 + geo_weight × magnitude × direction_sign)
5. Update company_score.geo_adjusted (targeted write, not full recalc)
6. WebSocket push: broadcast updated scores to subscribed map clients
7. Map re-renders affected company markers with new color/score

## Subtasks
- [ ] ST-001: Implement geo-modifier computation function — complexity: S
- [ ] ST-002: Implement event-driven trigger: on event_exposure write → dispatch geo-modifier task — complexity: S
- [ ] ST-003: Implement targeted company_score.geo_adjusted update (no full DSL recalc) — complexity: M
- [ ] ST-004: Implement WebSocket push for geo-modifier score updates — complexity: M
- [ ] ST-005: Unit tests for geo-modifier formula with varied magnitude/intensity/direction — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | §Business Rules item 14; §Architecture Signals | Event-driven invalidation, geo-modifier, no full recalculation cycle |
| system-description-digest.md | §Data Entities (company_score, indicator) | geo_adjusted field, geo_weight parameter |
