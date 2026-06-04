---
plan_id: PLAN-F-029
slug: admin-ai-audit-console
title: Admin AI Audit Console
linked_requirement: REQ-F-029
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-008, reason: "Every AI decision row links to a Langfuse trace URL — the searchable log is the primary AI observability surface for operators" }
  - { id: REQ-N-009, reason: "Prompt rollback via this console must propagate to agents within 60 seconds per the safety-gate SLA" }
  - { id: REQ-N-010, reason: "Calibration dashboard surfaces CORR(confidence, actual_t1d × direction_sign) from the Tier 3 daily job; operators act on the warning flag produced here" }
  - { id: REQ-N-012, reason: "Admin override writes an immutable user_feedback row to Layer 4; golden_dataset candidate records extend the compliance audit chain" }
dependencies:
  - { id: PLAN-F-016, reason: "Calibration dashboard reads calibration_result rows and CalibrationSummary API contract from the Three-Tier Evaluation Framework" }
  - { id: PLAN-F-014, reason: "Prompt version history is backed by prompt_publication table; rollback calls IPromptLabelService.rollback() from the Prompt Management Pipeline" }
  - { id: PLAN-F-015, reason: "Admin override writes user_feedback rows to Layer 4 via IFeedbackRepository; workflow_run history reads IEpisodicRepository" }
executed_at: 2026-06-04T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-04T00:00:00Z
---

# PLAN-F-029 — Admin AI Audit Console

## Linked Requirement
**REQ-F-029** — Admin AI Audit Console
Status: approved | Jira:

## Objective

Build the Admin AI Audit Console — the single operational surface from which administrators gain complete visibility and control over every AI decision in StokAI. The implementation delivers four integrated panels under `/admin/ai-audit`:

1. A **searchable AI decision log** backed by the `ai_decision` table (new), searchable by date range, model, agent role, confidence range, action signal, and company; each row expands to full detail including the Langfuse trace URL.
2. An **admin override workflow** that writes a `user_feedback` row to Layer 4 with `feedback_type=admin_override` via `IFeedbackRepository`, adds the decision to the `golden_dataset` candidate pool via `GoldenDatasetService`, and surfaces a proposed prompt adjustment for human review.
3. A **prompt version history panel** that reads `prompt_publication` rows per agent role and exposes a Rollback button that calls `IPromptLabelService.rollback()` — effective within 60 seconds per REQ-N-009.
4. A **Tier 3 calibration dashboard** displaying `CORR(confidence, actual_t1d × direction_sign)` over configurable lookback windows (30/60/90 days) with a warning indicator when CORR falls below the threshold, reading from the `CalibrationSummary` API provided by PLAN-F-016.
5. A **Mode B workflow history** panel showing all `workflow_run` rows with per-run detail (agent invocations, tool calls, cost breakdown) and a Re-run button that re-dispatches the same workflow inputs with current production prompts.

The backend is a FastAPI module under `src/api/admin/audit/`; the frontend is React components under `src/frontend/admin/ai-audit/`. All endpoints are ADMIN-role-gated. All mutations write immutable audit records.

## Architecture Context

This plan operates across four architecture sections.

**Section 11 (Admin Panel):** The AI Audit Console is explicitly listed as one of the five Admin panel sections (§11, "Admin panel sections" table). It lives under `/admin` on the same React app, guarded by `role === "admin"`. The four sub-panels map directly to this plan's five panels.

**Section 10 (Data Model):** Three existing tables are read-heavily: `ai_recommendation` (action signal, confidence, model, analogies), `workflow_run` / `agent_invocation` / `tool_call` (Mode B history), and `user_feedback` (Layer 4, feedback_type=admin_override). One new table is introduced: `ai_decision` — an audit log row that denormalises every AI classification or recommendation into a single queryable record with a `langfuse_trace_url` column. The `golden_dataset_item` table (PLAN-F-016) and `prompt_publication` table (PLAN-F-014) are read via their respective service contracts.

**Section 8 (Prompt Management):** The rollback path calls `IPromptLabelService.rollback(role_id, to_version)` from PLAN-F-014. No prompt change is applied without human approval; the console surfaces proposals only — it never auto-applies changes.

**Section 9 (Evaluation Framework — Tier 3):** The calibration dashboard reads `GET /api/v1/evaluation/calibration/summary` and `GET /api/v1/evaluation/calibration` (both provided by PLAN-F-016 TASK-009/TASK-011). This plan adds no new Tier 3 computation — it provides the frontend rendering and the backend pass-through for the admin panel.

**Section 7.4 (Four-Layer Memory — Layer 4):** Admin override calls `IFeedbackRepository.append_feedback` with `feedback_type=admin_override` via the `MemoryService` already established by PLAN-F-015. The override also calls `GoldenDatasetService.create_candidate` (PLAN-F-016) so the corrected decision enters the golden dataset candidate pool.

**Section 12.1 (Authorization):** Every endpoint in this plan asserts `current_user.role == "admin"` and returns 403 otherwise. The React route is guarded by a `RequireAdmin` wrapper component.

**Section 5 (Backend Module Map):** New API code lives in `src/api/admin/audit/`. Services are thin orchestrators that delegate to: `IEpisodicRepository` (workflow history), `IFeedbackRepository` (Layer 4 write), `GoldenDatasetService` (PLAN-F-016), `ICalibrationRepository` (Tier 3 data), and `IPromptPublicationRepository` + `IPromptLabelService` (PLAN-F-014). No business logic in controllers — parse, validate, delegate, respond.

## Component Design

### New Components

```
Backend: src/api/admin/audit/
  ├── __init__.py
  ├── audit_router.py              — FastAPI router: all five panel endpoints, ADMIN-gated
  ├── audit_api_schemas.py         — Pydantic: request/response DTOs for all five panels
  └── audit_service.py             — AuditService: orchestrates calls to dependency services

DB: alembic/versions/XXXX_ai_decision_table.py
  — ai_decision table (audit log row per requirement data model)

Frontend: src/frontend/admin/ai-audit/
  ├── AiAuditConsolePage.tsx        — Top-level page; tab navigation for the four panels
  ├── DecisionLogPanel.tsx          — Searchable/filterable decision log; row expansion
  ├── DecisionLogFilter.tsx         — Date, model, agent_role, confidence range, action_signal, company filters
  ├── DecisionDetailDrawer.tsx      — Full detail view with Langfuse trace URL link; Override button
  ├── OverrideModal.tsx             — Admin correction input; confirmation step; displays proposed prompt adjustment
  ├── PromptVersionPanel.tsx        — Per-agent prompt version list with quality metrics
  ├── RollbackConfirmModal.tsx      — Rollback confirmation with SLA callout (effective < 60 s)
  ├── CalibrationDashboard.tsx      — CORR chart; per-signal accuracy; lookback selector; warning banner
  ├── WorkflowHistoryPanel.tsx      — workflow_run list; per-run detail accordion; Re-run button
  ├── WorkflowDetailDrawer.tsx      — Agent invocations, tool calls, cost breakdown per run
  └── hooks/
      ├── useDecisionLog.ts         — TanStack Query: paginated decision log fetch + filters
      ├── useAdminOverride.ts       — Mutation hook: POST override
      ├── usePromptHistory.ts       — TanStack Query: prompt version history per agent
      ├── useRollback.ts            — Mutation hook: POST rollback
      ├── useCalibration.ts         — TanStack Query: calibration summary + time-series
      └── useWorkflowHistory.ts     — TanStack Query: workflow list + per-run detail

Frontend shared:
  src/frontend/admin/RequireAdmin.tsx  — HOC: redirects non-admin users to /
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/api/admin/__init__.py` | Register `audit_router` on the admin API prefix | Wire new router into existing admin module |
| `src/frontend/admin/AdminLayout.tsx` | Add "AI Audit" nav link pointing to `/admin/ai-audit` | Surface new console in admin navigation |
| `src/config/settings.py` | Add `CALIBRATION_WARN_THRESHOLD` (default 0.3) setting | Configurable CORR warning threshold for calibration dashboard |

### Interfaces and Contracts

```python
# src/api/admin/audit/audit_api_schemas.py

class AIDecisionRow(BaseModel):
    """One row in the decision log table."""
    decision_id: UUID
    agent_role: str
    model: str
    prompt_version: str          # SHA
    confidence: float
    inputs_summary: str          # truncated for table view
    action_signal: str | None    # e.g. HOLD / BUY_OPP / REDUCE_RISK
    company_ticker: str | None
    output_text: str             # truncated for table view
    langfuse_trace_url: str
    workflow_run_id: UUID | None
    created_at: datetime

class AIDecisionDetail(AIDecisionRow):
    """Expanded full detail for a single decision."""
    inputs_full: str
    retrieved_analogs: list[dict]
    output_text_full: str        # not truncated

class DecisionLogFilter(BaseModel):
    date_from: datetime | None = None
    date_to: datetime | None = None
    model: str | None = None
    agent_role: str | None = None
    confidence_min: float | None = None
    confidence_max: float | None = None
    action_signal: str | None = None
    company_ticker: str | None = None
    cursor: str | None = None    # cursor-based pagination
    limit: int = 50

class AdminOverrideRequest(BaseModel):
    decision_id: UUID
    corrected_output: str
    override_reason: str

class AdminOverrideResponse(BaseModel):
    feedback_id: UUID            # user_feedback row ID (Layer 4)
    golden_dataset_candidate_id: UUID
    proposed_prompt_adjustment: str  # human-readable proposal text
    status: str                  # "pending_review"

class PromptVersionEntry(BaseModel):
    version_id: str              # SHA
    agent_role: str
    label_applied: str           # production | staging | canary | experimental
    action: str                  # publish | label | rollback
    quality_metrics: dict | None # JSONB from golden_dataset regression for this version
    published_at: datetime
    rolled_back_at: datetime | None

class RollbackRequest(BaseModel):
    agent_role: str
    to_version: str              # SHA

class RollbackResponse(BaseModel):
    previous_version: str
    rolled_back_to: str
    effective_at: datetime

class WorkflowRunSummary(BaseModel):
    workflow_id: UUID
    workflow_type: str
    user_id: UUID | None
    status: str
    cost_usd: float
    duration_ms: int | None
    started_at: datetime
    completed_at: datetime | None

class WorkflowRunDetail(WorkflowRunSummary):
    agent_invocations: list[AgentInvocationSummary]
    tool_calls: list[ToolCallSummary]
    langfuse_trace_id: str | None

class AgentInvocationSummary(BaseModel):
    invocation_id: UUID
    agent_role_id: str
    model_used: str
    prompt_version: str
    confidence: float | None
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int

class ToolCallSummary(BaseModel):
    tool_call_id: UUID
    invocation_id: UUID
    tool_name: str
    duration_ms: int
    cost_tier: str
    cached: bool

class RerunRequest(BaseModel):
    workflow_id: UUID            # source run to re-trigger

class RerunResponse(BaseModel):
    new_workflow_id: UUID
    workflow_type: str
    dispatched_at: datetime


# src/api/admin/audit/audit_service.py

class AuditService:
    """
    Orchestrates the five audit panel operations. Constructor-injected dependencies:
      - IEpisodicRepository  (from PLAN-F-015)
      - IFeedbackRepository  (from PLAN-F-015)
      - GoldenDatasetService (from PLAN-F-016)
      - ICalibrationRepository (from PLAN-F-016)
      - IPromptPublicationRepository (from PLAN-F-014)
      - IPromptLabelService  (from PLAN-F-014)
      - IAIDecisionRepository (new, defined in this plan)
    """

    async def list_decisions(
        self, filters: DecisionLogFilter
    ) -> tuple[list[AIDecisionRow], str | None]: ...
    # Returns (rows, next_cursor). Cursor-based pagination (Architecture §5 API layer).

    async def get_decision_detail(self, decision_id: UUID) -> AIDecisionDetail: ...

    async def apply_override(
        self,
        request: AdminOverrideRequest,
        admin_user_id: UUID,
    ) -> AdminOverrideResponse: ...
    # 1. Appends user_feedback row (feedback_type="admin_override") via IFeedbackRepository.
    # 2. Fetches full AIDecision to build golden dataset input/output pair.
    # 3. Calls GoldenDatasetService.create_candidate(source="admin_override").
    # 4. Generates proposed_prompt_adjustment string (template-based, not LLM-generated).
    # 5. Returns AdminOverrideResponse.

    async def list_prompt_history(
        self, agent_role: str, limit: int = 50
    ) -> list[PromptVersionEntry]: ...

    async def rollback_prompt(self, request: RollbackRequest) -> RollbackResponse: ...
    # Calls IPromptLabelService.rollback(role_id, to_version).

    async def list_workflow_runs(
        self, cursor: str | None, limit: int = 50
    ) -> tuple[list[WorkflowRunSummary], str | None]: ...

    async def get_workflow_detail(self, workflow_id: UUID) -> WorkflowRunDetail: ...

    async def rerun_workflow(
        self, request: RerunRequest, admin_user_id: UUID
    ) -> RerunResponse: ...
    # 1. Loads source WorkflowRun via IEpisodicRepository.get_workflow_run.
    # 2. Extracts workflow_type and inputs from final_state.
    # 3. Enqueues a new Celery task for the same workflow type with same inputs.
    # 4. Appends a new workflow_run row for the re-run via IEpisodicRepository.
    # 5. Returns RerunResponse with new_workflow_id.


# src/ai/decision_log/interfaces/i_ai_decision_repository.py

class IAIDecisionRepository(ABC):
    @abstractmethod
    async def insert(self, decision: AIDecisionCreate) -> AIDecisionRow: ...
    @abstractmethod
    async def get_by_id(self, decision_id: UUID) -> AIDecisionDetail | None: ...
    @abstractmethod
    async def list_paginated(
        self,
        filters: DecisionLogFilter,
    ) -> tuple[list[AIDecisionRow], str | None]: ...
    # Returns (rows, next_cursor). Uses keyset/cursor pagination on (created_at, decision_id).
```

## Implementation Tasks

### TASK-001: DB migration — ai_decision audit log table · M/TDD · alembic/versions/XXXX_ai_decision_table.py

Create the `ai_decision` table that denormalises every AI classification and recommendation into a single queryable audit row.

Schema:

```sql
ai_decision (
    decision_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_role        VARCHAR     NOT NULL,
    model             VARCHAR     NOT NULL,
    prompt_version    VARCHAR(40) NOT NULL,   -- git SHA
    confidence        FLOAT       NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    inputs_summary    TEXT        NOT NULL,   -- first 500 chars of inputs
    inputs_full       TEXT        NOT NULL,   -- complete inputs JSON
    retrieved_analogs JSONB       NOT NULL DEFAULT '[]',
    action_signal     VARCHAR     NULL,       -- HOLD | BUY_OPP | etc; null for classifications
    company_ticker    VARCHAR     NULL,
    output_text       TEXT        NOT NULL,
    langfuse_trace_url VARCHAR    NOT NULL,
    workflow_run_id   UUID        NULL REFERENCES workflow_run(workflow_id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

Indexes: composite index on `(created_at DESC, decision_id)` for cursor-based pagination; index on `agent_role`; index on `company_ticker`; index on `action_signal`; GIN index on `retrieved_analogs`.

This table is populated by Mode A pipeline (classify_event, generate_alert_text steps) and all Mode B AgentNode invocations that produce a user-facing output. Population is out of scope for this plan; this plan owns the table definition and repository.

**Tests to write first (TDD)**:
- Test migration applies cleanly; all columns exist with correct types and constraints.
- Test `confidence` CHECK rejects values outside [0.0, 1.0].
- Test inserting a row with `action_signal=NULL` and `company_ticker=NULL` succeeds (classification-type decisions).
- Test inserting a row with `workflow_run_id` referencing a non-existent `workflow_run` raises FK violation.
- Test the composite index exists on `(created_at DESC, decision_id)`.

**AC covered**: AC-001

---

### TASK-002: SQLAlchemy ORM model, Pydantic schemas, and IAIDecisionRepository · M/TDD · src/ai/decision_log/__init__.py, src/ai/decision_log/models/ai_decision_model.py, src/ai/decision_log/schemas/ai_decision_schemas.py, src/ai/decision_log/interfaces/i_ai_decision_repository.py, src/ai/decision_log/repositories/ai_decision_repository.py

Define the `AIDecision` SQLAlchemy 2.0 `Mapped[]`-annotated ORM model. `retrieved_analogs` maps to `JSONB`.

Define Pydantic v2 schemas: `AIDecisionCreate`, `AIDecisionRow` (truncated view — `inputs_summary` from first 500 chars, `output_text` truncated to 300 chars), `AIDecisionDetail` (full fields, no truncation).

Implement `AIDecisionRepository`:

- `insert(decision: AIDecisionCreate) -> AIDecisionRow`: plain `INSERT`; returns created row.
- `get_by_id(decision_id: UUID) -> AIDecisionDetail | None`: returns full detail or `None`.
- `list_paginated(filters: DecisionLogFilter) -> tuple[list[AIDecisionRow], str | None]`: builds a parameterised WHERE clause from non-null filter fields; applies keyset pagination using `(created_at, decision_id)` as the cursor tuple encoded as a base64 string; returns at most `filters.limit` rows and the next cursor or `None` if exhausted.

All filter fields are optional. Multiple active filters are combined with AND. Confidence range is `confidence BETWEEN :min AND :max`. Date range uses `created_at >= :from AND created_at <= :to`.

**Tests to write first (TDD)**:
- Test `insert` persists a row and returns it with `decision_id` populated.
- Test `get_by_id` returns `None` for an unknown UUID.
- Test `get_by_id` returns full `inputs_full` (not truncated).
- Test `list_paginated` with no filters returns the most recent rows ordered by `(created_at DESC, decision_id)`.
- Test `list_paginated` with `confidence_min=0.7` excludes rows with confidence < 0.7.
- Test `list_paginated` with `agent_role="narrative_writer"` excludes rows with other roles.
- Test cursor pagination: request page 1, extract cursor, request page 2 with that cursor; assert page 2 starts after the last row of page 1 with no overlap.
- Test `list_paginated` returns `next_cursor=None` when total rows are fewer than limit.

**AC covered**: AC-001

---

### TASK-003: AuditService — decision log and override operations · M/TDD · src/api/admin/audit/audit_service.py, src/api/admin/audit/audit_api_schemas.py

Implement `AuditService.list_decisions`, `AuditService.get_decision_detail`, and `AuditService.apply_override`.

`list_decisions` delegates to `IAIDecisionRepository.list_paginated` and returns the row list and cursor.

`get_decision_detail` delegates to `IAIDecisionRepository.get_by_id`; raises `NotFoundError` if the decision is absent.

`apply_override(request, admin_user_id)`:
1. Calls `IAIDecisionRepository.get_by_id(request.decision_id)` to load the full decision detail. Raises `NotFoundError` if absent.
2. Calls `IFeedbackRepository.append_feedback` with: `feedback_type="admin_override"`, `feedback_text=request.override_reason`, `user_edit=request.corrected_output`, `reviewer_id=admin_user_id`, `source="hil_action"`. The `report_id` and `recommendation_id` fields are populated from `decision.workflow_run_id` if present; both may be `None` for standalone classifications.
3. Calls `GoldenDatasetService.create_candidate` with `input={"inputs_full": decision.inputs_full, "retrieved_analogs": decision.retrieved_analogs}`, `expected_output={"output_text": request.corrected_output}`, `quality_metrics={}`, `source="admin_override"`.
4. Generates a `proposed_prompt_adjustment` string by template: `"Agent {role} produced output that was manually corrected. Original confidence: {confidence:.2f}. Suggested review: prompt may over-weight {analogue_count} analogues when confidence is below {confidence:.2f}."` — this is a rule-based hint, not an LLM call.
5. Returns `AdminOverrideResponse` with all IDs and the proposal string.

The golden dataset candidate is NOT auto-activated; it is a candidate pending approval per PLAN-F-016 contract.

**Tests to write first (TDD)**:
- Test `list_decisions` with an empty filter delegates to `IAIDecisionRepository.list_paginated` and returns results.
- Test `get_decision_detail` returns `AIDecisionDetail` when the decision exists.
- Test `get_decision_detail` raises `NotFoundError` when decision is absent.
- Test `apply_override` with a valid decision: assert `IFeedbackRepository.append_feedback` is called with `feedback_type="admin_override"`.
- Test `apply_override` asserts `GoldenDatasetService.create_candidate` is called with `source="admin_override"`.
- Test `apply_override` returns `AdminOverrideResponse.status == "pending_review"`.
- Test `apply_override` with an unknown `decision_id` raises `NotFoundError` without calling any downstream service.
- Test `proposed_prompt_adjustment` contains the agent role name and confidence value.

**AC covered**: AC-001, AC-002

---

### TASK-004: AuditService — prompt version history and rollback operations · M/TDD · src/api/admin/audit/audit_service.py (extended)

Extend `AuditService` with `list_prompt_history` and `rollback_prompt`.

`list_prompt_history(agent_role, limit=50)`:
1. Calls `IPromptPublicationRepository.list_by_role(agent_role, limit=limit)` to retrieve `PromptPublication` rows ordered by `published_at DESC`.
2. Maps each `PromptPublication` to a `PromptVersionEntry`, enriching `quality_metrics` by looking up the most recent golden dataset regression report stored in `evaluation_result` rows whose `prompt_version` matches the SHA (via `IEvaluationRepository.list_recent` filtered by version; `quality_metrics` is derived from `scores` JSON on the evaluation result).
3. Sets `rolled_back_at` on an entry when a subsequent `action="rollback"` row exists for the same `role_id` and `sha` in the publication history.
4. Returns the list of `PromptVersionEntry` objects.

`rollback_prompt(request: RollbackRequest) -> RollbackResponse`:
1. Calls `IPromptLabelService.rollback(request.agent_role, request.to_version)` from PLAN-F-014.
2. The Langfuse re-label is complete when `rollback()` returns. Per PLAN-F-014, the full round-trip takes < 10 seconds; agents pick up the new label within 60 seconds (REQ-N-009 SLA).
3. Returns `RollbackResponse` with `previous_version`, `rolled_back_to`, and `effective_at`.

**Tests to write first (TDD)**:
- Test `list_prompt_history` returns entries sorted by `published_at DESC`.
- Test `list_prompt_history` sets `quality_metrics` from the matching evaluation result when one exists.
- Test `list_prompt_history` sets `quality_metrics=None` when no evaluation result matches the SHA.
- Test `list_prompt_history` sets `rolled_back_at` on an entry when a rollback publication row exists for that version.
- Test `rollback_prompt` calls `IPromptLabelService.rollback` with correct `role_id` and SHA.
- Test `rollback_prompt` returns `RollbackResponse.rolled_back_to` matching the requested version SHA.
- Test `rollback_prompt` propagates `LangfuseLabelError` as a service-level `RollbackError` (typed domain exception).

**AC covered**: AC-003

---

### TASK-005: AuditService — workflow history and re-run operations · M/TDD · src/api/admin/audit/audit_service.py (extended)

Extend `AuditService` with `list_workflow_runs`, `get_workflow_detail`, and `rerun_workflow`.

`list_workflow_runs(cursor, limit=50)`:
1. Calls `IEpisodicRepository.list_recent_runs(tenant_id=None, limit=limit+1)` with optional cursor decoding to apply keyset pagination on `(started_at DESC, workflow_id)`.
2. Returns `list[WorkflowRunSummary]` and `next_cursor`.

`get_workflow_detail(workflow_id)`:
1. Calls `IEpisodicRepository.get_workflow_run(workflow_id)`. Raises `NotFoundError` if absent.
2. Queries `agent_invocation` rows for the run (new method: `IEpisodicRepository.list_invocations_for_run(workflow_id)`).
3. Queries `tool_call` rows for each invocation (new method: `IEpisodicRepository.list_tool_calls_for_run(workflow_id)`).
4. Maps to `WorkflowRunDetail`.

`rerun_workflow(request, admin_user_id)`:
1. Loads source run via `IEpisodicRepository.get_workflow_run(request.workflow_id)`. Raises `NotFoundError` if absent.
2. Extracts `workflow_type` and `inputs` from the source run's `final_state` JSONB field.
3. Dispatches a new Celery task for the workflow type using the `workflow_runner.dispatch(workflow_type, inputs)` function (interface contract: accepts `workflow_type: str`, `inputs: dict[str, Any]`; returns a new `workflow_id: UUID`).
4. Returns `RerunResponse(new_workflow_id, workflow_type, dispatched_at=utcnow())`.

The re-run always uses the current production prompt versions — there is no mechanism to re-run with historical prompts (out of scope per requirement: "with current prompts").

**Tests to write first (TDD)**:
- Test `list_workflow_runs` returns summaries with correct fields.
- Test `list_workflow_runs` cursor pagination: two pages do not overlap.
- Test `get_workflow_detail` returns `WorkflowRunDetail` including agent invocations and tool calls.
- Test `get_workflow_detail` raises `NotFoundError` when the workflow does not exist.
- Test `rerun_workflow` calls `workflow_runner.dispatch` with the correct `workflow_type` and `inputs` extracted from the source run.
- Test `rerun_workflow` returns `RerunResponse.new_workflow_id` matching the UUID returned by `dispatch`.
- Test `rerun_workflow` raises `NotFoundError` when source `workflow_id` does not exist.

Note: `list_invocations_for_run` and `list_tool_calls_for_run` are new methods added to `IEpisodicRepository`. Define them in the interface and implement them in `EpisodicRepository` (from PLAN-F-015) within this task's scope.

**AC covered**: AC-005

---

### TASK-006: FastAPI audit router — all five panel endpoints · M/TDD · src/api/admin/audit/__init__.py, src/api/admin/audit/audit_router.py

Implement all REST endpoints. Controllers do only: parse, validate, check admin role, delegate to `AuditService`, respond. Zero business logic in the router.

**Decision log endpoints:**
- `GET /api/v1/admin/audit/decisions` — admin-only; accepts `DecisionLogFilter` as query params; returns `{ "data": list[AIDecisionRow], "next_cursor": str | null }`.
- `GET /api/v1/admin/audit/decisions/{decision_id}` — admin-only; returns `AIDecisionDetail`.

**Override endpoint:**
- `POST /api/v1/admin/audit/decisions/{decision_id}/override` — admin-only; body: `AdminOverrideRequest`; returns 201 `AdminOverrideResponse`.

**Prompt version history endpoints:**
- `GET /api/v1/admin/audit/prompts/{agent_role}/history` — admin-only; query param `limit` (default 50); returns `list[PromptVersionEntry]`.
- `POST /api/v1/admin/audit/prompts/{agent_role}/rollback` — admin-only; body: `RollbackRequest`; returns 200 `RollbackResponse`.

**Calibration dashboard endpoints (pass-through to PLAN-F-016):**
- `GET /api/v1/admin/audit/calibration` — admin-only; query params: `days` (default 30, allowed: 30, 60, 90), `action_signal`; proxies to `ICalibrationRepository.list_last_n_days`; returns `list[CalibrationResult]`.
- `GET /api/v1/admin/audit/calibration/summary` — admin-only; query param `days`; proxies to `Tier3CalibrationService.get_calibration_summary`; returns `CalibrationSummary`.

**Workflow history endpoints:**
- `GET /api/v1/admin/audit/workflows` — admin-only; query params: `cursor`, `limit`; returns `{ "data": list[WorkflowRunSummary], "next_cursor": str | null }`.
- `GET /api/v1/admin/audit/workflows/{workflow_id}` — admin-only; returns `WorkflowRunDetail`.
- `POST /api/v1/admin/audit/workflows/{workflow_id}/rerun` — admin-only; returns 202 `RerunResponse`.

All routes use `Depends(get_current_admin_user)` — a dependency that asserts `current_user.role == "admin"` and returns 403 otherwise (identical pattern to PLAN-F-016 TASK-009).

**Tests to write first (TDD)**:
- Test `GET /api/v1/admin/audit/decisions` by a non-admin returns 403.
- Test `GET /api/v1/admin/audit/decisions` by an unauthenticated request returns 401.
- Test `GET /api/v1/admin/audit/decisions` with `confidence_min=0.7` returns only high-confidence decisions.
- Test `GET /api/v1/admin/audit/decisions/{decision_id}` with a valid ID returns 200 with `langfuse_trace_url` present.
- Test `GET /api/v1/admin/audit/decisions/{decision_id}` with an unknown ID returns 404.
- Test `POST .../override` with valid body returns 201 and `golden_dataset_candidate_id` is populated.
- Test `GET .../prompts/{role}/history` returns list of `PromptVersionEntry` with `version_id` and `published_at`.
- Test `POST .../prompts/{role}/rollback` returns 200 with `effective_at` timestamp.
- Test `GET .../calibration/summary` with `days=30` returns a `CalibrationSummary` with `below_threshold` bool.
- Test `GET .../calibration` with `days=90` delegates with `days=90`.
- Test `GET .../workflows` returns paginated list; `next_cursor` is null on last page.
- Test `GET .../workflows/{id}` returns `agent_invocations` and `tool_calls` arrays.
- Test `POST .../workflows/{id}/rerun` returns 202 with `new_workflow_id`.
- Test `POST .../workflows/{unknown_id}/rerun` returns 404.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

### TASK-007: Frontend — AiAuditConsolePage and DecisionLogPanel · M/TDD · src/frontend/admin/ai-audit/AiAuditConsolePage.tsx, src/frontend/admin/ai-audit/DecisionLogPanel.tsx, src/frontend/admin/ai-audit/DecisionLogFilter.tsx, src/frontend/admin/ai-audit/DecisionDetailDrawer.tsx, src/frontend/admin/ai-audit/hooks/useDecisionLog.ts

Build the top-level console page with a four-tab layout (Decision Log | Prompt History | Calibration | Workflow History) using React 18 and the project's component library. Tab switching is controlled by React state; no URL routing between tabs.

`DecisionLogPanel` renders the decisions table. Columns: timestamp, agent_role, model, prompt_version (SHA abbreviated to 7 chars), confidence (color-coded: ≥0.7 green, 0.4–0.69 amber, <0.4 red), action_signal, company_ticker, Langfuse link (external link icon).

`DecisionLogFilter` renders filter controls: date-range picker, model select, agent_role select, confidence range sliders, action_signal select, company ticker text input. Applies filters on "Apply" button click. Resets on "Clear".

`DecisionDetailDrawer` is a side drawer that opens when a row is clicked. Shows all fields of `AIDecisionDetail` including the full `inputs_full`, `retrieved_analogs` as a collapsible JSON viewer, and `langfuse_trace_url` as a clickable link. Contains the "Override" button that opens `OverrideModal`.

`useDecisionLog` hook uses TanStack Query with `keepPreviousData: true` for smooth pagination. Cursor navigation: "Next page" appends the returned `next_cursor` as a query param. Filter changes reset the cursor.

**Tests to write first (TDD)**:
- Test `useDecisionLog` with mocked fetch: initial load returns first page rows.
- Test `useDecisionLog` cursor navigation: calling `loadNextPage()` passes the returned cursor to the next request.
- Test `useDecisionLog` with `confidence_min=0.7` filter sends `confidence_min=0.7` in the API request.
- Test `DecisionLogPanel` renders a table row for each returned decision.
- Test clicking a table row opens `DecisionDetailDrawer` with the correct `decision_id`.
- Test `DecisionDetailDrawer` renders the `langfuse_trace_url` as an anchor with `target="_blank"`.
- Test `DecisionLogFilter` "Clear" resets all filter fields and triggers a re-fetch with no filters.

**AC covered**: AC-001

---

### TASK-008: Frontend — OverrideModal and override submission · M/TDD · src/frontend/admin/ai-audit/OverrideModal.tsx, src/frontend/admin/ai-audit/hooks/useAdminOverride.ts

`OverrideModal` is a modal dialog opened from `DecisionDetailDrawer` "Override" button.

Content: original decision summary (agent role, model, confidence, truncated output); text area for "Corrected output" (required, min 10 chars); text input for "Override reason" (required, min 20 chars); "Submit Override" button; "Cancel" button.

On submit: calls `useAdminOverride.mutate(request)`. On success: displays the `proposed_prompt_adjustment` text in a read-only box with a header "Proposed prompt adjustment (requires admin approval)". Closes the modal after the admin acknowledges. On error: displays the error message in-modal without closing.

`useAdminOverride` is a TanStack Query mutation that POSTs to `POST /api/v1/admin/audit/decisions/{decision_id}/override`. On success, it invalidates the decision log query to refresh the list.

**Tests to write first (TDD)**:
- Test `OverrideModal` submit button is disabled when `corrected_output` is empty.
- Test `OverrideModal` submit button is disabled when `override_reason` is fewer than 20 chars.
- Test `OverrideModal` calls `useAdminOverride.mutate` with correct `decision_id`, `corrected_output`, and `override_reason` on valid submit.
- Test `OverrideModal` displays `proposed_prompt_adjustment` text after successful submission.
- Test `OverrideModal` displays an error message when the mutation returns a non-2xx response.
- Test `useAdminOverride` mutation POSTs to the correct endpoint with the serialised body.

**AC covered**: AC-002

---

### TASK-009: Frontend — PromptVersionPanel and RollbackConfirmModal · M/TDD · src/frontend/admin/ai-audit/PromptVersionPanel.tsx, src/frontend/admin/ai-audit/RollbackConfirmModal.tsx, src/frontend/admin/ai-audit/hooks/usePromptHistory.ts, src/frontend/admin/ai-audit/hooks/useRollback.ts

`PromptVersionPanel` renders a per-agent accordion. At the top level, a `Select` control lets the admin choose an `agent_role`. Below it, a table of `PromptVersionEntry` rows shows: SHA (abbreviated), `label_applied`, `published_at`, `rolled_back_at` (if present), and quality_metrics key values (e.g. `factual_grounding`, `confidence_calibration`). Each non-rolled-back row has a "Rollback" button.

`RollbackConfirmModal` opens on "Rollback" click. Shows: "You are rolling back {agent_role} to version {sha}. This will take effect within 60 seconds." Confirm and Cancel buttons.

On confirm: calls `useRollback.mutate({ agent_role, to_version })`. On success: displays "Rollback applied at {effective_at}. Agents will use this version within 60 seconds." On error: displays error message.

`useRollback` mutation POSTs to `POST /api/v1/admin/audit/prompts/{agent_role}/rollback`.

**Tests to write first (TDD)**:
- Test `PromptVersionPanel` renders table rows for each `PromptVersionEntry`.
- Test a row with `rolled_back_at` does not show a "Rollback" button.
- Test a row without `rolled_back_at` shows a "Rollback" button.
- Test clicking "Rollback" opens `RollbackConfirmModal` with the correct SHA.
- Test `RollbackConfirmModal` displays the "60 seconds" SLA callout text.
- Test `RollbackConfirmModal` "Cancel" does not call the mutation.
- Test `useRollback` mutation calls the correct endpoint with `agent_role` and `to_version`.
- Test `PromptVersionPanel` displays quality metrics columns when `quality_metrics` is non-null.

**AC covered**: AC-003

---

### TASK-010: Frontend — CalibrationDashboard · M/TDD · src/frontend/admin/ai-audit/CalibrationDashboard.tsx, src/frontend/admin/ai-audit/hooks/useCalibration.ts

`CalibrationDashboard` renders three elements:

1. **Warning banner**: shown when `CalibrationSummary.below_threshold === true`. Text: "Warning: CORR(confidence, actual_t1d × direction_sign) has dropped below the threshold ({threshold}). Review and trigger improvement loop." Banner color: amber background, bold text.

2. **CORR time-series chart**: uses Recharts `LineChart`. X-axis: date. Y-axis: `corr_confidence_actual` value (range -1 to 1). One line per `action_signal`. Reference line at y=0.3 (threshold). Rendered from `list[CalibrationResult]` returned by `GET /api/v1/admin/audit/calibration`.

3. **Per-signal accuracy table**: shows `action_signal`, `direction_correct_pct`, `mean_confidence`, `total_recommendations` for each signal in the summary.

Lookback selector: segmented control with options 30, 60, 90 days. Changing the selector re-fetches both the chart data and summary.

`useCalibration(days)` fetches both endpoints in parallel via `Promise.all` (TanStack Query `useQueries`).

**Tests to write first (TDD)**:
- Test `CalibrationDashboard` renders the warning banner when `below_threshold=true`.
- Test `CalibrationDashboard` does NOT render the warning banner when `below_threshold=false`.
- Test `CalibrationDashboard` renders a chart line for each distinct `action_signal` in the data.
- Test `CalibrationDashboard` renders the per-signal accuracy table with one row per signal.
- Test selecting "60 days" from the lookback selector triggers a new fetch with `days=60`.
- Test `useCalibration` fetches both the time-series and summary endpoints in parallel.

**AC covered**: AC-004

---

### TASK-011: Frontend — WorkflowHistoryPanel and WorkflowDetailDrawer · M/TDD · src/frontend/admin/ai-audit/WorkflowHistoryPanel.tsx, src/frontend/admin/ai-audit/WorkflowDetailDrawer.tsx, src/frontend/admin/ai-audit/hooks/useWorkflowHistory.ts

`WorkflowHistoryPanel` renders a paginated table of `WorkflowRunSummary` rows. Columns: type, status (color-coded by status), started_at, duration (computed from `completed_at - started_at`), cost_usd (formatted to 4 decimal places), Re-run button. Clicking a row (other than Re-run) opens `WorkflowDetailDrawer`.

`WorkflowDetailDrawer` shows: all summary fields; a collapsed accordion for each `AgentInvocationSummary` (role, model, prompt_version, confidence, cost_usd, duration_ms, input_tokens, output_tokens); a nested collapsed section for `ToolCallSummary` rows belonging to each invocation; total cost breakdown footer.

Re-run button on a row opens a confirmation popover ("Re-run this workflow with current production prompts?"). On confirm: calls the re-run mutation. On success: shows toast "New run {new_workflow_id} dispatched" and refreshes the workflow list after 1 second (to pick up the new run).

`useWorkflowHistory` uses TanStack Query with cursor-based next-page navigation.

**Tests to write first (TDD)**:
- Test `WorkflowHistoryPanel` renders one table row per `WorkflowRunSummary`.
- Test clicking a row (not Re-run) opens `WorkflowDetailDrawer` with correct `workflow_id`.
- Test `WorkflowDetailDrawer` renders one accordion per `AgentInvocationSummary`.
- Test `WorkflowDetailDrawer` renders tool calls nested under their parent invocation.
- Test Re-run button confirmation popover shows before the mutation is called.
- Test Re-run mutation on success shows the new `workflow_id` in a toast notification.
- Test `useWorkflowHistory` next-page call sends the cursor returned from the previous page.

**AC covered**: AC-005

---

### TASK-012: RequireAdmin guard component and admin route wiring · S/no-TDD · src/frontend/admin/RequireAdmin.tsx, src/frontend/App.tsx (or router config)

Implement `RequireAdmin` as a React component that reads the current user's role from auth context. If `role !== "admin"`, it redirects to `/` and renders nothing. If `role === "admin"`, it renders `{children}`.

Wire the `/admin/ai-audit` route in the app router (React Router or equivalent) inside a `<RequireAdmin>` wrapper so that non-admin users cannot access any sub-path under `/admin/ai-audit`.

**AC covered**: enables AC-001 through AC-005 (all admin panels require admin role)

---

### TASK-013: Integration tests — full audit console flows · L/TDD · tests/integration/admin/test_decision_log_flow.py, tests/integration/admin/test_override_flow.py, tests/integration/admin/test_rollback_flow.py, tests/integration/admin/test_workflow_rerun_flow.py, tests/integration/admin/test_calibration_dashboard_flow.py

Write integration tests against real PostgreSQL test instances with mocked external dependencies (Langfuse SDK, Celery dispatch).

`test_decision_log_flow.py`: seed 20 `ai_decision` rows with varying confidence, agent_role, and model values; call `GET /api/v1/admin/audit/decisions?confidence_min=0.7&agent_role=recommendation_synthesizer`; assert only rows matching both filters are returned; extract a `decision_id`; call `GET /api/v1/admin/audit/decisions/{decision_id}`; assert `langfuse_trace_url` is present and `inputs_full` is not truncated.

`test_override_flow.py`: seed one `ai_decision` row; POST override with `corrected_output` and `override_reason`; assert a `user_feedback` row exists in DB with `feedback_type="admin_override"`; assert a `golden_dataset_item` row exists with `active=False` and `source="admin_override"`; assert response contains `proposed_prompt_adjustment` string.

`test_rollback_flow.py`: seed `prompt_publication` rows for one agent; mock `IPromptLabelService.rollback()` to return a `RollbackResult` with `effective_at=now()`; POST rollback request; assert `RollbackResponse.effective_at` is within 10 seconds of the request; assert the rollback was called with correct `role_id` and `to_version`.

`test_workflow_rerun_flow.py`: seed one `workflow_run` row with `final_state` containing `workflow_type` and `inputs`; mock `workflow_runner.dispatch` to return a new UUID; POST re-run; assert `RerunResponse.new_workflow_id` matches the mocked UUID; assert `dispatch` was called with the correct `workflow_type` and `inputs`.

`test_calibration_dashboard_flow.py`: seed 10 `calibration_result` rows across 30 days; GET calibration time-series with `days=30`; assert 10 rows returned; GET calibration summary; assert `below_threshold` field is present (bool); assert `per_signal_accuracy` contains at least one entry.

**Tests to write first (TDD)**:
- All five integration test files are the TDD artifacts; they drive end-to-end correctness of the full stack.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

## Acceptance Criteria Coverage

- AC-001: Admin can search AI decisions by date range, confidence range, and model; clicking any row expands to full detail including the Langfuse trace URL → TASK-001, TASK-002, TASK-003, TASK-006, TASK-007, TASK-013
- AC-002: Admin overrides an AI decision → user_feedback row written to Layer 4 with feedback_type=admin_override, decision added to golden_dataset candidate pool, proposed prompt adjustment surfaced for review → TASK-003, TASK-006, TASK-008, TASK-013
- AC-003: Prompt version history panel open → admin can view quality metrics per version and click Rollback; rollback takes effect within 60 seconds; subsequent agent invocations use rolled-back prompt version → TASK-004, TASK-006, TASK-009, TASK-013
- AC-004: Calibration dashboard displays CORR(confidence, actual_t1d × direction_sign) for at least 30 days of history; if CORR is not significantly positive, a warning indicator is visible → TASK-006, TASK-010, TASK-013
- AC-005: Mode B workflow in history list → clicking Re-run dispatches the same workflow with current production prompts; new run appears in workflow history list → TASK-005, TASK-006, TASK-011, TASK-013

## Acceptance Notes

- The calibration endpoints in TASK-006 are pass-throughs that delegate to `ICalibrationRepository` and `Tier3CalibrationService` (both owned by PLAN-F-016). If PLAN-F-016 is not yet executed, the calibration endpoints return empty lists, not errors. The frontend must handle empty-state gracefully (empty chart with "No calibration data yet" message).
- The `ai_decision` table (TASK-001) must be populated by the Mode A pipeline (classify_event step) and Mode B AgentNode invocations. Population logic is out of scope for this plan but required for AC-001 to yield meaningful data in production. The TASK-001 migration and TASK-002 repository are the provisioning contract; population is owned by PLAN-F-001 (Mode A) and PLAN-F-011 (Agent Registry) at their respective execution times.
- The Rollback SLA (60 seconds for agents to pick up the new prompt) is enforced by PLAN-F-014's `IPromptLabelService.rollback()` implementation and the Langfuse SDK. This plan's contribution is the UI callout and the `RollbackResponse.effective_at` timestamp; it does not introduce any additional mechanism to verify agent re-reads.

## Risks and Notes

- **ai_decision population gap**: Until PLAN-F-001 and PLAN-F-011 are updated to write `ai_decision` rows on every LLM call, the decision log will be empty in production. The table and APIs should be shipped first; population updates are tracked as modifications to the upstream plans. Integration tests in TASK-013 seed rows directly to avoid this dependency.
- **Calibration dashboard CORR display for negative values**: `CORR(confidence, actual_t1d × direction_sign)` can be negative. The Recharts Y-axis must span [-1, 1] and the threshold reference line must be labeled clearly. A CORR near 0 with large sample size is a significant warning; the dashboard should not interpret near-zero as "healthy".
- **Rollback idempotency**: If an admin clicks Rollback twice in quick succession, `IPromptLabelService.rollback()` is called twice. PLAN-F-014 must handle idempotency (re-labeling the same version as `production` when it is already `production` is a no-op). This plan's frontend should disable the Rollback button for 5 seconds after a successful rollback to prevent accidental double-clicks.
- **Cursor encoding**: The cursor for decision log and workflow history pagination is a base64-encoded tuple `(created_at_iso, uuid_str)`. Both the backend (TASK-002, TASK-005) and frontend (TASK-007, TASK-011 hooks) must use the same encoding convention. Define this encoding in `audit_api_schemas.py` as a helper function `encode_cursor(dt, uid) -> str` and `decode_cursor(cursor) -> tuple[datetime, UUID]` to avoid drift.
- **Re-run workflow dispatch**: The `workflow_runner.dispatch` function called in TASK-005 must accept `workflow_type: str` and `inputs: dict`. The actual Celery task routing table (mapping `workflow_type` strings to Celery task functions) must be established by the individual workflow plans (PLAN-F-006 through PLAN-F-010). If a `workflow_type` is not registered, `dispatch` should raise a `WorkflowTypeNotFoundError`; TASK-005 and TASK-006 must map this to a 400 response.
- **EpisodicRepository extensions**: TASK-005 adds `list_invocations_for_run` and `list_tool_calls_for_run` to `IEpisodicRepository`. These new abstract methods must also be implemented in `EpisodicRepository` from PLAN-F-015. Any test doubles or mocks of `IEpisodicRepository` in PLAN-F-015 tests must be updated to include these methods when PLAN-F-029 is executed.
