---
req_id: REQ-F-010
slug: event-deep-dive-workflow
title: Event Deep-Dive Workflow (Mode B)
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "reactive-pipeline-ingestion: Step 12 enqueues the deep-dive; must exist first" }
  - { id: "", reason: "agent-registry-and-definitions: Event Deep-Dive Agent (Opus 4.7) must be defined" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, mode-b, deep-dive]
  story_points:
  components: [workflows, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Event Deep-Dive Workflow (Mode B)

## Domain Context
Triggered by Mode A pipeline step 12 when intensity ≥ 4 or a portfolio match is detected, with a 2-minute delay. Event Deep-Dive Agent (Opus 4.7) produces a "memo" artifact. Hard latency limit ≤15 minutes; cost ceiling $2.00.

## Summary
The system must execute an Event Deep-Dive LangGraph workflow, triggered 2 minutes after Mode A step 12 enqueues it, producing a comprehensive event analysis memo for high-intensity or portfolio-relevant events, completing within 7 minutes and costing no more than $2.00.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 13, 19 and §System Behaviours Required (5–7 min, $2.00), the deep-dive is triggered when Mode A detects intensity ≥ 4 or a portfolio match. The 2-minute delay allows Mode A's initial alert to reach users first before the deeper analysis is prepared.

The Event Deep-Dive Agent (Opus 4.7) is the primary agent. It produces a structured "memo" artifact covering:
- Comprehensive event context and geopolitical significance
- Full exposure analysis for all affected companies
- Extended historical analogies with detailed outcome statistics
- Scenario analysis (bull/base/bear)
- Action recommendations per affected company

Agent chain: Event Deep-Dive Agent (Opus 4.7) → Historical Context Agent → Recommendation Synthesizer → evaluate_quality → Narrative Writer.

The memo artifact is stored in the DB and linked to the originating geo_event. It becomes available in the side panel "Full Analysis" view and in the Reports section.

Hard limit 15 minutes. Cost ceiling $2.00.

## Desired Outcome
For any high-intensity (≥4) or portfolio-matching event, users receive a comprehensive analytical memo within 7 minutes (9 minutes maximum after the triggering Mode A alert), providing deeper context than the Mode A alert.

## Acceptance Criteria
- [ ] AC-001: Given Mode A step 12 enqueues a deep-dive job with a 2-minute delay, the Celery task executes after 2 minutes and not before.
- [ ] AC-002: Given the workflow executes, a memo artifact is produced containing: geopolitical context, exposure analysis for affected companies, extended historical analogies, scenario analysis, and per-company action recommendations.
- [ ] AC-003: Given the workflow runs, it completes within 7 minutes (target) and 15 minutes (hard limit), and total cost does not exceed $2.00.
- [ ] AC-004: Given the memo is produced with confidence ≥ 0.7, it is stored, linked to the geo_event, and made available in the full analysis view without requiring explicit user action.
- [ ] AC-005: Given the cost ceiling ($2.00) is reached before completion, the workflow terminates and a partial memo is stored with a "cost-limited" flag visible to the admin.

## Out of Scope
- Deep-dive for events below intensity 4 with no portfolio match (not triggered)
- User-requested re-runs of deep-dives (covered by admin-system-operations re-run capability)

## Data Models
```
workflow_run:
  run_id: UUID
  workflow_type: event_deep_dive
  event_id: UUID
  status: enum(pending, running, completed, failed, cost_limited)
  started_at: timestamp
  completed_at: timestamp | null
  cost_usd: float
  confidence: float

Report/Brief (DB row):
  brief_id: UUID
  type: event_deep_dive
  event_id: UUID
  content: JSONB  -- structured memo
  confidence: float
  cost_usd: float
  cost_limited: bool
```

## Process Sequence
1. Mode A step 12 enqueues deep-dive Celery task with 2-minute ETA
2. Task executes; LangGraph workflow initialised with geo_event context
3. Event Deep-Dive Agent (Opus 4.7) produces comprehensive event analysis
4. Historical Context Agent enriches with analogies
5. Recommendation Synthesizer generates per-company recommendations
6. evaluate_quality assesses confidence
7. Narrative Writer structures the memo
8. Memo stored, linked to geo_event, made available in full analysis view

## Subtasks
- [ ] ST-001: Implement 2-minute delayed Celery task dispatch from pipeline step 12 — complexity: S
- [ ] ST-002: Implement Event Deep-Dive Agent (Opus 4.7) YAML and prompt — complexity: M
- [ ] ST-003: Implement LangGraph StateGraph for deep-dive workflow — complexity: L
- [ ] ST-004: Implement memo artifact schema and DB storage — complexity: S
- [ ] ST-005: Implement cost ceiling ($2.00) and hard timeout (15 min) enforcement — complexity: S
- [ ] ST-006: Implement frontend link from geo_event to available memo — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 13, 19; §System Behaviours Required | 2-min delay, intensity ≥4/portfolio match trigger, 5–7 min $2.00 budget, 15 min hard limit |
