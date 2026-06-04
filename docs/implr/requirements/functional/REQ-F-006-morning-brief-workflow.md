---
req_id: REQ-F-006
slug: morning-brief-workflow
title: Morning Brief Workflow (Mode B)
type: functional
status: approved
complexity: XL
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - system-description-digest.md
dependencies:
  - { id: "", reason: "agent-registry-and-definitions: Named-role agents must be defined before workflow can execute" }
  - { id: "", reason: "four-layer-memory-subsystem: Memory layers required for context retrieval" }
  - { id: "", reason: "hil-review-queue: HIL review path required for confidence 0.4–0.69 outputs" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, mode-b, morning-brief, cron]
  story_points:
  components: [workflows, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Morning Brief Workflow (Mode B)

## Domain Context
A daily LangGraph-orchestrated Mode B deliberative workflow. Cron fires at ~05:30 to start the workflow; HTML email delivery target is 06:00 local time, configurable per user/tenant (C-001 resolved). Hard latency limit 10 minutes. Cost ceiling $1.50–$2.00.

## Summary
The system must run a daily cron-triggered workflow starting at ~05:30, processing overnight events through relevance filtering, score recomputation, anomaly detection, historical context, and recommendation synthesis, and deliver a personalized HTML Morning Brief email by 06:00, subject to HIL review for confidence 0.4–0.69 outputs.

## Detailed Description
The Morning Brief workflow executes as a LangGraph StateGraph with the following agent node sequence:
1. Relevance Analyst (Sonnet 4.6) — filters overnight events for portfolio relevance
2. Anomaly Detector (Sonnet 4.6) — identifies unusual price/score movements
3. Exposure Analyst (Sonnet 4.6) — maps event exposure across portfolio
4. Historical Context Agent (Opus 4.7) — retrieves and interprets historical analogies (shared across all 5 workflows)
5. Recommendation Synthesizer (Opus 4.7) — synthesizes action recommendations
6. evaluate_quality (Opus 4.7, LLM-as-judge) — Tier 1 quality gate, always second-to-last
7. Narrative Writer (Opus 4.7) — produces HTML email body, always last

WorkflowState carries: workflow_id, tenant_id, user_id, inputs, portfolio_state, events, relevant_events, score_changes, anomalies, analogies, recommendations, report, confidence_scores, requires_hil, cost_usd, tokens_consumed.

Confidence routing (per root-synthesis §Business Rules 19–22):
- confidence ≥ 0.7: auto-send at 06:00
- confidence 0.4–0.69: route to HIL queue; hold for human review by 05:45; if unreviewed by 05:45, do not send
- confidence < 0.4: block and do not send

LangGraph state is checkpointed to PostgreSQL. Independent agent invocations execute via asyncio.gather where possible.

## Desired Outcome
Every user with an active morning brief subscription receives a personalized, confidence-scored HTML email by 06:00 covering overnight geopolitical events affecting their portfolio, with recommendations traceable to historical analogies.

## Acceptance Criteria
- [ ] AC-001: Given the cron fires at 05:30, the workflow completes all agent nodes and either delivers the email by 06:00 or routes to HIL queue for review, without exceeding 10 minutes elapsed time or $2.00 cost.
- [ ] AC-002: Given the workflow produces confidence ≥ 0.7, the HTML email is dispatched automatically by 06:00 local time (configurable per user/tenant).
- [ ] AC-003: Given the workflow produces confidence in range 0.4–0.69, the output is placed in the HIL review queue; if not reviewed and approved by 05:45, the brief is withheld and the user is notified that no brief was sent.
- [ ] AC-004: Given the workflow produces confidence < 0.4, the output is blocked entirely and no brief is sent; the admin AI audit console records the blocked run.
- [ ] AC-005: Given a workflow node failure, LangGraph checkpoint state is persisted to PostgreSQL allowing replay from the last successful checkpoint rather than restarting the full workflow.
- [ ] AC-006: Given the evaluate_quality node runs second-to-last, its confidence score is the determinative input for the auto-send/HIL/block routing decision.

## Out of Scope
- Push/SMS delivery of morning brief — phase 2
- Multi-market morning briefs (US only in MVP)
- Real-time brief generation on user request (covered by on-demand-analysis-workflow)

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | What is the exact per-workflow HIL timing window between 05:30 start and 05:45 deadline? Is 05:45 a hard deadline for all users regardless of timezone? | root-synthesis §Ambiguities: "HIL timing windows per workflow type referenced but not specified" | 2026-06-02 | ☐ |

## Data Models
```
WorkflowState (Pydantic):
  workflow_id: UUID
  tenant_id: UUID
  user_id: UUID
  inputs: dict
  portfolio_state: dict
  events: list[geo_event]
  relevant_events: list[geo_event]
  score_changes: list[dict]
  anomalies: list[dict]
  analogies: list[dict]
  recommendations: list[ai_recommendation]
  report: str (HTML)
  confidence_scores: dict[str, float]
  requires_hil: bool
  cost_usd: float
  tokens_consumed: int

Report/Brief (DB row):
  brief_id: UUID
  type: morning_brief
  user_id: UUID
  content: text (HTML)
  confidence: float
  hil_status: enum(not_required, pending, approved, rejected, timed_out)
  sent_at: timestamp | null
  cost_usd: float
```

## Process Sequence
1. Cron triggers at 05:30, dispatches Morning Brief Celery task per subscribed user
2. LangGraph workflow initialised with WorkflowState from portfolio snapshot
3. Relevance Analyst, Anomaly Detector, Exposure Analyst run (parallel where independent)
4. Historical Context Agent retrieves analogies
5. Recommendation Synthesizer synthesizes recommendations
6. evaluate_quality runs Tier 1 LLM-as-judge assessment; confidence computed
7. If confidence < 0.4: block and record; workflow ends
8. If confidence 0.4–0.69: write to HIL queue; pause workflow (LangGraph checkpoint)
9. HIL reviewer approves/rejects by 05:45; if not reviewed, timeout and suppress
10. If confidence ≥ 0.7 or HIL approved: Narrative Writer generates HTML email
11. Email dispatched via SendGrid with 06:00 delivery target

## Subtasks
- [ ] ST-001: Implement LangGraph StateGraph for Morning Brief with all 7 agent nodes — complexity: XL
- [ ] ST-002: Implement cron trigger and Celery task dispatch per user — complexity: S
- [ ] ST-003: Implement HIL queue routing with 05:45 timeout and checkpoint/resume — complexity: L
- [ ] ST-004: Implement evaluate_quality node with Tier 1 LLM-as-judge (Opus 4.7) — complexity: M
- [ ] ST-005: Implement Narrative Writer HTML email generation (Opus 4.7) — complexity: M
- [ ] ST-006: Implement per-user delivery time configuration (default 06:00) — complexity: S
- [ ] ST-007: Integration tests for full workflow including HIL path and timeout — complexity: L

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 14, 15, 20, 21; §System Behaviours Required | Cron time 05:30, delivery 06:00 (C-001 resolved), HIL routing, evaluate_quality tail pattern, LangGraph checkpointing |
| system-description-digest.md | §Business Rules item 19; §System Behaviours Required | HTML email delivery at 06:00 |
| architectural-considerations-digest.md | §Business Rules item 59 (budget) | 4–5 min, $1.50–$2.00 budget |
