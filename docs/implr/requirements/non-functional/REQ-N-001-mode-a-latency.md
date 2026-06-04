---
req_id: REQ-N-001
slug: n-mode-a-latency
title: Mode A Pipeline Latency
type: non-functional
nfr_category: Performance
status: approved
complexity: M
tdd_required: true
source_docs:
  - system-description-digest.md
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "reactive-pipeline-ingestion: The pipeline being measured" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, performance, mode-a]
  story_points:
  components: [event-pipeline, performance]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Mode A Pipeline Latency

## Domain Context
Mode A Reactive Pipeline must deliver the information edge of 20–90 minutes ahead of the average retail investor. Strict stage-gate latency budgets prevent any single step from consuming the full pipeline budget.

## Summary
The Mode A pipeline must complete end-to-end in ≤90 seconds for intensity 4–5 events; Tweet-to-alert in ≤30 seconds for TIER1 tweets; score-change alert in ≤5 minutes; SEC filing alert in ≤20 minutes.

## Detailed Description
As specified in system-description-digest.md system behaviours required and architectural-considerations-digest.md, the reactive pipeline has defined stage-gate latency budgets:
- Detection: 0–15 s
- LLM classification: 15–45 s
- Exposure mapping: 45–60 s
- Historical matching: 60–75 s
- Recommendation generation: 75–90 s
- Dispatch: 90+ s (async, does not block)

The Haiku 4.5 classification call must complete within 5 s; ticker extraction within 3 s; OpenAI embedding within 2 s; Sonnet 4.6 alert text within 8 s. These sub-budgets sum to ~60 s of LLM budget within the 90 s total.

## Desired Outcome
Users consistently receive alerts within the defined time windows, maintaining the system's information edge over the average retail investor.

## Acceptance Criteria
- [ ] AC-001: Given 100 consecutive intensity-4 or intensity-5 events processed, p95 end-to-end latency from event arrival to alert dispatch is ≤90 seconds.
- [ ] AC-002: Given a TIER1 tweet arrives via Twitter/X Filtered Stream (when enabled), the alert is dispatched within 30 seconds at p95.
- [ ] AC-003: Given a score-changing event is detected, the score-change alert is dispatched within 5 minutes at p95.
- [ ] AC-004: Given an SEC filing is ingested, the corresponding alert is dispatched within 20 minutes at p95.

## Out of Scope
- Real-time latency monitoring dashboard (covered by n-ai-observability NFR)

## NFR-Specific Fields

### Measurable Target
- Mode A end-to-end (intensity 4–5 events): p95 ≤ 90 seconds from event arrival to alert dispatch
- Tweet-to-alert (TIER1 tweet, Twitter/X enabled): p95 ≤ 30 seconds
- Score-change alert: p95 ≤ 5 minutes
- SEC filing alert: p95 ≤ 20 minutes
- Stage-gate sub-budgets: classify ≤5 s, extract ≤3 s, embed ≤2 s, alert text ≤8 s

### Verification Method
- Method: Automated load test with synthetic events at varied intensity levels
- Tool/Process: locust or pytest with time assertions; pipeline stage timing instrumented via Langfuse traces
- Frequency: Per release; continuous Langfuse latency monitoring in production
- Owner: QA / DevOps

### Category Rationale
Performance NFR because the system's core value proposition (20–90 min information edge) directly depends on sub-90-second pipeline execution. Latency violations negate the product's primary differentiator.

## Subtasks
- [ ] ST-001: Instrument each pipeline stage with latency telemetry — complexity: S
- [ ] ST-002: Create automated pipeline latency test suite — complexity: M
- [ ] ST-003: Set up Langfuse latency alert for p95 > 80 s — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | System Behaviours Required; Non-Functional Signals | Stage-gate latency targets (15 s increments to 90 s), tweet ≤30 s, score ≤5 min, SEC ≤20 min |
| architectural-considerations-digest.md | System Behaviours Required; Non-Functional Signals | LLM sub-budget ~60 s, sub-step latency targets |
