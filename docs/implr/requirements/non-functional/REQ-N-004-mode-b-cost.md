---
req_id: REQ-N-004
slug: n-mode-b-cost
title: Mode B Per-Report Cost Ceiling and User Budget
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "morning-brief-workflow: Primary Mode B workflow with $1.50–$2.00 ceiling" }
  - { id: "", reason: "agent-registry-and-definitions: Per-agent cost_ceiling_usd" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, cost, mode-b]
  story_points:
  components: [workflows, cost-management]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Mode B Per-Report Cost Ceiling and User Budget

## Domain Context
Mode B workflows use Opus 4.7 for reasoning-heavy agents, incurring significantly higher per-token costs than Mode A. Per-report ceilings and per-user daily budgets prevent runaway expenditure.

## Summary
Mode B workflows must not exceed per-report cost ceilings ($1.00 Watchlist; $1.50 On-Demand/Earnings; $2.00 Deep-Dive). Per-user daily budget enforced: alert at daily_alert_threshold_pct; hard stop at daily_hard_stop_pct. No further AI-cost workflows dispatched after hard stop.

## Detailed Description
As specified in architectural-considerations-digest.md business rules 2, 3, 24 and system behaviours required, per-workflow cost ceilings:
- Watchlist Scan: $1.00
- On-Demand Analysis: $1.50
- Morning Brief: $1.50–$2.00 (target $1.50, ceiling $2.00)
- Earnings Brief: $1.50
- Event Deep-Dive: $2.00
- Cost has to adjustable, monthly costs shoud not be higher than 100$ for ai model, infrastructure

Per-user daily cost enforcement:
- daily_budget_usd: configurable daily spending limit per user
- daily_alert_threshold_pct: percentage at which an alert is sent (e.g. 80%)
- daily_hard_stop_pct: percentage at which no further workflows are dispatched for that user (100%)

Workflow cost is recorded in workflow_run.cost_usd. When a workflow's running cost reaches its ceiling mid-execution, it is terminated with a cost-exceeded flag and partial results stored.

## Desired Outcome
No Mode B workflow run produces API charges exceeding its per-report ceiling, and no user can inadvertently incur unlimited daily AI costs.

## Acceptance Criteria
- [ ] AC-001: Given an Event Deep-Dive workflow reaches $2.00 in accumulated AI cost before completion, the workflow is terminated immediately, partial results are stored with cost_limited=true, and the admin is notified.
- [ ] AC-002: Given a user's accumulated daily AI cost reaches daily_alert_threshold_pct (e.g. 80%) of daily_budget_usd, an alert is sent to the admin cost monitor; workflows continue to dispatch.
- [ ] AC-003: Given a user's accumulated daily AI cost reaches daily_hard_stop_pct (100%) of daily_budget_usd, no further AI-cost-incurring workflows are dispatched for that user for the remainder of the calendar day.
- [ ] AC-004: Given 50 consecutive Morning Brief runs, the maximum recorded cost per run does not exceed $2.00; the mean is ≤$1.50.

## Out of Scope
- Per-user billing (MVP is single-tenant; cost enforcement is operational, not billing)
- Infrastructure cost per user (covered by n-infrastructure-budget)

## NFR-Specific Fields

### Measurable Target
- Watchlist Scan: ≤$1.00 per run (hard ceiling)
- On-Demand Analysis: ≤$1.50 per run (hard ceiling)
- Morning Brief: ≤$2.00 per run (hard ceiling); target ≤$1.50
- Earnings Brief: ≤$1.50 per run (hard ceiling)
- Event Deep-Dive: ≤$2.00 per run (hard ceiling)
- Per-user daily: alert at daily_alert_threshold_pct; hard stop at daily_hard_stop_pct

### Verification Method
- Method: workflow_run.cost_usd monitored per run; automated tests asserting ceiling enforcement
- Tool/Process: pytest integration tests with cost ceiling assertion; admin cost monitor; Langfuse per-run cost breakdown
- Frequency: Continuous (every production workflow tracked); per-release
- Owner: DevOps / QA

### Category Rationale
Reliability NFR because uncontrolled AI costs directly threaten the system's economic viability. The $0.50–$2.00 ceiling per report ensures Mode B cost remains predictable and within the overall $100/month budget.

## Subtasks
- [ ] ST-001: Implement per-workflow cost accumulator with hard-stop termination — complexity: M
- [ ] ST-002: Implement per-user daily budget tracking and alert/hard-stop logic — complexity: M
- [ ] ST-003: Integration tests for cost ceiling enforcement per workflow type — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rules 3, 24; System Behaviours Required (budgets per workflow) | Per-workflow cost ceilings, per-user daily budget enforcement |
