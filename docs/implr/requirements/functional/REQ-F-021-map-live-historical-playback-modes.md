---
req_id: REQ-F-021
slug: map-live-historical-playback-modes
title: Map Live, Historical, and Playback Modes
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - ui-design-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "intelligence-map: Map must exist before modes can be added" }
  - { id: "", reason: "scoring-engine-and-indicator-builder: Score history required for historical mode" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, map, historical, playback]
  story_points:
  components: [intelligence-map, frontend]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Map Live, Historical, and Playback Modes

## Domain Context
The map supports three time modes: Live (WebSocket real-time), Historical (date-range slider, companies colored by score at selected time), and Playback (animated forward at 1×/4×/16×). Historical and Playback modes require score history storage.

## Summary
The system must implement three map time modes: Live (real-time WebSocket pulses), Historical (date-range slider with companies colored by score-at-time), and Playback (animated forward at 1×/4×/16× speed), with meaningful empty/quiet states in all modes.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 20–24 and §System Behaviours Required:

**Live Mode:**
- WebSocket connection delivers real-time event pulses
- Default mode on app load
- Events appear as new pulses within seconds of pipeline processing

**Historical Mode:**
- Date-range slider (from_date, to_date)
- Map renders events that occurred in the selected range
- Company markers colored by their company_score at the selected time (time-machine isolation)
- Requires score history stored in the DB with timestamps

**Playback Mode:**
- User selects a date window and clicks Play
- Map animates forward through events in chronological order
- Speed control: 1× (real-time equivalent), 4×, 16×
- Play/Pause/Reset controls
- Pulse animation rate simulates the event's original recency

**Empty/quiet state (all modes):**
- If no events exist for the selected time/filter: human-readable contextual message
- Example: "Quiet session. 2 low-intensity events near your holdings"
- Never a blank map or an error state

## Desired Outcome
Users can explore the Intelligence Map in real-time, investigate past events historically, and replay market periods at speed, enabling pattern recognition and educational use of the historical archive.

## Acceptance Criteria
- [ ] AC-001: Given Live mode is active, the WebSocket connection is established on load and new event pulses appear on the map within 5 seconds of the event being processed.
- [ ] AC-002: Given Historical mode and a date range is selected, events within the range render as static pulses; company markers display their company_score value from the closest timestamp in the score history table for the selected date.
- [ ] AC-003: Given Playback mode is started, events appear chronologically; at 16× speed a 1-hour window of events plays in approximately 3.75 minutes; Play/Pause/Reset controls function correctly.
- [ ] AC-004: Given any mode and the current filter/date produces zero events, the map displays a contextual human-readable message rather than a blank canvas.
- [ ] AC-005: Given Historical mode, switching back to Live mode reconnects the WebSocket and resumes real-time event delivery without requiring a page reload.

## Out of Scope
- Historical playback at granularity finer than per-event (tick-level replay)
- Offline map mode

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | What is the retention period, granularity, and storage strategy for score history required by Historical mode? No document specifies these. | root-synthesis §Ambiguities Detected: "Score history retention period, granularity, and storage strategy for Historical mode time-machine unspecified" | 2026-06-02 | ✅ 2026-06-02: Event-driven snapshots — a company_score row is written only on score change; TimescaleDB retention policy drops rows older than 2 years. (ARCHITECTURE.md D4) |

## Data Models
```
company_score_history (required for Historical mode):
  company_id: UUID
  indicator_id: UUID
  score: float
  geo_adjusted: float
  scored_at: timestamp  -- TimescaleDB hypertable recommended

TimeMode:
  type: enum(live, historical, playback)
  from_date: ISO date | null
  to_date: ISO date | null
  playback_speed: enum(1x, 4x, 16x) | null
```

## Process Sequence
1. User selects time mode from map toolbar
2. Live: WebSocket reconnected (if switching from Historical/Playback)
3. Historical: date range submitted to API; events + score-at-time loaded
4. Playback: date window loaded; animation timer initialised with selected speed
5. Playback tick: advance time window, show events up to current tick time
6. Empty state check at each render: if no events → display contextual message

## Subtasks
- [ ] ST-001: Implement Live mode WebSocket connection and pulse rendering — complexity: M
- [ ] ST-002: Implement Historical mode date range slider and event/score query — complexity: M
- [ ] ST-003: Implement score-at-time lookup (company_score_history table) — complexity: M
- [ ] ST-004: Implement Playback mode animation engine with 1×/4×/16× speed — complexity: L
- [ ] ST-005: Implement mode switching (Live ↔ Historical ↔ Playback) without page reload — complexity: M
- [ ] ST-006: Implement empty/quiet state message rendering for all modes — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 20-24; §System Behaviours Required | Live/Historical/Playback definitions, speed controls, score-at-time, empty states |
| system-description-digest.md | §System Behaviours Required | Map time modes, WebSocket real-time, score history requirement |
