---
req_id: REQ-N-002
slug: n-mode-b-latency
title: Mode B Workflow Latency
type: non-functional
nfr_category: Performance
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "morning-brief-workflow: Primary Mode B workflow being measured" }
  - { id: "", reason: "on-demand-analysis-workflow: On-demand latency target" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, performance, mode-b]
  story_points:
  components: [workflows, performance]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Mode B Workflow Latency

## Domain Context
Mode B deliberative workflows must complete within defined hard latency limits to meet delivery targets. Targets and hard limits differ: target is the expected happy-path duration; hard limit is the absolute ceiling after which the workflow is terminated.

## Summary
Mode B workflow hard latency limits: Morning Brief ≤10 minutes; On-Demand ≤6 minutes; Watchlist Scan ≤8 minutes; Earnings Brief ≤10 minutes; Event Deep-Dive ≤15 minutes.

## Detailed Description
As specified in architectural-considerations-digest.md system behaviours required:
- Morning Brief: target 4–5 min, hard limit 10 min
- On-Demand: target 3–4 min, hard limit 6 min
- Watchlist Scan: target 3 min, hard limit 8 min
- Earnings Brief: target 4 min, hard limit 10 min
- Event Deep-Dive: target 5–7 min, hard limit 15 min

Hard limits are enforced by per-workflow timeout on the Celery task. When reached, workflow terminates, partial results are stored, and the admin AI audit console records the timeout.

## Desired Outcome
Mode B workflows reliably complete and deliver output within the delivery window, with hard limits preventing runaway workflows from consuming excessive resources.

## Acceptance Criteria
- [ ] AC-001: Given 50 consecutive Morning Brief runs, p95 completion time is ≤5 minutes; no run exceeds the 10-minute hard limit without being terminated.
- [ ] AC-002: Given an On-Demand analysis is triggered, the result is available within 4 minutes at p95 and never takes longer than 6 minutes before returning a partial or terminated result.
- [ ] AC-003: Given any Mode B workflow reaches its hard time limit, the Celery task is terminated, partial results are stored with a timeout flag, and the admin AI audit console records the event within 60 seconds.
- [ ] AC-004: Given Watchlist Scan runs at 17:30, it completes and dispatches within 8 minutes at p95, ensuring delivery by 18:00.

## Out of Scope
- Real-time user-facing latency dashboard

## NFR-Specific Fields

### Measurable Target
- Morning Brief hard limit: ≤10 minutes; target ≤5 minutes
- On-Demand hard limit: ≤6 minutes; target ≤4 minutes
- Watchlist Scan hard limit: ≤8 minutes; target ≤3 minutes
- Earnings Brief hard limit: ≤10 minutes; target ≤4 minutes
- Event Deep-Dive hard limit: ≤15 minutes; target ≤7 minutes
- All limits: p95 over 30-day rolling window in production

### Verification Method
- Method: Automated workflow timing tests + production Langfuse trace analysis
- Tool/Process: pytest workflow integration tests with timing assertions; Langfuse latency dashboards per workflow type
- Frequency: Per release (integration tests); continuous (Langfuse production monitoring)
- Owner: QA / DevOps

### Category Rationale
Performance NFR because Mode B delivery windows are product commitments (06:00 Morning Brief, 18:00 Watchlist) and hard limits prevent runaway cost accrual from long-running workflows.

## Subtasks
- [ ] ST-001: Implement Celery task timeout per workflow type — complexity: S
- [ ] ST-002: Implement timeout recording in admin AI audit console — complexity: S
- [ ] ST-003: Create per-workflow latency test suite — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | System Behaviours Required (Mode B budgets) | All five workflow targets and hard limits |
