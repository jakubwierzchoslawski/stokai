---
req_id: REQ-F-020
slug: progressive-disclosure-ui
title: Progressive Disclosure UI (Popup, Side Panel, Deep Dive)
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "intelligence-map: Popup is triggered from map pulse click" }
  - { id: "", reason: "evaluation-framework: Why this read audit trail requires stored reasoning chain" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [frontend, ux, disclosure]
  story_points:
  components: [frontend, intelligence-map]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Progressive Disclosure UI (Popup, Side Panel, Deep Dive)

## Domain Context
The UI depth follows a three-level progressive disclosure model: pulse → popup (3-second read) → side panel (30-second read) → full analysis deep dive. The user controls depth. Every recommendation must have a traceable "why" explanation reachable in one click.

## Summary
The system must implement three UI depth levels: a 3-second-read popup showing event essentials + "Expand" button, a 30-second-read side panel showing full analysis + "Why this read?" audit trail link, and a full deep-dive analysis page; each level opened voluntarily by the user from the previous level.

## Detailed Description
As specified in ui-design-digest.md §Business Rules items 2–4, 16–19 and §System Behaviours Required:

**Popup (3-second read):**
- Triggered by clicking a map pulse
- Contains: category, intensity badge, headline, time ago, location, number of holdings exposed, ticker symbols with score delta, AI one-word action signal, confidence level
- "Expand" button opens side panel

**Side Panel (30-second read):**
- Collapsed by default; opened by "Expand" from popup
- Contains: event summary, T±7 day price sparklines for exposed companies, AI action signal, confidence, sample_size, recommendation rationale, historical analogies (top 3), affected companies with custom scores, "Why this read?" audit trail link
- When AI read is contrarian: leads with "history says" callout box showing contrarian interpretation and supporting statistics
- When social sources enabled: shows triggering social posts with timestamps

**"Why this read?" Audit Trail:**
- Opens full audit trail view
- Shows: historical analogs with similarity scores, prompt version (SHA) used, agent reasoning chain, Langfuse trace link

**Full Deep Dive:**
- Accessible from side panel
- Shows complete analysis memo (from event-deep-dive-workflow if available, or on-demand analysis)
- Includes scenario tree, full analogy table, per-company breakdowns

## Desired Outcome
Users progressively access event detail at their chosen depth without being overwhelmed, with full transparency into AI reasoning available within one additional click from any level.

## Acceptance Criteria
- [ ] AC-001: Given a user clicks a map pulse, the popup renders within 300ms with category, intensity, headline, exposed holdings count, ticker symbols with score delta, action signal, and confidence; the side panel is collapsed.
- [ ] AC-002: Given a user clicks "Expand" in the popup, the side panel opens showing the full analysis content including sparklines, analogies, and confidence; "Why this read?" link is visible.
- [ ] AC-003: Given a user clicks "Why this read?", a view opens showing: historical analogs with similarity scores, the prompt SHA that was used, and the agent reasoning steps stored from the workflow run.
- [ ] AC-004: Given the AI recommendation is contrarian to the naive interpretation, the side panel leads with a highlighted "history says" callout block before the main recommendation text.
- [ ] AC-005: Given sample_size < 5 for the event's analogies, the popup and side panel both display the low-sample disclaimer inline with the recommendation.

## Out of Scope
- In-panel trading actions (no trade execution)
- Side panel as a standalone page (it is a panel overlay over the map)

## Data Models
```
PopupData:
  event_id: UUID
  category: string[]
  intensity: int
  headline: string
  time_ago: string
  location: string
  exposed_holdings_count: int
  tickers_with_delta: list[{ticker, score_delta}]
  action_signal: string
  confidence: float
  sample_size: int
  low_sample: bool

SidePanelData (extends PopupData):
  summary: text
  sparklines: list[{ticker, ohlcv_7d}]
  rationale: text
  analogies: list[AnalogSummary]
  affected_companies: list[{company, score, delta}]
  is_contrarian: bool
  contrarian_callout: text | null
  social_posts: list[SocialPost] | null  -- only if social enabled
  audit_trail_url: string
```

## Process Sequence
1. User clicks pulse → popup renders from cached event data
2. User clicks Expand → side panel slides open; full analysis loaded from API
3. User clicks "Why this read?" → audit trail view fetched from Langfuse + DB
4. User navigates to full analysis → deep-dive memo displayed (if available)

## Subtasks
- [ ] ST-001: Implement popup component with all required fields — complexity: M
- [ ] ST-002: Implement side panel component (collapsible, 30-second content budget) — complexity: L
- [ ] ST-003: Implement "Why this read?" audit trail view — complexity: M
- [ ] ST-004: Implement contrarian callout logic — complexity: S
- [ ] ST-005: Implement low-sample disclaimer in popup and side panel — complexity: S
- [ ] ST-006: Implement social posts section (conditional on social source enabled) — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | §Business Rules items 2-4, 16-19; §System Behaviours Required | Popup content, side panel content, audit trail, contrarian callout, 3s/30s read constraints |
