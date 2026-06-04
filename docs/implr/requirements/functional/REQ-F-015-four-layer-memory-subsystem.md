---
req_id: REQ-F-015
slug: four-layer-memory-subsystem
title: Four-Layer Memory Subsystem
type: functional
status: approved
complexity: XL
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, memory, data]
  story_points:
  components: [memory-subsystem]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Four-Layer Memory Subsystem

## Domain Context
All five Mode B workflows and the evaluation framework depend on the four-layer memory architecture. All layers are implemented from day 1 in MVP — no incremental rollout. Episodic is append-only, semantic has evidence-gated commit and 6-month decay, procedural is hand-seeded v1 with weekly mining v2, and Layer 4 captures user feedback.

## Summary
The system must implement a four-layer memory subsystem: Layer 1 episodic (append-only, indefinite retention), Layer 2 semantic (evidence_count ≥ 3 to commit, 6-month decay), Layer 3 procedural (hand-seeded v1; weekly mined v2), and Layer 4 user feedback (explicit HIL and in-app signals), with a weekly offline improvement loop requiring human approval before changes are applied.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 11–17, 38–44 and §Architecture Signals:

**Layer 1 — Episodic Memory (append-only, indefinite retention)**
Tables: workflow_run, agent_invocation, tool_call, recommendation_outcome
Every workflow execution, agent invocation, tool call, and recommendation outcome is recorded. No deletion. Provides the raw material for Tier 3 calibration and Layer 3 pattern mining.

**Layer 2 — Semantic Memory (evidence-gated, decay)**
Table: semantic_fact (entity facts with pgvector embeddings)
Facts only committed when evidence_count ≥ 3. Facts decay if unconfirmed for 6 months. Quarterly review and explicit retraction capability. Memory hygiene enforced.

**Layer 3 — Procedural Memory (patterns, versioned)**
Table: procedural_pattern
v1: hand-authored reasoning patterns (before Phase 4 go-live). v2: weekly automated job mines episodic memory for recurring patterns. All proposed changes require human approval before application.

**Layer 4 — User Feedback (explicit signals)**
Table: user_feedback
Captures: HIL actions (Approve / Edit & Approve / Reject / Reject with feedback), in-app thumbs up/down/edit signals from reports reader. Used by the weekly improvement loop.

**Weekly Offline Improvement Loop:**
Aggregates Layer 4 patterns → generates proposed prompt/threshold adjustments → presents to human for approval → on approval, changes flow through the git+Langfuse pipeline.

## Desired Outcome
The system continuously learns from its outputs and user corrections, improving recommendation quality over time through structured memory layers, while all changes to prompts and thresholds require explicit human approval.

## Acceptance Criteria
- [ ] AC-001: Given any Mode B workflow completes, workflow_run, agent_invocation, and tool_call rows are written to Layer 1 episodic tables with no deletes permitted; the insert-only constraint is enforced at the DB level.
- [ ] AC-002: Given a proposed semantic fact with evidence_count < 3, the system does not commit it to the semantic_fact table; it is held in a staging state until evidence_count reaches 3.
- [ ] AC-003: Given a semantic_fact has not been confirmed for 6 months, the weekly hygiene job marks it as decayed and it is excluded from tool query results; it is not deleted but flagged inactive.
- [ ] AC-004: Given a weekly improvement loop run, proposed prompt or threshold adjustments are written to a pending-review table and are not applied until a human reviewer explicitly approves them.
- [ ] AC-005: Given a user provides an in-app thumbs-down feedback signal on a report, a user_feedback row is written to Layer 4 with feedback_type=thumbs_down and the report reference, without requiring the user to be an admin.

## Out of Scope
- Automated application of improvement loop changes without human approval
- Memory deletion beyond semantic decay flagging (Layer 1 is permanently append-only)

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | Who authors the Layer 3 procedural memory v1 patterns, and what completeness criteria must be met before Phase 4 go-live? | root-synthesis §Ambiguities Detected | 2026-06-02 | ☐ |

## Data Models
```
workflow_run: run_id, workflow_type, tenant_id, user_id, started_at, completed_at,
              confidence, cost_usd, status

agent_invocation: invocation_id, run_id, agent_role, model_id, prompt_version,
                  input_tokens, output_tokens, latency_ms, confidence, cost_usd

tool_call: call_id, invocation_id, tool_name, args_hash, result_rows, cached, latency_ms,
           error_type

recommendation_outcome: outcome_id, run_id, company_id, action_signal, confidence,
                        actual_t1d, actual_t1w, direction_correct

semantic_fact: fact_id, entity_id, entity_type, fact_text, embedding VECTOR(1536),
               evidence_count, last_confirmed, decayed_at, source_run_ids[]

procedural_pattern: pattern_id, pattern_type, context_tags[], pattern_text,
                    authored_by (human|mined), approved_at, version

user_feedback: feedback_id, decision_ref, feedback_type, correction, source,
               reviewer_id, timestamp
```

## Process Sequence
1. Workflow execution: episodic tables populated in real-time (Layer 1)
2. Agent output with entity facts: semantic_fact staging → evidence accumulation → commit at ≥3
3. Weekly hygiene job: scan semantic_fact for unconfirmed > 6 months → mark decayed
4. Weekly pattern mining job (v2): scan episodic for recurring patterns → propose to Layer 3
5. Human approves Layer 3 pattern additions
6. Layer 4: HIL actions and in-app feedback written continuously
7. Weekly improvement loop: aggregate Layer 4 → propose prompt/threshold changes → human gate → approved changes enter git+Langfuse pipeline

## Subtasks
- [ ] ST-001: Implement Layer 1 episodic tables with insert-only DB constraints — complexity: M
- [ ] ST-002: Implement Layer 2 semantic_fact with evidence_count gate and staging — complexity: M
- [ ] ST-003: Implement 6-month semantic decay job — complexity: S
- [ ] ST-004: Implement quarterly memory hygiene (decay + retraction) workflow — complexity: M
- [ ] ST-005: Implement Layer 3 procedural_pattern table with approval gate — complexity: M
- [ ] ST-006: Implement weekly episodic pattern mining job (v2) — complexity: L
- [ ] ST-007: Implement Layer 4 user_feedback write from HIL actions and in-app signals — complexity: S
- [ ] ST-008: Implement weekly improvement loop aggregation and proposal generation — complexity: L
- [ ] ST-009: Unit and integration tests for evidence gate, decay, insert-only enforcement — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 11-17, 38-44; §Architecture Signals; §Data Entities | All four layer definitions, evidence gate, 6-month decay, weekly jobs, improvement loop |
