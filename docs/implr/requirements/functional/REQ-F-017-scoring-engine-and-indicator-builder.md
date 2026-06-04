---
req_id: REQ-F-017
slug: scoring-engine-and-indicator-builder
title: Scoring Engine and Indicator Builder
type: functional
status: approved
complexity: XL
tdd_required: true
source_docs:
  - system-description-digest.md
  - ui-design-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, frontend, scoring, dsl]
  story_points:
  components: [scoring, indicator-builder]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Scoring Engine and Indicator Builder

## Domain Context
The Scoring Engine is the analytical backbone that translates raw company data + geopolitical events into the scores displayed on the Intelligence Map. The DSL-based Indicator Builder allows users and admins to define custom scoring formulas. Scoring profiles switch the entire market rating and map coloring.

## Summary
The system must provide a DSL formula parser, evaluator, normalization engine (percentile/z-score/min-max), and geo-modifier; scoring profiles (Value Investor, Growth Hunter, Macro Aware); event-driven score invalidation; indicator versioning with diff and rollback; and a visual DSL editor in the frontend with live preview on 5 sample companies.

## Detailed Description
As specified in system-description-digest.md §Business Rules items 14, 15; §System Behaviours Required; and ui-design-digest.md §Business Rules items 28–30, 46:

**DSL Engine:**
- Custom DSL with arithmetic, logical, ranking, and time-series operators
- Formulas parsed and evaluated at runtime (not compiled)
- DSL parameter catalog managed by admin: add/enable/disable parameters, define derived/composite parameters, manage benchmark groups and peer sets

**Normalization Modes:**
- percentile: rank within peer group
- z-score: standard score vs benchmark
- min-max: scaled 0–100 within configured range

**Geo-Modifier:**
- Applied after base score computation
- Takes geo_event.geo_regions[] × company.geo_revenue JSONB × event.intensity → magnitude_adjustment
- Applied to company_score rows without full recalculation

**Scoring Profiles:**
- Three built-in profiles: Value Investor, Growth Hunter, Macro Aware
- Each profile selects a set of indicators and weights them
- Switching profile immediately updates map coloring and all company scores displayed
- Users can create custom profiles by composing indicators

**Indicator Versioning:**
- Every save creates a new version (version field on indicator table)
- Diff between versions: show changed DSL tokens
- Rollback to any previous version

**Visual DSL Editor (Frontend):**
- Left panel: parameter palette (browsable catalog)
- Center: formula canvas with live syntax validation
- Right panel: live score preview on 5 sample companies

**Score Invalidation:**
- Triggered by geo_event persistence (event-driven, not scheduled)
- Only affected companies (from event_exposure) have scores invalidated

## Desired Outcome
Users and admins can define, version, and apply custom scoring formulas that produce normalized, geo-adjusted company scores reflected in real-time on the Intelligence Map, with full traceability of score computation.

## Acceptance Criteria
- [ ] AC-001: Given a DSL formula string is saved, the scoring engine parses it, validates syntax, and can evaluate it against a company's data to produce a raw_value and a normalized score (0–100) within the Indicator Builder preview.
- [ ] AC-002: Given a geopolitical event fires and event_exposure rows are created, only company_score rows for affected companies are invalidated; re-scoring runs for those companies only, not the full universe.
- [ ] AC-003: Given a scoring profile is selected, all company scores on the map update to reflect the new profile's indicators and weights; the map color gradient updates within a single page navigation.
- [ ] AC-004: Given an indicator is saved a second time with formula changes, a new version is created, the previous version remains queryable, and a diff view shows the changed DSL tokens.
- [ ] AC-005: Given a DSL formula references a geo-modifier, the geo_revenue JSONB × event intensity calculation is applied to the base score, and the company_score row records both the raw_value and geo_adjusted score.
- [ ] AC-006: Given the Indicator Builder canvas, the right panel displays live score previews for 5 sample companies updating within 2 seconds of formula edits.

## Out of Scope
- Fully custom normalization modes beyond percentile/z-score/min-max
- Automated portfolio recommendation based on scoring (scoring is for display/analysis only)
- Score computation for non-tracked companies (on-demand fetch only)

## Data Models
```
indicator:
  indicator_id: UUID
  tenant_id: UUID
  name: string
  formula_dsl: text
  benchmark_mode: enum(percentile, z_score, min_max)
  normalization: JSONB  -- mode-specific parameters
  direction: enum(higher_better, lower_better)
  geo_weight: float
  version: int
  created_at: timestamp

company_score:
  company_id: UUID (FK → company)
  indicator_id: UUID (FK → indicator)
  score: float (0-100)
  raw_value: float
  percentile: float
  geo_adjusted: float
  inputs_hash: string
  computed_at: timestamp

ScoringProfile:
  profile_id: UUID
  name: string  -- e.g. "Value Investor"
  indicators: list[{indicator_id, weight}]
  version: int
```

## Process Sequence
1. Admin or user creates/edits DSL formula in Indicator Builder
2. Frontend sends formula to backend DSL parser for validation
3. Live preview computed for 5 sample companies
4. On save: new indicator version created; formula stored
5. Scoring engine evaluates formula for all tracked companies → raw_value
6. Normalization applied (percentile/z-score/min-max) → score (0–100)
7. Geo-modifier applied if geo_weight > 0 → geo_adjusted score
8. company_score rows written/updated
9. On geo_event: event-driven invalidation → targeted re-score for affected companies

## Subtasks
- [ ] ST-001: Implement DSL parser and runtime evaluator with arithmetic/logical/ranking/time-series operators — complexity: XL
- [ ] ST-002: Implement normalization engine (percentile, z-score, min-max) — complexity: M
- [ ] ST-003: Implement geo-modifier computation — complexity: M
- [ ] ST-004: Implement event-driven score invalidation trigger — complexity: M
- [ ] ST-005: Implement indicator versioning with diff and rollback — complexity: M
- [ ] ST-006: Implement scoring profiles (three built-in + custom) — complexity: M
- [ ] ST-007: Implement frontend visual DSL editor with live validation and preview — complexity: L
- [ ] ST-008: Implement DSL parameter catalog admin management — complexity: M
- [ ] ST-009: Unit tests for DSL parser, normalization, geo-modifier — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | §Business Rules items 14, 15; §System Behaviours Required; §Data Entities (indicator, company_score); §Architecture Signals | DSL, normalization, event-driven invalidation, geo-modifier, scoring profiles |
| ui-design-digest.md | §Business Rules items 28-30, 46; §System Behaviours Required | Visual editor layout, live preview, versioning, parameter catalog admin |
