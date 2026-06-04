---
req_id: REQ-F-029
slug: admin-ai-audit-console
title: Admin AI Audit Console
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - ui-design-digest.md
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "evaluation-framework: Tier 3 calibration dashboard lives here" }
  - { id: "", reason: "prompt-management-pipeline: Prompt version history and rollback control" }
  - { id: "", reason: "four-layer-memory-subsystem: Admin override writes to Layer 4" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, frontend, admin, audit, ai]
  story_points:
  components: [admin-panel, audit]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Admin AI Audit Console

## Domain Context
The AI Audit Console gives operators full visibility into every AI decision. It combines: searchable AI decision log with Langfuse trace links, admin override capability, prompt version history and rollback, and the Tier 3 calibration dashboard.

## Summary
The system must provide an admin AI audit console with a searchable decision log (inputs, analogues, prompt version, model, confidence, output, Langfuse trace link), admin override capability writing to Layer 4 and golden dataset, prompt version history with rollback, and Mode B workflow history with re-run capability.

## Detailed Description
As specified in ui-design-digest.md business rules 47–54 and architectural-considerations-digest.md system behaviours:

**Searchable AI Decision Log:**
- Every AI classification and recommendation stored
- Searchable/filterable by: date, model, agent_role, confidence range, action_signal, company
- Each row shows: inputs (truncated), retrieved analogues, prompt_version (SHA), model, confidence, output text, Langfuse trace link
- Click row → expand to full detail

**Admin Override:**
- Admin selects an AI decision and overrides with corrected output
- System: writes to Layer 4 (feedback_type=admin_override), adds to golden_dataset candidate pool, surfaces proposed prompt adjustment for review
- On approval: prompt change enters git+Langfuse pipeline

**Prompt Version History:**
- Per-agent prompt version list with: SHA, date, quality_metrics per Tier 2/3, active_from, rolled_back_at
- Rollback button: calls `stokai prompts rollback` → effective within 60 seconds

**Calibration Dashboard (Tier 3):**
- Per-action-signal accuracy over time
- CORR(confidence, actual_t1d × direction_sign) chart
- Weekly review indicator: flag when CORR drops below threshold
- Configurable lookback window (30/60/90 days)

**Mode B Workflow History:**
- List of all workflow runs: type, user, status, cost, duration
- Per-run detail: agent invocations, tool calls, cost breakdown
- Re-run button: re-triggers the same workflow with current prompts

## Desired Outcome
Operators have complete traceability and control over AI behaviour, can override incorrect outputs to improve the system, and can monitor recommendation accuracy against market reality.

## Acceptance Criteria
- [ ] AC-001: Given the AI audit console is open, an admin can search AI decisions by date range, confidence range, and model; clicking any row expands to full detail including the Langfuse trace URL.
- [ ] AC-002: Given an admin overrides an AI decision, a user_feedback row is written to Layer 4 with feedback_type=admin_override, the decision is added to the golden_dataset candidate pool, and a proposed prompt adjustment is surfaced in the admin panel for review.
- [ ] AC-003: Given the prompt version history panel is open, the admin can view quality metrics per version and click Rollback; the rollback takes effect within 60 seconds and subsequent agent invocations use the rolled-back prompt version.
- [ ] AC-004: Given the calibration dashboard, it displays CORR(confidence, actual_t1d × direction_sign) for at least 30 days of history; if CORR is not significantly positive, a warning indicator is visible.
- [ ] AC-005: Given a Mode B workflow in the history list, clicking Re-run dispatches the same workflow with current production prompts and the new run appears in the workflow history list.

## Out of Scope
- Real-time override of in-flight workflows (override applies to historical decisions)
- Automated prompt changes without human approval

## Data Models
```
AIDecision (audit log row):
  decision_id: UUID
  agent_role: string
  model: string
  prompt_version: string (SHA)
  confidence: float
  inputs_summary: text
  retrieved_analogs: JSONB
  output_text: text
  langfuse_trace_url: string
  workflow_run_id: UUID
  created_at: timestamp

PromptVersionHistory:
  version_id: string (SHA)
  agent_role: string
  quality_metrics: JSONB
  active_from: timestamp
  rolled_back_at: timestamp | null
```

## Process Sequence
1. Admin navigates to AI Audit Console
2. Decision log loaded with search/filter applied
3. Admin selects a decision → full detail with Langfuse trace
4. Admin clicks Override → correction entered → Layer 4 write + golden dataset candidate + prompt proposal
5. Admin reviews prompt version history → clicks Rollback → prompt reverted in Langfuse
6. Admin views calibration dashboard → weekly CORR check visible
7. Admin clicks Re-run on workflow → workflow dispatched with current prompts

## Subtasks
- [ ] ST-001: Implement AI decision log API with search/filter — complexity: M
- [ ] ST-002: Implement admin override: Layer 4 write + golden dataset candidate + prompt proposal — complexity: M
- [ ] ST-003: Implement prompt version history panel and rollback control — complexity: M
- [ ] ST-004: Implement Tier 3 calibration dashboard with CORR chart — complexity: M
- [ ] ST-005: Implement Mode B workflow history with re-run — complexity: M
- [ ] ST-006: Frontend admin AI audit console — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| ui-design-digest.md | Business Rules 47-54; System Behaviours Required | All audit console requirements, override flow, prompt rollback, calibration dashboard |
| architectural-considerations-digest.md | Business Rules item 11; System Behaviours Required | Every AI reasoning step stored, override triggers prompt/config changes |
