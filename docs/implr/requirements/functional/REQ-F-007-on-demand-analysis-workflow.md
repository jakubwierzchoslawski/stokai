---
req_id: REQ-F-007
slug: on-demand-analysis-workflow
title: On-Demand Company Analysis Workflow (Mode B)
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "agent-registry-and-definitions: Named-role agents required" }
  - { id: "", reason: "company-detail-and-on-demand: On-demand analysis is triggered from Company Detail screen" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, mode-b, on-demand]
  story_points:
  components: [workflows, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — On-Demand Company Analysis Workflow (Mode B)

## Domain Context
A user-triggered Mode B deliberative workflow launched from the Company Detail screen. Produces a full deep-analysis report covering exposure, historical context, anomaly detection, and recommendations. Hard latency limit ≤4 minutes (≤6 minutes absolute), cost ceiling $1.50 (≤$1.50 per architectural-considerations-digest.md).

## Summary
The system must execute a full LangGraph-orchestrated analysis workflow on user request for a specific company, completing within 4 minutes and costing no more than $1.50, delivering a structured report with confidence scoring, action signal, and historical context.

## Detailed Description
User triggers on-demand analysis from Company Detail screen. The workflow executes the full agent chain: Relevance Analyst → Exposure Analyst → Anomaly Detector → Historical Context Agent → Recommendation Synthesizer → evaluate_quality → Narrative Writer.

Unlike scheduled workflows, on-demand runs are initiated synchronously from a user action. The result is displayed within the Company Detail screen and stored in the AI analysis history. The user can see a loading indicator during processing.

Confidence routing applies identically to other Mode B workflows: ≥ 0.7 auto-deliver, 0.4–0.69 show with HIL annotation indicating human review is pending, < 0.4 block and show a "unable to generate confident analysis" message.

The workflow targets ≤3–4 minutes per architectural-considerations-digest.md §System Behaviours Required; the absolute hard limit is 6 minutes per the NFR.

## Desired Outcome
A user requesting analysis of a specific company from the Company Detail screen receives a comprehensive AI-generated report with recommendations, historical analogies, and confidence scores within 4 minutes, costing no more than $1.50.

## Acceptance Criteria
- [ ] AC-001: Given a user clicks "On-Demand Analysis" on a Company Detail screen, a LangGraph workflow is initiated and a loading state is displayed; the report is delivered to the screen within 4 minutes (p95 user-visible target); if not delivered within 6 minutes the Celery workflow is hard-terminated (per REQ-N-002) and the user sees an error state.
- [ ] AC-002: Given the workflow completes, the report includes: action signal, confidence score, sample_size, historical analogies with market statistics, exposure analysis, and anomaly assessment.
- [ ] AC-003: Given the workflow produces confidence < 0.4, the UI displays a "unable to generate confident analysis" message rather than a blocked report, and the run is recorded in the admin AI audit console.
- [ ] AC-004: Given the total workflow cost exceeds $1.50, the workflow is terminated by the cost ceiling guard and the user sees a partial-results message.
- [ ] AC-005: Given the analysis completes, it is stored in the company's AI analysis history and visible on subsequent Company Detail views.

## Out of Scope
- Automatic periodic on-demand runs (all on-demand runs are explicitly user-triggered)
- Batch on-demand analysis for multiple companies simultaneously

## Data Models
```
WorkflowState: (same as morning-brief-workflow, scoped to single company)

ai_recommendation:
  event_id: UUID | null
  company_id: UUID
  action_signal: enum(HOLD, WATCH, BUY_OPP, REDUCE_RISK, HEDGE, CONTRARIAN)
  direction: string
  confidence: float
  sample_size: int
  rationale: text
  forecast: JSONB
  analogies: JSONB
  model_version: string
  workflow_run_id: UUID
```

## Process Sequence
1. User clicks "On-Demand Analysis" on Company Detail screen
2. API endpoint accepts request, creates workflow_run record, returns run_id
3. Celery dispatches LangGraph workflow for the company
4. Agents execute sequentially/parallel as applicable
5. evaluate_quality runs confidence assessment
6. If confidence ≥ 0.7: Narrative Writer generates report; stored and delivered to frontend
7. If confidence 0.4–0.69: report delivered with HIL annotation
8. If confidence < 0.4: blocked, user sees error message

## Subtasks
- [ ] ST-001: Implement on-demand workflow trigger API endpoint — complexity: S
- [ ] ST-002: Implement LangGraph StateGraph for on-demand analysis — complexity: L
- [ ] ST-003: Implement cost ceiling enforcement ($1.50 hard stop) — complexity: S
- [ ] ST-004: Implement frontend loading state and async result delivery — complexity: M
- [ ] ST-005: Implement AI analysis history storage and display on Company Detail — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §System Behaviours Required (Mode B budgets) | 3–4 min, $1.00–$1.50; hard limit 6 min |
| ui-design-digest.md | §Business Rules items 31, 32 | Company Detail screen trigger, analysis history |
