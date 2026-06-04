---
req_id: REQ-F-013
slug: hil-review-queue
title: Human-in-the-Loop Review Queue
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "four-layer-memory-subsystem: HIL actions write to Layer 4 user feedback memory" }
  - { id: "", reason: "morning-brief-workflow: HIL queue is the pause/resume point for confidence 0.4-0.69 outputs" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, frontend, admin, hil]
  story_points:
  components: [admin-panel, workflows]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Human-in-the-Loop Review Queue

## Domain Context
The HIL Review Queue is a first-class admin panel component. Workflows producing confidence 0.4–0.69 are paused (via LangGraph checkpoint) and placed in the queue. Admin reviewers act before the delivery deadline. Each action writes to Layer 4 user feedback memory.

## Summary
The system must provide an admin panel HIL review queue displaying pending workflow outputs sorted by scheduled send time, supporting Approve / Edit & Approve / Reject / Reject with feedback actions, where each action resumes or terminates the paused LangGraph workflow and writes to Layer 4 user feedback memory.

## Detailed Description
As specified in architectural-considerations-digest.md §System Behaviours Required and §Business Rules item 16, Mode B workflows with confidence 0.4–0.69 route to the HIL queue. The workflow is paused (not killed) via LangGraph PostgreSQL checkpoint, maintaining state for resume or discard.

Queue display requirements:
- Sorted by scheduled send time (earliest first — most urgent at top)
- Shows: workflow type, user, confidence score, scheduled delivery time, time remaining
- Each item expandable to show full AI output and reasoning

Actions:
- **Approve**: resume workflow; Narrative Writer runs to produce final output; dispatch
- **Edit & Approve**: reviewer edits AI output text; save as edited; dispatch; write edit to Layer 4
- **Reject**: terminate workflow; no dispatch; write rejection signal to Layer 4
- **Reject with feedback**: same as Reject plus reviewer writes free-text feedback stored in Layer 4

Each action writes a user_feedback row (Layer 4) with: feedback_type, correction (if edit), decision_ref, reviewer_id, timestamp.

The queue lives in the admin panel and is gated by admin/operator role.

## Desired Outcome
Operators can review, edit, approve, or reject AI-generated outputs before they reach users, with all decisions feeding back into the system's continuous improvement loop, and no workflow remaining in limbo beyond its delivery deadline.

## Acceptance Criteria
- [ ] AC-001: Given a Mode B workflow produces confidence in range 0.4–0.69, the workflow is paused via LangGraph checkpoint and a HIL queue item is created with status=pending, visible in the admin panel queue sorted by scheduled send time.
- [ ] AC-002: Given a reviewer clicks Approve, the LangGraph workflow is resumed from the checkpoint, Narrative Writer executes, and the output is dispatched; the HIL queue item moves to status=approved.
- [ ] AC-003: Given a reviewer clicks Edit & Approve, the reviewer's text is saved as the final output, dispatch occurs, and a user_feedback row is written with feedback_type=edit and the correction text.
- [ ] AC-004: Given a reviewer clicks Reject or Reject with feedback, the workflow is terminated (not resumed), no output is dispatched, and a user_feedback row is written with the appropriate feedback_type and optional correction text.
- [ ] AC-005: Given a HIL item's scheduled send time passes without any reviewer action, the workflow is automatically terminated and no output is dispatched; the admin AI audit console records the timeout.
- [ ] AC-006: Given an end-user (non-admin) attempts to access the HIL queue endpoint, the response is HTTP 403 Forbidden.

## Out of Scope
- End-user self-approval of their own reports (HIL is admin/operator only)
- Automatic re-queuing of rejected workflows

## Data Models
```
HILQueueItem:
  item_id: UUID
  workflow_run_id: UUID
  workflow_type: string
  user_id: UUID (the report recipient)
  tenant_id: UUID
  confidence: float
  scheduled_send_at: timestamp
  status: enum(pending, approved, edited_approved, rejected, timed_out)
  reviewer_id: UUID | null
  reviewed_at: timestamp | null
  lc_checkpoint_id: string  -- LangGraph checkpoint reference

user_feedback (Layer 4):
  feedback_id: UUID
  decision_ref: UUID  -- workflow_run_id
  feedback_type: enum(approve, edit, reject, reject_with_feedback)
  correction: text | null
  reviewer_id: UUID
  timestamp: timestamp
```

## Process Sequence
1. Mode B workflow confidence in 0.4–0.69 range triggers HIL routing
2. LangGraph state checkpointed to PostgreSQL
3. HIL queue item created with status=pending
4. Admin panel displays item in queue sorted by scheduled_send_at
5. Reviewer selects action (Approve / Edit & Approve / Reject / Reject with feedback)
6. System writes user_feedback row to Layer 4
7. On Approve/Edit & Approve: workflow resumed from checkpoint; output dispatched
8. On Reject/Reject with feedback: workflow terminated; no dispatch
9. On deadline timeout: workflow terminated; HIL item status=timed_out

## Subtasks
- [ ] ST-001: Implement LangGraph HIL pause/resume via PostgreSQL checkpointing — complexity: L
- [ ] ST-002: Implement HIL queue API endpoints (list, action) with role guard — complexity: M
- [ ] ST-003: Implement admin panel HIL queue UI component — complexity: M
- [ ] ST-004: Implement deadline timeout worker — complexity: S
- [ ] ST-005: Implement Layer 4 user_feedback write for all four actions — complexity: S
- [ ] ST-006: Integration tests for full pause-resume and pause-reject flows — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 15, 16; §System Behaviours Required | HIL routing thresholds, four actions, Layer 4 write, LangGraph checkpoint |
| ui-design-digest.md | §Business Rules items 38, 54; §System Behaviours Required | Admin panel location, sort by send time, role gate |
