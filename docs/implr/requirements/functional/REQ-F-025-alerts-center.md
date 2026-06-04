---
req_id: REQ-F-025
slug: alerts-center
title: Alerts Center
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "alert-dispatch-anti-fatigue: Alert rows must be persisted before Alerts Center can list them" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, alerts]
  story_points:
  components: [alerts-center, frontend]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Alerts Center

## Domain Context
The Alerts Center lists all fired alerts with links back to the originating map event or report. Alert rule management (create/edit thresholds, quiet hours, channels) lives here or in settings.

## Summary
The system must provide an Alerts Center screen listing all fired alerts linked to the originating map event or report, and alert rule management for creating/editing rules with thresholds, quiet hours, and notification channels.

## Detailed Description
As specified in ui-design-digest.md §Business Rules item 35:

**Alerts List:**
- Chronological list of all fired alerts for the user
- Each alert shows: timestamp, event title, action signal, confidence, channel (email/push), status (dispatched/suppressed)
- Each alert links to the originating map event pulse (deep-link to map at event location) or report
- Filter by: date range, status, action signal type

**Alert Rule Management:**
- Create new alert rule: define event category filter, intensity threshold, ticker list (empty = all portfolio), notification channel
- Edit existing rules
- Per-rule quiet hours configuration
- Per-ticker alert frequency threshold
- Rules listed with status (enabled/disabled)

**Anti-Fatigue Settings Integration:**
- Daily push limit configuration
- Overall quiet hours (applies to all rules unless rule overrides)
- Deduplication window setting

## Desired Outcome
Users have full visibility into their alert history and can configure, fine-tune, and disable alert rules to manage notification volume according to their preferences.

## Acceptance Criteria
- [ ] AC-001: Given alerts have been fired, the Alerts Center lists them chronologically with event title, action signal, confidence, channel, and status; each row links to the originating map event or report.
- [ ] AC-002: Given a user clicks an alert's event link, the map navigates to the event location and opens the popup for that event.
- [ ] AC-003: Given a user creates a new alert rule with intensity_min=4 and a ticker list, the rule is saved and subsequent Mode A alerts matching that criteria are evaluated against the rule.
- [ ] AC-004: Given a user edits quiet hours on an existing rule, the updated quiet hours apply to all future alert evaluations for that rule starting immediately.
- [ ] AC-005: Given a user filters alerts by status=suppressed, only suppressed alerts are shown in the list.

## Out of Scope
- Push notification configuration (channel available but delivery deferred to phase 2)
- SMS alert rules (deferred to phase 2)
- Historical alert analytics/reporting

## Data Models
```
alert (frontend view adds):
  event_link: string  -- /map?event={event_id}
  report_link: string | null

alert_rule:
  rule_id: UUID
  user_id: UUID
  name: string
  enabled: bool
  event_category_filter: string[]
  intensity_min: int
  ticker_list: string[]
  quiet_hours_start: time
  quiet_hours_end: time
  per_ticker_interval_hours: int
  channels: string[]
```

## Process Sequence
1. User navigates to Alerts Center
2. Alerts loaded from API (paginated, filterable)
3. User clicks event link → map deep-link to event
4. User navigates to alert rule management tab
5. CRUD operations on alert rules via API

## Subtasks
- [ ] ST-001: Implement Alerts Center API endpoint with filters — complexity: S
- [ ] ST-002: Implement alert rule CRUD API — complexity: M
- [ ] ST-003: Implement frontend Alerts Center list with filter controls — complexity: M
- [ ] ST-004: Implement alert-to-map deep-link navigation — complexity: S
- [ ] ST-005: Implement anti-fatigue settings UI — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules item 35, 36 | Alert list requirements, rule management, anti-fatigue settings |
