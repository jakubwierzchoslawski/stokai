---
plan_id: PLAN-F-013
slug: hil-review-queue
title: Human-in-the-Loop Review Queue
linked_requirement: REQ-F-013
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-006, reason: "HIL items are tenant-scoped; all repository queries must include tenant_id" }
  - { id: REQ-N-012, reason: "Every HIL action must be logged in episodic memory (Layer 1) for audit" }
dependencies:
  - { id: PLAN-F-015, reason: "HIL actions write to Layer 4 user_feedback memory; user_feedback table and repository are owned by PLAN-F-015" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-013 — Human-in-the-Loop Review Queue

## Linked Requirement
**REQ-F-013** — Human-in-the-Loop Review Queue
Status: approved | Jira:

## Objective

Build the complete Human-in-the-Loop Review Queue: the mechanism by which Mode B workflows
producing confidence in the 0.4–0.69 range (D9) are paused via LangGraph PostgreSQL
checkpointing, placed into an admin-visible queue, acted on by a reviewer (Approve /
Edit & Approve / Reject / Reject with feedback), and resumed or terminated accordingly.
Every action writes to Layer 4 user_feedback memory and to the Layer 1 episodic store for
audit. A Celery beat task enforces delivery deadlines and times out un-reviewed items.
The queue is exposed through FastAPI endpoints gated by admin/operator role and rendered
as an `/admin/hil` React page within the existing admin panel.

## Architecture Context

This plan touches four of the six system layers:

- **Layer 4 — Processing (`ai` module):** The `evaluate_quality` node at the end of every
  Mode B workflow already sets `WorkflowState.requires_hil`. This plan adds the
  `hil_router` conditional edge that checkpoints the LangGraph graph to PostgreSQL and
  inserts the `hil_queue_item` row. The graph pause/resume logic lives in `src/ai/hil/`.
  Resume re-enters the graph at the `narrative_writer` node; rejection terminates the run.

- **Layer 3 — Storage (`storage` module):** Two new tables: `hil_queue_item` (see Data
  Models in REQ-F-013) and the pre-existing `user_feedback` (owned by PLAN-F-015, reused
  here). A new `HILQueueRepository` handles all DB access.

- **Layer 5 — Serving (`api` module):** Four new FastAPI endpoints under
  `/api/v1/admin/hil/`. JWT middleware already exists; role guard (`admin | operator`) is
  applied via an existing dependency.

- **Layer 6 — Presentation (frontend):** A new React page `/admin/hil` with a queue table
  component, expandable item detail, and action buttons. TanStack Query drives server
  state; WebSocket push is used for real-time queue updates.

Architecture refs: §7.1 (LangGraph checkpointing), §7.4 (Layer 4 user_feedback),
§7.6 (HIL queue UI and timing windows), §7.7 (D9 thresholds), §11 (admin panel),
§12.1 (JWT role guard), §12.3 (multi-tenancy tenant_id).

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-006 | All HIL items are tenant-scoped | `hil_queue_item.tenant_id` is non-nullable; `HILQueueRepository` includes `tenant_id` in every WHERE clause; API extracts `tenant_id` from JWT claims |
| REQ-N-012 | Every HIL action logged in episodic memory (Layer 1) for audit | `HILActionService` writes a `workflow_run` status update and an `agent_invocation`-style audit row on every Approve / Edit & Approve / Reject / Reject-with-feedback action |

## Component Design

### New Components

```
src/ai/hil/
  hil_router.py          — Conditional edge function; reads requires_hil flag;
                           checkpoints graph; inserts hil_queue_item row
  hil_resume.py          — Loads checkpoint by lc_checkpoint_id; resumes graph
                           from narrative_writer node
  hil_timeout_task.py    — Celery beat task; queries pending items past deadline;
                           terminates and marks timed_out

src/storage/repositories/
  hil_queue_repository.py — HILQueueRepository: CRUD for hil_queue_item;
                            all queries tenant-scoped

src/api/routers/
  hil_router.py          — FastAPI router; 4 endpoints; role-gated

src/api/schemas/
  hil_schemas.py         — Pydantic request/response DTOs for HIL API

src/api/dependencies/
  (no new file — reuse existing role_required dependency)

frontend/src/pages/admin/
  HilQueue.tsx           — /admin/hil page; queue table + item panel

frontend/src/components/admin/hil/
  HilQueueTable.tsx      — Sortable queue list; time-to-send countdown
  HilItemDetail.tsx      — Expandable: report preview, confidence breakdown,
                           key concerns
  HilActionButtons.tsx   — Approve / Edit & Approve / Reject / Reject w/ feedback
  useHilQueue.ts         — TanStack Query hooks + WebSocket subscription
```

### New DB Table

```sql
CREATE TABLE hil_queue_item (
    item_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id    UUID NOT NULL REFERENCES workflow_run(workflow_id),
    workflow_type      VARCHAR(64) NOT NULL,
    user_id            UUID NOT NULL REFERENCES "user"(user_id),
    tenant_id          UUID NOT NULL,
    confidence         FLOAT NOT NULL CHECK (confidence >= 0.4 AND confidence < 0.7),
    scheduled_send_at  TIMESTAMPTZ NOT NULL,
    status             VARCHAR(32) NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','approved','edited_approved',
                                             'rejected','timed_out')),
    reviewer_id        UUID REFERENCES "user"(user_id),
    reviewed_at        TIMESTAMPTZ,
    lc_checkpoint_id   TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_hil_queue_tenant_status
    ON hil_queue_item (tenant_id, status, scheduled_send_at);
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/workflows/base_workflow.py` | Add `hil_router` as conditional edge after `evaluate_quality` node | Every workflow must branch to HIL when `requires_hil=True` |
| `src/api/main.py` (or app factory) | Register `hil_router` FastAPI router | Expose `/api/v1/admin/hil/` endpoints |
| `src/config/celery_app.py` | Register `hil_timeout_task` in beat schedule | Runs every 60 s to enforce deadlines |
| `frontend/src/router.tsx` | Add `/admin/hil` route guarded by admin role | Mount HIL queue page |
| `frontend/src/pages/admin/AdminLayout.tsx` | Add "HIL Queue" nav link with pending-count badge | Operator discoverability |
| `alembic/versions/` | New migration: `create_hil_queue_item` | Schema change |

### Interfaces and Contracts

```python
# src/ai/hil/hil_router.py
async def hil_router_edge(state: WorkflowState) -> str:
    """LangGraph conditional edge. Returns 'hil' or 'narrative_writer'."""
    ...

# src/storage/repositories/hil_queue_repository.py
class HILQueueRepository:
    async def create(self, item: HILQueueItemCreate) -> HILQueueItem: ...
    async def list_pending(self, tenant_id: UUID) -> list[HILQueueItem]: ...
    async def get(self, item_id: UUID, tenant_id: UUID) -> HILQueueItem | None: ...
    async def update_status(
        self,
        item_id: UUID,
        tenant_id: UUID,
        status: HILStatus,
        reviewer_id: UUID | None = None,
        reviewed_at: datetime | None = None,
    ) -> HILQueueItem: ...
    async def list_timed_out_pending(self, now: datetime) -> list[HILQueueItem]: ...

# src/api/routers/hil_router.py — endpoint signatures
# GET  /api/v1/admin/hil/                    → HILQueueListResponse
# GET  /api/v1/admin/hil/{item_id}           → HILQueueItemResponse
# POST /api/v1/admin/hil/{item_id}/approve   → HILActionResponse
# POST /api/v1/admin/hil/{item_id}/action    body: HILActionRequest → HILActionResponse

# src/api/schemas/hil_schemas.py
class HILActionRequest(BaseModel):
    action: Literal["approve", "edit_approve", "reject", "reject_with_feedback"]
    edited_text: str | None = None    # required when action == "edit_approve"
    feedback_text: str | None = None  # required when action == "reject_with_feedback"

class HILActionResponse(BaseModel):
    item_id: UUID
    status: str
    workflow_resumed: bool
    feedback_id: UUID
```

## Implementation Tasks

### TASK-001: Alembic migration — create hil_queue_item table · S/no-TDD · alembic/versions/XXXX_create_hil_queue_item.py

Write the Alembic migration that creates the `hil_queue_item` table with all columns,
constraints, and the composite index on `(tenant_id, status, scheduled_send_at)`.
Include a corresponding downgrade that drops the table.

**AC covered**: AC-001 (prerequisite schema)

---

### TASK-002: HILQueueRepository · M/TDD · src/storage/repositories/hil_queue_repository.py, tests/unit/storage/test_hil_queue_repository.py

Implement `HILQueueRepository` using SQLAlchemy 2.0 async session. All five methods in the
interface above must be present. Every query must include `tenant_id` in the WHERE clause
(REQ-N-006). `list_timed_out_pending` returns all rows where `status='pending'` and
`scheduled_send_at < now`. No business logic in the repository.

**Tests to write first (TDD)**:
- `test_create_inserts_row_with_correct_tenant_id`
- `test_list_pending_filters_by_tenant_and_status`
- `test_get_returns_none_for_wrong_tenant`
- `test_update_status_changes_status_and_reviewer`
- `test_list_timed_out_pending_returns_only_past_deadline_pending_rows`

**AC covered**: AC-001, AC-005, AC-006 (data layer prerequisite)

---

### TASK-003: LangGraph HIL pause — hil_router_edge and hil_queue_item creation · L/TDD · src/ai/hil/hil_router.py, tests/unit/ai/hil/test_hil_router.py

Implement `hil_router_edge(state: WorkflowState) -> str`. When `state.requires_hil` is
`True`:

1. Persist the current LangGraph checkpoint to PostgreSQL (LangGraph's built-in
   `AsyncPostgresSaver`). Read the resulting `checkpoint_id`.
2. Call `HILQueueRepository.create(...)` to insert the `hil_queue_item` row with
   `status='pending'`, `lc_checkpoint_id` set to the checkpoint reference, and
   `scheduled_send_at` derived from workflow type (Morning Brief → next 05:45 cutoff,
   Watchlist → 17:45, On-Demand → now+10 min, Event Deep-Dive → now+30 min).
3. Return the string `"hil"` to route the graph to a terminal `HIL_PENDING` node (does
   not kill the Celery task — the task parks and waits).

When `state.requires_hil` is `False`, return `"narrative_writer"`.

Add the conditional edge in every workflow's `StateGraph` definition at the
`evaluate_quality → (hil_router_edge) → narrative_writer | hil_pending` branch.

**Tests to write first (TDD)**:
- `test_routes_to_narrative_writer_when_requires_hil_false`
- `test_routes_to_hil_when_requires_hil_true`
- `test_creates_hil_queue_item_on_hil_route`
- `test_scheduled_send_at_morning_brief_is_0545`
- `test_scheduled_send_at_on_demand_is_now_plus_10_min`
- `test_checkpoint_id_stored_in_queue_item`

**AC covered**: AC-001

---

### TASK-004: LangGraph HIL resume — hil_resume · L/TDD · src/ai/hil/hil_resume.py, tests/unit/ai/hil/test_hil_resume.py

Implement `HILResumeService`:

- `resume_from_checkpoint(lc_checkpoint_id: str, override_text: str | None) -> WorkflowState`
  — Loads the LangGraph checkpoint via `AsyncPostgresSaver`; if `override_text` is set,
  writes it into `state.report.content` before resuming; re-enters the graph at the
  `narrative_writer` node; returns the completed state.

- `terminate_workflow(lc_checkpoint_id: str, reason: str) -> None`
  — Marks the checkpoint as discarded; writes a `workflow_run` status update of
  `terminated_hil`; does not resume the graph.

Both methods must be async. The Celery worker calls these methods from the `HILActionService`.

**Tests to write first (TDD)**:
- `test_resume_loads_checkpoint_and_continues_from_narrative_writer`
- `test_resume_with_override_text_replaces_report_content`
- `test_terminate_marks_workflow_run_as_terminated_hil`
- `test_terminate_does_not_resume_graph`

**AC covered**: AC-002, AC-003, AC-004

---

### TASK-005: HILActionService — action dispatch and Layer 4 / Layer 1 writes · L/TDD · src/ai/hil/hil_action_service.py, tests/unit/ai/hil/test_hil_action_service.py

Implement `HILActionService` with a single public method:

```python
async def apply_action(
    item_id: UUID,
    tenant_id: UUID,
    reviewer_id: UUID,
    action: HILAction,
    edited_text: str | None = None,
    feedback_text: str | None = None,
) -> HILActionResult
```

Logic per action:

- **approve**: call `HILResumeService.resume_from_checkpoint(override_text=None)`;
  update item status to `approved`; write `user_feedback` row with
  `feedback_type='approve'`.

- **edit_approve**: call `HILResumeService.resume_from_checkpoint(override_text=edited_text)`;
  update item status to `edited_approved`; write `user_feedback` row with
  `feedback_type='edit'` and `correction=edited_text`.

- **reject**: call `HILResumeService.terminate_workflow`; update item status to `rejected`;
  write `user_feedback` row with `feedback_type='reject'`.

- **reject_with_feedback**: same as reject plus `feedback_type='reject_with_feedback'`
  and `correction=feedback_text`.

For every action, also append a row to the episodic Layer 1 audit log via
`WorkflowRunRepository.append_audit_event(workflow_run_id, event_type='hil_action',
payload={action, reviewer_id, timestamp})` (REQ-N-012).

Validate: `edited_text` required for `edit_approve`; `feedback_text` required for
`reject_with_feedback`. Raise `HILValidationError` otherwise.

**Tests to write first (TDD)**:
- `test_approve_resumes_workflow_and_writes_user_feedback`
- `test_edit_approve_resumes_with_override_text_and_writes_edit_feedback`
- `test_reject_terminates_workflow_and_writes_reject_feedback`
- `test_reject_with_feedback_stores_feedback_text`
- `test_edit_approve_raises_when_edited_text_missing`
- `test_reject_with_feedback_raises_when_feedback_text_missing`
- `test_every_action_writes_layer1_audit_row`

**AC covered**: AC-002, AC-003, AC-004

---

### TASK-006: Deadline timeout Celery task · M/TDD · src/ai/hil/hil_timeout_task.py, tests/unit/ai/hil/test_hil_timeout_task.py

Implement `expire_overdue_hil_items` as a Celery task (scheduled every 60 s by Celery beat).

Logic:
1. Call `HILQueueRepository.list_timed_out_pending(now=utcnow())`.
2. For each item: call `HILActionService.apply_action(..., action='reject')` with a
   system reviewer ID (a fixed sentinel UUID stored in settings).
3. Update status to `timed_out` (override the `rejected` status set by `apply_action` to
   distinguish operator rejection from system timeout).
4. Write an episodic audit row with `event_type='hil_timeout'`.

Register the beat schedule entry in `src/config/celery_app.py`.

**Tests to write first (TDD)**:
- `test_no_items_no_action`
- `test_overdue_item_is_terminated_and_marked_timed_out`
- `test_episodic_audit_row_written_on_timeout`
- `test_non_overdue_pending_items_are_not_touched`

**AC covered**: AC-005

---

### TASK-007: FastAPI HIL endpoints · M/TDD · src/api/routers/hil_router.py, src/api/schemas/hil_schemas.py, tests/integration/api/test_hil_endpoints.py

Implement four FastAPI endpoints under prefix `/api/v1/admin/hil`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all pending items for the authenticated tenant, sorted by `scheduled_send_at` asc |
| GET | `/{item_id}` | Get single item detail including full `WorkflowState.report` preview |
| POST | `/{item_id}/action` | Execute an action (body: `HILActionRequest`) |
| GET | `/count` | Pending count for badge display |

All endpoints:
- Require JWT auth; role guard allows `admin` or `operator` only (return 403 for others).
- Extract `tenant_id` from JWT claims; pass to repository — never accept `tenant_id` from
  request body (prevents cross-tenant access, REQ-N-006).
- Return standard success envelope `{"data": ..., "meta": {}, "error": null}`.
- Return 403 for end_user role; 404 when item not found or belongs to different tenant.

Pydantic response DTOs: `HILQueueItemDTO`, `HILQueueListResponse`, `HILActionResponse`.

**Tests to write first (TDD)**:
- `test_list_returns_200_for_admin_role`
- `test_list_returns_403_for_end_user_role`
- `test_list_items_sorted_by_scheduled_send_at`
- `test_action_approve_returns_200_and_workflow_resumed_true`
- `test_action_edit_approve_returns_200`
- `test_action_reject_returns_200`
- `test_action_on_nonexistent_item_returns_404`
- `test_action_on_other_tenant_item_returns_404`

**AC covered**: AC-002, AC-003, AC-004, AC-006

---

### TASK-008: Admin panel — HIL queue React page · M/TDD · frontend/src/pages/admin/HilQueue.tsx, frontend/src/components/admin/hil/HilQueueTable.tsx, frontend/src/components/admin/hil/HilItemDetail.tsx, frontend/src/components/admin/hil/HilActionButtons.tsx, frontend/src/components/admin/hil/useHilQueue.ts

Build the `/admin/hil` admin panel page.

`useHilQueue.ts`: TanStack Query hook for `GET /api/v1/admin/hil/` and
`POST /api/v1/admin/hil/{item_id}/action`. WebSocket subscription refreshes query cache
on `hil_queue_updated` events.

`HilQueueTable.tsx`: Renders queue items sorted by scheduled send time. Displays:
workflow type, user email, confidence score (colour-coded), scheduled delivery time,
live time-to-send countdown (refreshed every second via `setInterval`), status badge.
Click row to expand `HilItemDetail`.

`HilItemDetail.tsx`: Shows full report preview, per-node confidence breakdown, key
concerns from `WorkflowState.hil_reason`.

`HilActionButtons.tsx`: Renders four action buttons. "Edit & Approve" opens an inline
textarea pre-filled with report text. "Reject with feedback" opens a feedback textarea.
Calls `useHilQueue.executeAction` on submit.

Route is guarded — only renders if `user.role === 'admin' || 'operator'`; otherwise
redirects to `/`.

`AdminLayout.tsx` gains a "HIL Queue" sidebar entry with a pending-count badge sourced
from `GET /api/v1/admin/hil/count` (polled every 30 s).

**Tests to write first (TDD)**:
- `HilQueueTable.test.tsx`: renders items sorted by `scheduled_send_at`; displays
  countdown; shows confidence value colour-coded
- `HilActionButtons.test.tsx`: Approve button calls `executeAction` with `action='approve'`;
  Edit & Approve reveals textarea; Reject with feedback reveals feedback input
- `useHilQueue.test.ts`: `executeAction` calls correct API endpoint; invalidates query
  cache on success
- `HilQueue.test.tsx`: redirects non-admin user to `/`

**AC covered**: AC-001 (queue visible), AC-002, AC-003, AC-004, AC-006

---

### TASK-009: Integration test — full pause-resume and pause-reject flows · M/TDD · tests/integration/hil/test_hil_full_flow.py

Write two end-to-end integration tests against a real PostgreSQL test database with
LangGraph in-process:

**Flow A — pause then approve:**
1. Construct a `WorkflowState` with `requires_hil=True`, confidence=0.55.
2. Call `hil_router_edge` — assert a `hil_queue_item` row is created with
   `status='pending'`.
3. Call `HILActionService.apply_action(action='approve')`.
4. Assert item `status='approved'`, `user_feedback` row exists with
   `feedback_type='approve'`, Layer 1 audit row exists.

**Flow B — pause then reject with feedback:**
1. Same setup with `requires_hil=True`.
2. Call `hil_router_edge`.
3. Call `HILActionService.apply_action(action='reject_with_feedback',
   feedback_text='Insufficient data for recommendation')`.
4. Assert item `status='rejected'`, `user_feedback` row has `feedback_type=
   'reject_with_feedback'` and `correction='Insufficient data for recommendation'`,
   Layer 1 audit row exists, no dispatch occurred.

**Tests to write first (TDD)**:
- `test_full_approve_flow`
- `test_full_reject_with_feedback_flow`

**AC covered**: AC-001, AC-002, AC-004 (integration confirmation)

---

## Acceptance Criteria Coverage

- AC-001: Given confidence in 0.4–0.69, workflow paused via LangGraph checkpoint and HIL item created with status=pending, visible in admin queue sorted by scheduled_send_at → TASK-003, TASK-007, TASK-008, TASK-009
- AC-002: Given reviewer clicks Approve, workflow resumed from checkpoint, Narrative Writer executes, output dispatched, item status=approved → TASK-004, TASK-005, TASK-007, TASK-008, TASK-009
- AC-003: Given reviewer clicks Edit & Approve, reviewer text saved as final output, dispatch occurs, user_feedback row written with feedback_type=edit → TASK-005, TASK-007, TASK-008
- AC-004: Given reviewer clicks Reject or Reject with feedback, workflow terminated, no dispatch, user_feedback row written with correct feedback_type and optional correction → TASK-004, TASK-005, TASK-007, TASK-008, TASK-009
- AC-005: Given HIL item deadline passes without reviewer action, workflow automatically terminated, no dispatch, admin audit console records timeout → TASK-006, TASK-002
- AC-006: Given an end-user (non-admin) accesses the HIL queue endpoint, response is HTTP 403 → TASK-007, TASK-008

## Risks and Notes

- **LangGraph checkpoint API stability:** LangGraph's `AsyncPostgresSaver` is the
  mandatory checkpoint backend (architecture §7.1). The exact API for reading
  `checkpoint_id` after a save may vary across LangGraph versions. Pin the LangGraph
  version in `pyproject.toml` and document the pinned API surface in `hil_router.py`.

- **Celery task / parked workflow interaction:** When the graph reaches the `hil_pending`
  terminal node the Celery task must park (return without error) without killing the
  LangGraph process state. The checkpoint holds all state in PostgreSQL; the Celery task
  can exit. Resume is a fresh Celery task dispatched by `HILActionService`.

- **Timing window derivation:** The `scheduled_send_at` for Morning Brief and Watchlist
  Scan is the next occurrence of 05:45 / 17:45 local time. If the workflow arrives after
  the deadline on the same day, the next-day deadline applies. This logic must be unit
  tested (TASK-003).

- **Tenant_id in JWT claims:** `HILActionService` must never accept `tenant_id` from the
  request body; it must always be extracted from the validated JWT. The repository
  enforces this at the data layer as a second line of defence (REQ-N-006).

- **PLAN-F-015 dependency:** `user_feedback` table DDL and `UserFeedbackRepository` are
  owned by PLAN-F-015. This plan consumes them but does not redefine them. TASK-005
  assumes `UserFeedbackRepository.create(feedback: UserFeedbackCreate) -> UserFeedback`
  is available. If PLAN-F-015 execution is delayed, TASK-005 is blocked.

- **WebSocket HIL push:** Real-time queue updates in the frontend rely on the WebSocket
  channel. The WebSocket manager (PLAN-F-001 or a shared `api` module) must support
  broadcasting `hil_queue_updated` events to admin sessions. If the broadcast channel is
  not yet available, the frontend falls back to 30-second polling with no functional
  regression.
