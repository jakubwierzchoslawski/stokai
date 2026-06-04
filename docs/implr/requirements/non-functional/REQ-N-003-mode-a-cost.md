---
req_id: REQ-N-003
slug: n-mode-a-cost
title: Mode A Per-Event Cost Ceiling
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "reactive-pipeline-ingestion: Cost ceiling enforced within the pipeline" }
  - { id: "", reason: "agent-registry-and-definitions: Per-agent cost_ceiling_usd enforced in YAML" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, cost, mode-a]
  story_points:
  components: [event-pipeline, cost-management]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Mode A Per-Event Cost Ceiling

## Domain Context
Mode A processes real-time events continuously. Without per-event cost enforcement, a traffic spike could produce unbounded AI costs. $0.05 per event is the ceiling; per-agent YAML limits provide the first-level guard.

## Summary
Every Mode A pipeline run must not exceed $0.05 total LLM and API cost. Per-agent cost_ceiling_usd limits defined in agent YAML files are enforced at runtime. Violations terminate the pipeline step and record the overrun.

## Detailed Description
As specified in architectural-considerations-digest.md business rule 2 and non-functional signals, the $0.05 ceiling covers all LLM calls (Haiku 4.5 classify, Haiku 4.5 extract, Sonnet 4.6 alert text) and the OpenAI embedding call within a single pipeline run.

Per-agent cost_ceiling_usd is enforced by the agent execution context. If an agent's cost exceeds its ceiling mid-execution, the call is terminated with a cost-exceeded error.

Total pipeline cost is tracked on the alert row (cost_usd field) and visible in the admin cost monitor.

## Desired Outcome
No single Mode A pipeline run costs more than $0.05 in external API charges, regardless of event complexity or text length.

## Acceptance Criteria
- [ ] AC-001: Given 1,000 consecutive pipeline runs, the mean cost per run is < $0.03 and the maximum cost per run does not exceed $0.05.
- [ ] AC-002: Given an agent's per-invocation cost would exceed its cost_ceiling_usd from the YAML, the agent execution terminates immediately and returns a cost-exceeded error rather than completing the call.
- [ ] AC-003: Given every completed pipeline run, the cost_usd field on the alert row accurately records the total LLM and API cost for that run.

## Out of Scope
- Cost ceiling for Mode B workflows (covered by n-mode-b-cost)
- Infrastructure cost (compute, storage) — covered by n-infrastructure-budget

## NFR-Specific Fields

### Measurable Target
- Per-event cost ceiling: $0.05 maximum (hard stop) per Mode A pipeline run
- Mean target: < $0.03 per event over 1,000+ events
- Per-agent sub-ceiling: enforced from agent YAML cost_ceiling_usd field

### Verification Method
- Method: Cost tracking on alert rows; automated test asserting max cost per pipeline run
- Tool/Process: pytest integration tests with cost assertion; Langfuse cost per trace; admin cost monitor dashboard
- Frequency: Continuous (every production run tracked); per-release integration test
- Owner: DevOps / QA

### Category Rationale
Reliability NFR because cost overruns at scale would make the system economically unviable. The $0.05 ceiling ensures the business model remains sustainable regardless of event volume.

## Subtasks
- [ ] ST-001: Implement total pipeline cost accumulator and alert row cost_usd write — complexity: S
- [ ] ST-002: Implement hard-stop at $0.05 with pipeline termination — complexity: S
- [ ] ST-003: Integration tests asserting cost ceiling compliance — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rule 2; Non-Functional Signals | $0.05 ceiling per Mode A event, per-agent cost_ceiling_usd |
