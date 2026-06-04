---
req_id: REQ-F-009
slug: earnings-risk-brief-workflow
title: Earnings Risk Brief Workflow (Mode B)
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "agent-registry-and-definitions: Earnings Context Agent must be defined" }
  - { id: "", reason: "portfolio-and-watchlist-management: Portfolio companies with T+1 earnings needed" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [backend, ai, mode-b, earnings, cron]
  story_points:
  components: [workflows, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Earnings Risk Brief Workflow (Mode B)

## Domain Context
A daily cron-triggered Mode B deliberative workflow for portfolio companies with T+1 earnings events. Earnings Context Agent (Opus 4.7) generates a macro/sector scenario tree. Hard latency limit ≤10 minutes; cost ceiling $1.50.

## Summary
The system must daily identify portfolio companies with earnings scheduled for T+1, execute an Earnings Risk Brief LangGraph workflow per company using the Earnings Context Agent to build a macro/sector scenario tree, and deliver the brief within 4 minutes at a cost ≤$1.50.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules item 20 and §System Behaviours Required (budget: 4 min, $1.50), this workflow triggers daily for all portfolio companies that have earnings events scheduled for the next trading day.

The Earnings Context Agent (Opus 4.7) is the primary agent, constructing a scenario tree covering:
- Macro conditions at earnings date
- Sector performance context
- Bull/base/bear scenarios with probability weights
- Historical earnings surprise analogies

Agent chain: Earnings Context Agent → Historical Context Agent → Recommendation Synthesizer → evaluate_quality → Narrative Writer.

One brief per qualifying company. HIL routing applies. Hard limit 10 minutes per architectural-considerations-digest.md §System Behaviours Required.

## Desired Outcome
Users with portfolio companies entering earnings the next day receive a pre-earnings risk brief with scenario analysis, delivered the evening before, enabling informed decision-making before the earnings event.

## Acceptance Criteria
- [ ] AC-001: Given portfolio companies with T+1 earnings events, the system triggers an earnings brief workflow for each qualifying company daily, completing within 4 minutes and $1.50 per company.
- [ ] AC-002: Given the Earnings Context Agent runs, the output includes a structured scenario tree with at minimum bull, base, and bear scenarios each with a probability weight and macro/sector rationale.
- [ ] AC-003: Given the evaluate_quality node produces confidence ≥ 0.7, the brief is auto-delivered; confidence 0.4–0.69 routes to HIL queue; confidence < 0.4 is blocked.
- [ ] AC-004: Given no portfolio companies have T+1 earnings, no earnings brief workflow is triggered and no cost is incurred.
- [ ] AC-005: Given the workflow hard limit (10 minutes) is reached before completion, the workflow is terminated and the admin AI audit console records the timeout.

## Out of Scope
- Earnings calendars for non-portfolio companies
- Post-earnings analysis workflow (separate requirement)
- Real-time earnings announcement monitoring (Mode A handles anomaly detection)

## Data Models
```
WorkflowState (standard, with scenario_tree in inputs/outputs)

EarningsScenario:
  company_id: UUID
  earnings_date: date
  scenario_tree: JSONB  -- {bull: {prob, rationale}, base: {...}, bear: {...}}
  macro_context: text
  sector_context: text
  analogies: JSONB
  confidence: float
```

## Process Sequence
1. Daily cron identifies portfolio companies with T+1 earnings (via earnings calendar data)
2. Celery dispatches Earnings Risk Brief task per qualifying company
3. Earnings Context Agent (Opus 4.7) builds scenario tree
4. Historical Context Agent retrieves earnings analogies
5. Recommendation Synthesizer synthesizes pre-earnings action signal
6. evaluate_quality assesses confidence
7. Narrative Writer generates brief
8. Brief delivered or routed to HIL queue per confidence threshold

## Subtasks
- [ ] ST-001: Implement daily T+1 earnings detection query — complexity: S
- [ ] ST-002: Implement Earnings Context Agent (Opus 4.7) with scenario tree output schema — complexity: L
- [ ] ST-003: Implement LangGraph StateGraph for earnings brief workflow — complexity: L
- [ ] ST-004: Implement cost ceiling ($1.50) and hard timeout (10 min) enforcement — complexity: S
- [ ] ST-005: Integration test: multiple companies with earnings, no earnings case — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules item 20; §System Behaviours Required | Daily cron T+1 earnings, 4 min $1.50 budget, 10 min hard limit, Earnings Context Agent |
