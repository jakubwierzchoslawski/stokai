---
req_id: REQ-F-016
slug: evaluation-framework
title: Three-Tier Evaluation Framework
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "four-layer-memory-subsystem: Tier 3 calibration reads from Layer 1 recommendation_outcome" }
  - { id: "", reason: "prompt-management-pipeline: Tier 2 regression gates prompt promotion" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, evaluation, quality]
  story_points:
  components: [evaluation, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Three-Tier Evaluation Framework

## Domain Context
Three tiers of evaluation operate continuously in production: Tier 1 online LLM-as-judge (every output), Tier 2 golden dataset regression (blocks prompt promotion), Tier 3 daily ex-post calibration (tracks recommendation accuracy). All three are mandatory from Phase 4.

## Summary
The system must implement a three-tier evaluation framework: Tier 1 (Opus 4.7 LLM-as-judge, async, every production output), Tier 2 (golden dataset regression, >5% degradation hard-blocks prompt promotion), and Tier 3 (daily ex-post calibration tracking actual_t1d and actual_t1w vs ai_recommendation). The continuous improvement loop closes the feedback cycle.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 23, 37, 52, 53, 60, 61 and §System Behaviours Required:

**Tier 1 — Online LLM-as-Judge (evaluate_quality node)**
- Runs asynchronously after every production workflow output
- Uses Opus 4.7 as the judge model
- Evaluates: coherence, factual consistency, confidence calibration, recommendation quality
- The evaluate_quality node is always second-to-last in every workflow (see agent-registry-and-definitions)
- Results stored in Langfuse as evaluation trace

**Tier 2 — Golden Dataset Regression**
- A curated dataset of input scenarios + expected outputs + quality metrics
- Run automatically on every prompt PR (CI gate)
- Hard-blocks promotion if any metric degrades >5% vs current production
- Golden dataset is a living artifact — admin can add new cases from AI override decisions

**Tier 3 — Daily Ex-Post Calibration**
- Runs daily; reviewed weekly by admin
- Collects actual market outcomes (actual_t1d, actual_t1w) and matches against ai_recommendation rows
- Computes: CORR(confidence, actual_t1d × direction_sign) — should be significantly positive
- Tracks directional accuracy per action signal type
- Results visible in admin calibration dashboard
- Weekly review gate: calibration results reviewed; if CORR not significantly positive, improvement loop triggered

## Desired Outcome
Every AI output is quality-checked before delivery, prompt regressions are caught before production, and recommendation accuracy is tracked against ground truth, enabling data-driven improvement of the AI system.

## Acceptance Criteria
- [ ] AC-001: Given any Mode B workflow output, evaluate_quality (Tier 1) runs as the second-to-last node using Opus 4.7; the evaluation result is stored as a Langfuse evaluation trace linked to the workflow run.
- [ ] AC-002: Given a prompt PR, CI runs the Tier 2 golden dataset regression; if any metric degrades >5% compared to the production prompt's scores, the CI check fails and the PR cannot be merged.
- [ ] AC-003: Given the daily Tier 3 job runs, it queries actual_t1d and actual_t1w price changes, matches them to ai_recommendation rows by company and date, and computes CORR(confidence, actual_t1d × direction_sign) stored in the calibration results table.
- [ ] AC-004: Given the Tier 3 calibration dashboard is viewed by an admin, it displays per-action-signal accuracy, confidence calibration curve, and the weekly correlation metric, with data going back at least 30 days.
- [ ] AC-005: Given an admin overrides an AI decision in the AI audit console, the overridden input/output pair is added as a golden dataset candidate for Tier 2; it becomes an active test case after admin approval.

## Out of Scope
- Automated remediation of calibration failures (weekly human review required before any action)
- Real-time Tier 3 calibration (runs once daily)

## Data Models
```
evaluation_result (Tier 1):
  eval_id: UUID
  run_id: UUID
  eval_type: tier_1
  judge_model: string
  scores: JSONB  -- per-dimension scores
  overall_quality: float
  prompt_version: string
  evaluated_at: timestamp

golden_dataset_item (Tier 2):
  item_id: UUID
  input: JSONB
  expected_output: JSONB
  quality_metrics: JSONB
  source: enum(hand_authored, admin_override)
  active: bool

calibration_result (Tier 3):
  date: date
  action_signal: string
  total_recommendations: int
  direction_correct_pct: float
  corr_confidence_actual: float
  mean_confidence: float
  mean_actual_t1d: float
```

## Process Sequence
1. Tier 1: evaluate_quality node runs in every workflow; Opus 4.7 judges output; result stored in Langfuse
2. Tier 2: prompt PR opened → CI triggers golden dataset run → compare against production baseline → block or pass
3. Admin override: input/output pair added to golden_dataset candidate pool → admin approves → active test case
4. Tier 3: daily cron queries recommendation_outcome joined with actual price data → computes calibration metrics → stores results
5. Weekly: admin reviews calibration dashboard; if CORR not significantly positive → improvement loop triggered

## Subtasks
- [ ] ST-001: Implement Tier 1 evaluate_quality node with Opus 4.7 judge and Langfuse result storage — complexity: M
- [ ] ST-002: Implement golden dataset management (add, activate, version) — complexity: M
- [ ] ST-003: Implement Tier 2 CI regression runner with 5% degradation gate — complexity: M
- [ ] ST-004: Implement daily Tier 3 calibration job with CORR computation — complexity: M
- [ ] ST-005: Implement admin calibration dashboard with 30-day history — complexity: M
- [ ] ST-006: Implement golden dataset candidate creation from admin override — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 23, 37, 52, 53, 60, 61; §System Behaviours Required | Three-tier definitions, LLM-as-judge, >5% gate, daily Tier 3, CORR metric, weekly review |
