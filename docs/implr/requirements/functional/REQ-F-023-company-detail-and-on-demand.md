---
req_id: REQ-F-023
slug: company-detail-and-on-demand
title: Company Detail Screen and On-Demand Analysis Trigger
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "on-demand-analysis-workflow: On-demand analysis triggered from this screen" }
  - { id: "", reason: "scoring-engine-and-indicator-builder: Score breakdown required" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, company-detail]
  story_points:
  components: [frontend, company-detail]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Company Detail Screen and On-Demand Analysis Trigger

## Domain Context
The Company Detail screen is the deepest drill-down for a specific company. It aggregates price history, fundamentals, all custom scores, active events, AI analysis history, and recommendation track record. The On-Demand Analysis workflow is triggered exclusively from this screen.

## Summary
The system must provide a Company Detail screen showing price chart, fundamentals, all custom scores with breakdown, active events, AI analysis history, and recommendation track record; and a button that triggers the On-Demand Analysis workflow for that company.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 31–32:

**Price Chart:**
- Interactive OHLCV chart (Recharts or visx)
- Configurable time range
- Overlays: active events (vertical markers), score change markers

**Fundamentals Panel:**
- P/E, EPS, Revenue, Debt/Equity, and other fetched fundamentals
- Data sourced via FMP (primary) or SEC EDGAR cross-validation

**Custom Scores Panel:**
- All active scoring profile scores for the company
- Score breakdown: which indicators contribute, with weights
- Score history sparkline (last 30 days)

**Active Events:**
- List of geo_events currently affecting the company
- Each event links to map pulse and popup

**AI Analysis History:**
- All previous on-demand and workflow-generated analyses for this company
- Each entry shows: date, type, action signal, confidence, brief summary

**Recommendation Track Record:**
- Past recommendations with actual_t1d and actual_t1w outcomes
- Directional accuracy summary

**On-Demand Analysis Button:**
- Single "Analyze Now" button
- Triggers on-demand-analysis-workflow
- Shows loading state; delivers report when complete

## Desired Outcome
A user viewing a company's detail page has complete context — price history, scores, active events, and AI analysis history — and can trigger fresh analysis with a single click.

## Acceptance Criteria
- [ ] AC-001: Given a user navigates to a Company Detail page, the screen displays price chart, fundamentals, all custom scores with indicator breakdown, active events, and AI analysis history for that company.
- [ ] AC-002: Given a user clicks "Analyze Now", the on-demand analysis workflow is triggered, a loading indicator is shown, and the resulting report is appended to the AI analysis history when complete.
- [ ] AC-003: Given a past AI recommendation exists for the company with an available actual_t1d outcome, the Recommendation Track Record section shows whether the directional call was correct.
- [ ] AC-004: Given the score breakdown panel is expanded, it shows each contributing indicator's name, formula summary, weight, and its sub-score contribution to the total.

## Out of Scope
- Trade execution from Company Detail (no broker integration in MVP)
- Comparison of multiple companies side-by-side

## Data Models
```
CompanyDetailView:
  company: Company
  price_history: list[price_bar]
  fundamentals: JSONB
  scores: list[{indicator, score, breakdown}]
  active_events: list[geo_event]
  analysis_history: list[ai_recommendation]
  recommendation_track_record: list[{signal, confidence, actual_t1d, correct}]
```

## Process Sequence
1. User navigates to /company/{company_id}
2. Page fetches price history, fundamentals, scores, active events, analysis history in parallel
3. UI renders all panels
4. User clicks "Analyze Now" → POST /workflows/on-demand/{company_id}
5. Loading state shown; WebSocket or polling for result
6. Report displayed when complete; AI analysis history updated

## Subtasks
- [ ] ST-001: Implement Company Detail API endpoint aggregating all required data — complexity: M
- [ ] ST-002: Implement frontend Company Detail page with all panels — complexity: L
- [ ] ST-003: Implement score breakdown panel — complexity: M
- [ ] ST-004: Implement recommendation track record panel — complexity: S
- [ ] ST-005: Implement "Analyze Now" button with loading state — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 31-32 | All panel content, On-Demand Analysis trigger from Company Detail |
