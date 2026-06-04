---
req_id: REQ-F-022
slug: screener
title: Company Screener
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "scoring-engine-and-indicator-builder: Scores required for company rows" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, screener, data]
  story_points:
  components: [screener, frontend]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Company Screener

## Domain Context
The Screener is a sortable/filterable company table reachable from the map ("show in screener" button) and from the top navigation bar. When launched from a map event context it pre-filters to that event's affected companies.

## Summary
The system must provide a sortable, filterable company screener table with AND/OR operator composition for filters, pre-filtering to the triggering event's affected companies when launched from map context, and CSV export.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 25–27 and system-description-digest.md §System Behaviours Required:

The Screener shows all tracked companies (~100–200) with:
- Company name, ticker, sector, market cap
- Current custom score(s) per active scoring profile
- Price (15-min delayed by default)
- Active events touching the company (count + indicator)
- Custom score delta since last session

Filter capabilities:
- Filter by any displayed column
- AND/OR operator composition for multi-filter
- Preset filters: "affected by [event name]" when launched from map

Sort capabilities:
- Click any column header to sort ascending/descending
- Multi-column sort not required in MVP

When the Screener is entered from a map event ("show in screener" button on popup or side panel), it pre-filters to that event's affected companies sorted by custom score descending.

CSV export: exports current filtered + sorted view.

## Desired Outcome
Users can discover, compare, and export company data with flexible filtering, and immediately see which companies are affected by a specific event when navigating from the map.

## Acceptance Criteria
- [ ] AC-001: Given the user navigates to the Screener from the top nav, it displays all tracked companies with name, ticker, sector, custom score, current price, and active events count.
- [ ] AC-002: Given the user applies two filters with AND/OR composition, the company list updates to show only companies matching the combined filter criteria.
- [ ] AC-003: Given the user opens the Screener from a map event ("show in screener" button), the Screener pre-filters to the event's affected companies sorted by custom score descending.
- [ ] AC-004: Given the user clicks "Export CSV", a CSV file downloads containing the current filtered and sorted company rows with all visible columns.
- [ ] AC-005: Given the user clicks a column header, the table sorts by that column; clicking again reverses sort order.

## Out of Scope
- Real-time price data in screener (15-min delayed in MVP)
- Screening by non-tracked on-demand companies
- Saved screener filter presets (phase 2)

## Data Models
```
ScreenerRow:
  company_id: UUID
  ticker: string
  name: string
  sector: string
  market_cap: float
  custom_score: float
  score_delta: float
  current_price: float (15-min delayed)
  active_events_count: int
  active_event_categories: string[]

ScreenerFilter:
  column: string
  operator: enum(eq, gt, lt, contains, in)
  value: any
  logical_op: enum(AND, OR)  -- combines with previous filter
```

## Process Sequence
1. User navigates to Screener (nav bar or map "show in screener")
2. If from map event: pre-filter applied for event's affected companies
3. Company rows loaded with scores, prices, active events
4. User applies additional filters with AND/OR composition
5. Sort by column header click
6. Export CSV: serialize current filtered view

## Subtasks
- [ ] ST-001: Implement Screener API endpoint with filter and sort parameters — complexity: M
- [ ] ST-002: Implement AND/OR filter composition logic — complexity: M
- [ ] ST-003: Implement frontend Screener table component — complexity: M
- [ ] ST-004: Implement pre-filter from map event context — complexity: S
- [ ] ST-005: Implement CSV export — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 25-27; §System Behaviours Required | Table structure, AND/OR filters, pre-filter from event, CSV export |
| system-description-digest.md | §System Behaviours Required | "show in screener" button, score sort |
