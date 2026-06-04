---
req_id: REQ-N-009
slug: n-prompt-regression-safety
title: Prompt Regression Safety Gate
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "prompt-management-pipeline: Tier 2 regression is part of the promotion pipeline" }
  - { id: "", reason: "evaluation-framework: Golden dataset managed by evaluation framework" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [ai, quality, regression, prompts]
  story_points:
  components: [prompt-management, ci-cd]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Prompt Regression Safety Gate

## Domain Context
Prompt regressions can silently degrade recommendation quality without any runtime error. The golden dataset regression gate is the hard quality control preventing degraded prompts from reaching production.

## Summary
Any prompt change that degrades performance by more than 5% on any metric of the golden dataset regression must be automatically blocked from merging to main. Rollback of a promoted prompt must be effective within 60 seconds.

## Detailed Description
As specified in architectural-considerations-digest.md business rule 23 and 36:

**>5% degradation hard gate:** CI runs the golden dataset test suite on every prompt PR. If any metric (coherence, factual accuracy, action signal correctness, recommendation quality, confidence calibration) degrades by more than 5% relative to the current production prompt's scores, the CI check fails and the PR cannot be merged.

The 5% threshold is per-metric, not aggregate: a 3% improvement in coherence does not offset a 6% degradation in action signal accuracy.

**Rollback within 60 seconds:** The `stokai prompts rollback` command must update the Langfuse active version and have the change propagate to all agent invocations within 60 seconds. This is verified by testing that an agent invocation triggered 60 seconds after rollback uses the rolled-back prompt version.

## Desired Outcome
No prompt change that degrades recommendation quality reaches production, and any production issue can be reverted within one minute without requiring a code deployment.

## Acceptance Criteria
- [ ] AC-001: Given a PR modifies a prompt and the Tier 2 golden dataset regression detects a >5% degradation on any metric, the CI check fails; the PR is blocked from merging until the prompt author fixes the regression.
- [ ] AC-002: Given a prompt regression that degrades 3 metrics by 2%, 4%, and 6% respectively, the CI check fails (the 6% degradation breaches the threshold) even though 2 metrics are within tolerance.
- [ ] AC-003: Given `stokai prompts rollback --agent <role> --to-version <sha>` is executed, an agent invocation 60 seconds later uses the specified rolled-back prompt version, confirmed by the prompt_version field in the Langfuse trace.
- [ ] AC-004: Given the golden dataset contains at least 20 test cases across varied event types, the CI regression run completes in under 5 minutes to avoid blocking the development workflow.

## Out of Scope
- Automated rollback without human command (all rollbacks are operator-initiated)
- A/B testing framework beyond the golden dataset gate

## NFR-Specific Fields

### Measurable Target
- Regression gate: >5% degradation on any metric hard-blocks merge; enforced on 100% of prompt PRs
- Rollback effective time: ≤60 seconds from command execution to all new agent invocations using the rolled-back version
- CI regression run time: ≤5 minutes for a golden dataset of ≥20 test cases

### Verification Method
- Method: CI integration test with intentionally degraded prompt asserting gate blocks merge; rollback timing test
- Tool/Process: GitHub Actions / CI pipeline; pytest timing test for rollback SLA; Langfuse prompt version verification
- Frequency: On every prompt PR (regression gate); per release (rollback timing test)
- Owner: QA / DevOps

### Category Rationale
Reliability NFR because silent prompt regression directly degrades user-facing recommendation quality without any runtime error or alert. The regression gate is the primary quality guard for the AI system.

## Subtasks
- [ ] ST-001: Implement CI golden dataset regression runner with per-metric comparison — complexity: M
- [ ] ST-002: Implement 5% threshold check per metric with CI fail on breach — complexity: S
- [ ] ST-003: Implement `stokai prompts rollback` command with ≤60 s SLA — complexity: M
- [ ] ST-004: Rollback timing test asserting ≤60 s propagation — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rules 23, 36; Non-Functional Signals | >5% degradation hard gate, rollback within seconds |
