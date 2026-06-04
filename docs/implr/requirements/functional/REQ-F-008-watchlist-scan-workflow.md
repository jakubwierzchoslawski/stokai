---
req_id: REQ-F-008
slug: watchlist-scan-workflow
title: Watchlist Scan Workflow (Mode B)
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "agent-registry-and-definitions: Named-role agents required" }
  - { id: "", reason: "portfolio-and-watchlist-management: Portfolio and watchlist must exist" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [backend, ai, mode-b, watchlist, cron]
  story_points:
  components: [workflows, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Watchlist Scan Workflow (Mode B)

## Domain Context
A daily cron-triggered Mode B deliberative workflow that runs at 17:30, delivering a watchlist/portfolio scan report by 18:00. Hard latency limit ≤8 minutes; cost ceiling $1.00.

## Summary
The system must execute a daily 17:30 cron-triggered LangGraph workflow that scans portfolio and watchlist events for relevance, scores affected companies, and delivers a structured digest report by 18:00, within 3 minutes and $1.00.

## Detailed Description
As described in architectural-considerations-digest.md §Business Rules item 20 and §System Behaviours Required, Watchlist Scan runs daily at 17:30. The workflow processes the day's events filtered by portfolio and watchlist relevance, re-runs exposure scoring for changed companies, and produces a digest report.

The full agent chain: Relevance Analyst → Exposure Analyst → Historical Context Agent → Recommendation Synthesizer → evaluate_quality → Narrative Writer.

The report delivery target is 18:00 (analogous to Morning Brief's 06:00 target). HIL routing applies for confidence 0.4–0.69.

Cost ceiling is $1.00 per run. Target duration is 3 minutes; hard limit 8 minutes.

## Desired Outcome
Users with active watchlist subscriptions receive a daily end-of-session digest by 18:00 covering events affecting their portfolio and watchlist companies, with action signals and confidence scores.

## Acceptance Criteria
- [ ] AC-001: Given the cron fires at 17:30, the watchlist scan workflow completes and delivers the report by 18:00 (within 3 minutes target, 8 minutes hard limit) without exceeding $1.00 cost.
- [ ] AC-002: Given the user has a portfolio and/or watchlist, the report covers only events relevant to those specific companies, not all events in the system.
- [ ] AC-003: Given the workflow produces confidence ≥ 0.7, the report is automatically delivered via email by 18:00.
- [ ] AC-004: Given the workflow produces confidence 0.4–0.69, the report enters the HIL queue; if unreviewed before the delivery deadline, it is withheld and the user is notified.
- [ ] AC-005: Given the evaluate_quality node runs second-to-last and Narrative Writer runs last, this structural pattern is enforced in the LangGraph definition.

## Out of Scope
- Intraday watchlist scanning (single daily run only in MVP)
- Multi-channel delivery beyond email in MVP

## Data Models
```
WorkflowState: (standard, scoped to user's portfolio + watchlist)

Report/Brief (DB row):
  brief_id: UUID
  type: watchlist_scan
  user_id: UUID
  content: text
  confidence: float
  hil_status: enum
  sent_at: timestamp | null
  cost_usd: float
```

## Process Sequence
1. Cron triggers at 17:30, dispatches Watchlist Scan Celery task per subscribed user
2. LangGraph workflow filters day's events by portfolio + watchlist relevance
3. Exposure Analyst computes end-of-day score changes
4. Historical Context Agent retrieves analogies for relevant events
5. Recommendation Synthesizer produces action signals
6. evaluate_quality assesses confidence
7. Confidence routing: auto-deliver / HIL queue / block
8. Narrative Writer generates report HTML (if approved)
9. Email dispatched with 18:00 delivery target

## Subtasks
- [ ] ST-001: Implement cron trigger and Celery dispatch for watchlist scan at 17:30 — complexity: S
- [ ] ST-002: Implement LangGraph StateGraph for watchlist scan workflow — complexity: L
- [ ] ST-003: Implement portfolio + watchlist event filter (relevance scoping) — complexity: M
- [ ] ST-004: Implement HIL routing with delivery-time deadline — complexity: M
- [ ] ST-005: Implement cost ceiling enforcement ($1.00) — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules item 20; §System Behaviours Required | 17:30 cron, 3 min / $1.00 budget, 8 min hard limit |
| system-description-digest.md | §System Behaviours Required | Portfolio/watchlist relevance filtering |
