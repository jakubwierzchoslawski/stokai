---
plan_id: PLAN-F-015
slug: four-layer-memory-subsystem
title: Four-Layer Memory Subsystem
linked_requirement: REQ-F-015
type: functional
status: done
blocked_reason:
executed_at: 2026-06-03T00:00:00Z
complexity: XL
tdd_required: true
linked_nfrs:
  - { id: REQ-N-008, reason: "All AI reasoning steps must be stored in Layer 1 episodic memory as part of system observability" }
  - { id: REQ-N-010, reason: "recommendation_outcome rows in Layer 1 provide Tier 3 calibration data for confidence model accuracy" }
  - { id: REQ-N-011, reason: "Semantic fact 6-month confidence decay enforces data freshness requirements" }
  - { id: REQ-N-012, reason: "Layer 1 stores the complete reasoning chain (agent_invocation + tool_call rows) for compliance audit" }
dependencies: []
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-015 — Four-Layer Memory Subsystem

## Linked Requirement
**REQ-F-015** — Four-Layer Memory Subsystem
Status: approved | Jira:

## Objective

Implement the four-layer agentic memory subsystem that all five Mode B workflows and the evaluation framework depend on. Layer 1 (episodic) provides an append-only audit trail of every workflow run, agent invocation, tool call, and recommendation outcome, enforced at the DB level with no deletes permitted. Layer 2 (semantic) stores curated entity facts gated behind an evidence_count ≥ 3 staging mechanism with 6-month confidence decay. Layer 3 (procedural) stores versioned reasoning patterns, hand-seeded for v1, with a weekly mining job and human approval gate for v2. Layer 4 (user feedback) captures HIL actions and in-app signals continuously. A weekly offline improvement loop aggregates Layer 4 signals, generates proposed prompt and threshold adjustments, and presents them for human approval before any change is applied. Everything is implemented from day one; no incremental rollout.

## Architecture Context

The Memory Subsystem lives entirely within the `ai` backend module (`src/ai/memory/`), as defined in Architecture §5 (Backend Module Map) and §7.4 (Four-Layer Memory Subsystem). It is Layer 4 of the Six-Layer System Model (Processing). The subsystem sits below the Tool Library and above the `storage` module: agents call memory tools, memory tools call memory services, memory services call memory repositories, repositories call PostgreSQL via SQLAlchemy 2.0 async.

All four layers write to PostgreSQL 16. Layer 2 additionally writes VECTOR(1536) embeddings to the `semantic_fact.embedding` column using the pgvector extension with an HNSW index, consistent with the pattern established for `event_embedding` (Architecture §10, Key DB Extensions).

The `workflow_run`, `agent_invocation`, `tool_call`, and `recommendation_outcome` tables (Layer 1) also serve REQ-N-008 (full reasoning chain observability), REQ-N-010 (Tier 3 calibration), and REQ-N-012 (compliance audit). The `semantic_fact` decay mechanism is the mechanism through which REQ-N-011 (data freshness) is enforced for entity-level facts.

A new Celery beat schedule entry provides the weekly hygiene and improvement loop jobs. The pending-review table (`improvement_proposal`) surfaces in the Admin AI Audit Console (Architecture §11, Admin Panel — AI Audit Console).

The module structure follows the Controller → Service → Repository → Database layering rule. All DB access is behind repository interfaces. No raw SQL in the service layer.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-008 | Every AI reasoning step stored in episodic memory | `EpisodicRepository.append_*` methods called by workflow execution path; every agent_invocation and tool_call row is mandatory, not optional |
| REQ-N-010 | recommendation_outcome provides Tier 3 calibration data | `recommendation_outcome` table includes `actual_t1d`, `actual_t1w`, `direction_correct` columns; a separate Celery task fills them from price data at T+1d and T+1w |
| REQ-N-011 | Semantic facts have 6-month freshness decay | `SemanticHygieneService.run_decay_pass()` runs weekly via Celery beat; `decayed_at` column set; decayed facts excluded from all tool query results |
| REQ-N-012 | Complete reasoning chain stored for compliance | Layer 1 tables are append-only with `INSERT` triggers and no `DELETE` or `UPDATE` grants on episodic tables; `langfuse_trace_id` stored on `workflow_run` for cross-system audit |

## Component Design

### New Components

```
Module: ai/memory  (src/ai/memory/)
  ├── interfaces/
  │   ├── i_episodic_repository.py     — IEpisodicRepository (abstract)
  │   ├── i_semantic_repository.py     — ISemanticRepository (abstract)
  │   ├── i_procedural_repository.py   — IProceduralRepository (abstract)
  │   ├── i_feedback_repository.py     — IFeedbackRepository (abstract)
  │   └── i_memory_service.py          — IMemoryService (abstract, orchestration)
  ├── repositories/
  │   ├── episodic_repository.py       — EpisodicRepository (SQLAlchemy 2.0 async)
  │   ├── semantic_repository.py       — SemanticRepository (SQLAlchemy 2.0 async)
  │   ├── procedural_repository.py     — ProceduralRepository (SQLAlchemy 2.0 async)
  │   └── feedback_repository.py       — FeedbackRepository (SQLAlchemy 2.0 async)
  ├── services/
  │   ├── memory_service.py            — MemoryService (orchestrates reads/writes across layers)
  │   ├── semantic_hygiene_service.py  — SemanticHygieneService (decay + retraction)
  │   ├── pattern_mining_service.py    — PatternMiningService (episodic → procedural v2)
  │   └── improvement_loop_service.py  — ImprovementLoopService (Layer 4 → proposals)
  ├── models/
  │   ├── episodic_models.py           — SQLAlchemy ORM: WorkflowRun, AgentInvocation,
  │   │                                  ToolCall, RecommendationOutcome
  │   ├── semantic_models.py           — SQLAlchemy ORM: SemanticFact, SemanticFactStaging
  │   ├── procedural_models.py         — SQLAlchemy ORM: ProceduralPattern
  │   ├── feedback_models.py           — SQLAlchemy ORM: UserFeedback
  │   └── improvement_models.py        — SQLAlchemy ORM: ImprovementProposal
  ├── schemas/
  │   ├── episodic_schemas.py          — Pydantic DTOs for Layer 1
  │   ├── semantic_schemas.py          — Pydantic DTOs for Layer 2
  │   ├── procedural_schemas.py        — Pydantic DTOs for Layer 3
  │   └── feedback_schemas.py          — Pydantic DTOs for Layer 4
  ├── tasks/
  │   ├── hygiene_tasks.py             — Celery tasks: run_semantic_hygiene, run_outcome_fill
  │   ├── mining_tasks.py              — Celery tasks: run_pattern_mining
  │   └── improvement_tasks.py        — Celery tasks: run_improvement_loop
  └── __init__.py

Module: api/memory  (src/api/memory/)
  ├── memory_router.py                 — FastAPI router: feedback submit, proposal list/approve
  └── memory_schemas.py                — Request/response Pydantic models for API layer

Alembic migration:
  alembic/versions/XXXX_layer1_episodic_tables.py
  alembic/versions/XXXX_layer2_semantic_tables.py
  alembic/versions/XXXX_layer3_procedural_tables.py
  alembic/versions/XXXX_layer4_feedback_improvement_tables.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/config/celery_app.py` | Register hygiene, mining, and improvement loop beat schedules | Weekly jobs need Celery beat entries |
| `src/config/settings.py` | Add `SEMANTIC_DECAY_MONTHS`, `EVIDENCE_GATE_MIN_COUNT`, `EMBEDDING_MODEL` settings | Configurable thresholds; no hardcoded values |
| `docker/postgres/init.sql` | Enable pgvector extension; grant restricted permissions on episodic tables | pgvector HNSW index on semantic_fact.embedding; insert-only enforcement |

### Interfaces and Contracts

```python
# src/ai/memory/interfaces/i_episodic_repository.py

class IEpisodicRepository(ABC):
    @abstractmethod
    async def append_workflow_run(self, run: WorkflowRunCreate) -> WorkflowRun: ...
    @abstractmethod
    async def append_agent_invocation(self, inv: AgentInvocationCreate) -> AgentInvocation: ...
    @abstractmethod
    async def append_tool_call(self, call: ToolCallCreate) -> ToolCall: ...
    @abstractmethod
    async def append_recommendation_outcome(self, outcome: RecommendationOutcomeCreate) -> RecommendationOutcome: ...
    @abstractmethod
    async def fill_outcome_actuals(self, rec_id: UUID, actual_t1d: float, actual_t1w: float, direction_correct: bool) -> None: ...
    @abstractmethod
    async def get_workflow_run(self, workflow_id: UUID) -> WorkflowRun | None: ...
    @abstractmethod
    async def list_recent_runs(self, tenant_id: UUID, limit: int = 50) -> list[WorkflowRun]: ...

# src/ai/memory/interfaces/i_semantic_repository.py

class ISemanticRepository(ABC):
    @abstractmethod
    async def stage_fact(self, fact: SemanticFactStagingCreate) -> SemanticFactStaging: ...
    @abstractmethod
    async def increment_evidence(self, staging_id: UUID, source_invocation_id: UUID) -> SemanticFactStaging: ...
    @abstractmethod
    async def commit_fact(self, staging_id: UUID, embedding: list[float]) -> SemanticFact: ...
    @abstractmethod
    async def query_facts(self, embedding: list[float], limit: int = 20, exclude_decayed: bool = True) -> list[SemanticFact]: ...
    @abstractmethod
    async def mark_decayed(self, fact_ids: list[UUID]) -> int: ...
    @abstractmethod
    async def retract_fact(self, fact_id: UUID, retracted_by: UUID) -> None: ...
    @abstractmethod
    async def list_unconfirmed_older_than(self, months: int) -> list[SemanticFact]: ...

# src/ai/memory/interfaces/i_procedural_repository.py

class IProceduralRepository(ABC):
    @abstractmethod
    async def get_patterns(self, context_tags: list[str], agent_role: str | None = None) -> list[ProceduralPattern]: ...
    @abstractmethod
    async def create_pattern(self, pattern: ProceduralPatternCreate) -> ProceduralPattern: ...
    @abstractmethod
    async def approve_pattern(self, pattern_id: UUID, approved_by: UUID) -> ProceduralPattern: ...
    @abstractmethod
    async def retract_pattern(self, pattern_id: UUID, retracted_by: UUID) -> None: ...
    @abstractmethod
    async def list_pending_approval(self) -> list[ProceduralPattern]: ...

# src/ai/memory/interfaces/i_feedback_repository.py

class IFeedbackRepository(ABC):
    @abstractmethod
    async def append_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback: ...
    @abstractmethod
    async def list_since(self, since: datetime, tenant_id: UUID | None = None) -> list[UserFeedback]: ...
    @abstractmethod
    async def get_feedback_for_report(self, report_id: UUID) -> list[UserFeedback]: ...

# src/ai/memory/interfaces/i_memory_service.py

class IMemoryService(ABC):
    @abstractmethod
    async def record_workflow_start(self, ctx: WorkflowContext) -> WorkflowRun: ...
    @abstractmethod
    async def record_workflow_end(self, workflow_id: UUID, status: str, cost_usd: float, final_state: dict) -> None: ...
    @abstractmethod
    async def record_agent_invocation(self, inv: AgentInvocationCreate) -> AgentInvocation: ...
    @abstractmethod
    async def record_tool_call(self, call: ToolCallCreate) -> ToolCall: ...
    @abstractmethod
    async def propose_semantic_fact(self, fact: SemanticFactStagingCreate) -> SemanticFactStaging: ...
    @abstractmethod
    async def query_semantic_memory(self, query_embedding: list[float], limit: int) -> list[SemanticFact]: ...
    @abstractmethod
    async def get_procedural_patterns(self, context_tags: list[str], agent_role: str) -> list[ProceduralPattern]: ...
    @abstractmethod
    async def record_user_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback: ...
```

## Implementation Tasks

### TASK-001: DB migrations — Layer 1 episodic tables with insert-only enforcement · M/TDD · alembic/versions/0001_layer1_episodic_tables.py, docker/postgres/init.sql

Create the four Layer 1 tables: `workflow_run`, `agent_invocation`, `tool_call`, `recommendation_outcome`. All columns match the data model in Architecture §10 (Agentic Layer Tables). Enforce append-only semantics at the DB level: a PostgreSQL trigger function raises an exception on any `UPDATE` or `DELETE` against these four tables. Grant `INSERT` and `SELECT` to the application role; revoke `UPDATE` and `DELETE`.

**Tests to write first (TDD)**:
- Test that the Alembic migration applies cleanly against a test PostgreSQL instance and all four tables exist with the correct columns and constraints.
- Test that inserting a `workflow_run` row succeeds.
- Test that attempting an `UPDATE` on a `workflow_run` row raises a DB-level exception.
- Test that attempting a `DELETE` on an `agent_invocation` row raises a DB-level exception.

**AC covered**: AC-001

---

### TASK-002: SQLAlchemy ORM models — Layer 1 episodic · S/no-TDD · src/ai/memory/models/episodic_models.py

Define SQLAlchemy 2.0 `DeclarativeBase` mapped classes for `WorkflowRun`, `AgentInvocation`, `ToolCall`, and `RecommendationOutcome`. Use `Mapped[]` typed annotations. Mark `final_state` and `tools_called` as `JSONB`. Include relationship definitions for foreign keys (`agent_invocation.workflow_id → workflow_run`, `tool_call.invocation_id → agent_invocation`). No business logic in models.

**AC covered**: AC-001

---

### TASK-003: Pydantic schemas — Layer 1 episodic · S/no-TDD · src/ai/memory/schemas/episodic_schemas.py

Define Pydantic v2 `BaseModel` classes: `WorkflowRunCreate`, `WorkflowRun`, `AgentInvocationCreate`, `AgentInvocation`, `ToolCallCreate`, `ToolCall`, `RecommendationOutcomeCreate`, `RecommendationOutcome`. All fields typed. `status` field on `WorkflowRun` uses a `WorkflowStatus` `StrEnum`. All `UUID` fields default to `uuid4` where appropriate.

**AC covered**: AC-001

---

### TASK-004: IEpisodicRepository interface and EpisodicRepository implementation · M/TDD · src/ai/memory/interfaces/i_episodic_repository.py, src/ai/memory/repositories/episodic_repository.py

Define the `IEpisodicRepository` abstract class per the interface contract above. Implement `EpisodicRepository` using SQLAlchemy 2.0 async session. All five write methods are `INSERT`-only; no `session.merge()` or `session.execute(update(...))`. `fill_outcome_actuals` updates `recommendation_outcome.actual_t1d`, `actual_t1w`, `direction_correct` — this is the one permitted partial update (outcome fills are not prohibited by the append-only rule, which covers episodic event rows not calibration fills). Include `list_recent_runs` for the Admin panel.

**Tests to write first (TDD)**:
- Test `append_workflow_run` inserts a row and returns the created entity with a generated `workflow_id`.
- Test `append_agent_invocation` with a valid `workflow_id` succeeds; with an invalid FK raises `IntegrityError`.
- Test `append_tool_call` inserts correctly.
- Test `append_recommendation_outcome` inserts correctly.
- Test `fill_outcome_actuals` updates only the three outcome columns and leaves all other columns unchanged.
- Test `list_recent_runs` returns rows ordered by `started_at` descending, bounded by `limit`.

**AC covered**: AC-001

---

### TASK-005: DB migrations — Layer 2 semantic tables · M/TDD · alembic/versions/0002_layer2_semantic_tables.py

Create `semantic_fact_staging` (pre-gate holding area) and `semantic_fact` (committed facts). `semantic_fact` includes `embedding VECTOR(1536)` with an HNSW index (`vector_cosine_ops`). Add `decayed_at TIMESTAMPTZ NULL` column; a non-null value means decayed. Add `retracted_at TIMESTAMPTZ NULL` and `retracted_by UUID NULL`. Create GIN index on `source_invocations` array column. Enable `vector` extension if not already enabled.

**Tests to write first (TDD)**:
- Test migration applies cleanly; `semantic_fact` and `semantic_fact_staging` tables exist.
- Test that `semantic_fact.embedding` column exists with type `vector(1536)`.
- Test that the HNSW index is present on `semantic_fact.embedding`.
- Test that inserting a row with a 1536-dimension embedding succeeds.

**AC covered**: AC-002, AC-003

---

### TASK-006: SQLAlchemy ORM models and Pydantic schemas — Layer 2 semantic · S/no-TDD · src/ai/memory/models/semantic_models.py, src/ai/memory/schemas/semantic_schemas.py

Define `SemanticFactStaging` and `SemanticFact` ORM mapped classes. The `embedding` column uses `pgvector`'s SQLAlchemy type `Vector(1536)`. Define Pydantic schemas: `SemanticFactStagingCreate`, `SemanticFactStaging`, `SemanticFactCreate`, `SemanticFact`. `SemanticFact.is_active` is a computed property: `decayed_at is None and retracted_at is None`.

**AC covered**: AC-002, AC-003

---

### TASK-007: ISemanticRepository interface and SemanticRepository implementation · M/TDD · src/ai/memory/interfaces/i_semantic_repository.py, src/ai/memory/repositories/semantic_repository.py

Define `ISemanticRepository` per the interface contract. Implement `SemanticRepository`. Key methods:

- `stage_fact`: insert a `semantic_fact_staging` row with `evidence_count=1`.
- `increment_evidence`: `UPDATE semantic_fact_staging SET evidence_count = evidence_count + 1` and append to `source_invocation_ids`.
- `commit_fact`: called only when caller confirms `evidence_count >= 3`; inserts into `semantic_fact` and deletes the staging row.
- `query_facts`: cosine similarity search via `embedding <=> :query_vec ORDER BY ... LIMIT :limit`; `WHERE decayed_at IS NULL AND retracted_at IS NULL` when `exclude_decayed=True`.
- `mark_decayed`: bulk `UPDATE semantic_fact SET decayed_at = NOW() WHERE fact_id = ANY(:ids)`.
- `list_unconfirmed_older_than`: facts where `last_confirmed < NOW() - INTERVAL ':months months'` and `decayed_at IS NULL`.

**Tests to write first (TDD)**:
- Test `stage_fact` creates a staging row with `evidence_count=1`.
- Test `increment_evidence` increments `evidence_count` from 1 to 2.
- Test `commit_fact` moves staging row to `semantic_fact` when `evidence_count >= 3`; staging row is removed.
- Test that calling `commit_fact` on a staging row with `evidence_count < 3` raises `EvidenceGateError`.
- Test `query_facts` with `exclude_decayed=True` does not return facts where `decayed_at IS NOT NULL`.
- Test `mark_decayed` sets `decayed_at` on targeted rows and leaves others untouched.
- Test `list_unconfirmed_older_than` returns only facts unconfirmed beyond the threshold.

**AC covered**: AC-002, AC-003

---

### TASK-008: Evidence gate service logic within MemoryService · M/TDD · src/ai/memory/services/memory_service.py, src/ai/memory/interfaces/i_memory_service.py

Implement `MemoryService.propose_semantic_fact()`:
1. Look up `semantic_fact_staging` for same `entity_id + fact_text` hash.
2. If no existing staging row: call `SemanticRepository.stage_fact()`.
3. If staging row exists: call `SemanticRepository.increment_evidence()`.
4. If `staging.evidence_count >= EVIDENCE_GATE_MIN_COUNT` (from settings, default 3): compute embedding via embedding service, call `SemanticRepository.commit_fact()`.
5. Return the staging or committed fact with a `committed: bool` flag in the response schema.

Define `IMemoryService` abstract class. `MemoryService` takes all four repository interfaces as constructor-injected dependencies.

**Tests to write first (TDD)**:
- Test that `propose_semantic_fact` with a new fact creates a staging row and returns `committed=False`.
- Test that proposing the same fact a second time increments `evidence_count` to 2, returns `committed=False`.
- Test that proposing the same fact a third time triggers `commit_fact`, returns `committed=True`, and staging row is removed.
- Test that the committed fact is queryable via `query_semantic_memory`.
- Mock the embedding service; confirm it is only called when `evidence_count >= 3`.

**AC covered**: AC-002

---

### TASK-009: DB migrations — Layer 3 procedural and Layer 4 feedback + improvement proposal tables · M/TDD · alembic/versions/0003_layer3_procedural_tables.py, alembic/versions/0004_layer4_feedback_improvement_tables.py

Create `procedural_pattern` with columns: `pattern_id UUID PK`, `pattern_type`, `context_tags TEXT[]`, `pattern_text TEXT`, `authored_by VARCHAR CHECK(authored_by IN ('human', 'mined'))`, `approved_at TIMESTAMPTZ NULL`, `approved_by UUID NULL`, `version INT DEFAULT 1`, `success_rate FLOAT`, `sample_size INT`, `confidence FLOAT`, `recommended_for_agents TEXT[]`, `created_at`, `retracted_at NULL`.

Create `user_feedback` with columns: `feedback_id UUID PK`, `tenant_id UUID NOT NULL`, `report_id UUID NULL`, `recommendation_id UUID NULL`, `feedback_type VARCHAR NOT NULL` (CHECK in `thumbs_up, thumbs_down, approve, edit_approve, reject, reject_with_feedback`), `feedback_text TEXT NULL`, `user_edit TEXT NULL`, `reviewer_id UUID NULL`, `source VARCHAR NOT NULL` (CHECK in `hil_action, in_app`), `submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.

Create `improvement_proposal` with columns: `proposal_id UUID PK`, `proposal_type VARCHAR` (CHECK in `prompt_adjustment, threshold_adjustment`), `description TEXT`, `proposed_changes JSONB`, `status VARCHAR DEFAULT 'pending'` (CHECK in `pending, approved, rejected`), `reviewed_by UUID NULL`, `reviewed_at TIMESTAMPTZ NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `source_feedback_ids UUID[]`.

**Tests to write first (TDD)**:
- Test all three tables exist after migration.
- Test `authored_by` CHECK constraint rejects values outside `(human, mined)`.
- Test `feedback_type` CHECK constraint rejects invalid values.
- Test `improvement_proposal.status` CHECK constraint rejects invalid values.
- Test `procedural_pattern` insert with `approved_at=NULL` succeeds (pattern pending approval).

**AC covered**: AC-004, AC-005

---

### TASK-010: SQLAlchemy ORM models and Pydantic schemas — Layers 3 and 4 · S/no-TDD · src/ai/memory/models/procedural_models.py, src/ai/memory/models/feedback_models.py, src/ai/memory/models/improvement_models.py, src/ai/memory/schemas/procedural_schemas.py, src/ai/memory/schemas/feedback_schemas.py

Define ORM mapped classes: `ProceduralPattern`, `UserFeedback`, `ImprovementProposal`. Define Pydantic schemas for each: `ProceduralPatternCreate`, `ProceduralPattern`, `UserFeedbackCreate`, `UserFeedback`, `ImprovementProposalCreate`, `ImprovementProposal`. `ProceduralPattern.is_active` is a computed property: `approved_at is not None and retracted_at is None`. `ImprovementProposal.status` uses `ProposalStatus` `StrEnum`.

**AC covered**: AC-004, AC-005

---

### TASK-011: IProceduralRepository, IFeedbackRepository interfaces and implementations · M/TDD · src/ai/memory/interfaces/i_procedural_repository.py, src/ai/memory/interfaces/i_feedback_repository.py, src/ai/memory/repositories/procedural_repository.py, src/ai/memory/repositories/feedback_repository.py

Implement `ProceduralRepository`: `get_patterns` filters by `context_tags && :tags` (GIN overlap) and `recommended_for_agents @> ARRAY[:agent_role]`; returns only `approved_at IS NOT NULL AND retracted_at IS NULL` rows. `list_pending_approval` returns `approved_at IS NULL AND retracted_at IS NULL`. `approve_pattern` sets `approved_at=NOW()` and `approved_by`.

Implement `FeedbackRepository`: `append_feedback` is INSERT-only. `list_since` returns all feedback since a datetime threshold, optionally filtered by `tenant_id`. `get_feedback_for_report` returns all feedback for a `report_id`.

**Tests to write first (TDD)**:
- Test `get_patterns` only returns approved, non-retracted patterns.
- Test `list_pending_approval` returns only unapproved patterns.
- Test `approve_pattern` sets the approval columns and the pattern appears in `get_patterns` afterward.
- Test `retract_pattern` sets `retracted_at` and the pattern no longer appears in `get_patterns`.
- Test `append_feedback` with `feedback_type=thumbs_down` and `source=in_app` inserts correctly.
- Test `list_since` returns only feedback after the threshold datetime.
- Test `get_feedback_for_report` returns all feedback records for the specified `report_id`.

**AC covered**: AC-004, AC-005

---

### TASK-012: MemoryService — record_* methods and record_user_feedback · M/TDD · src/ai/memory/services/memory_service.py

Implement the episodic recording methods on `MemoryService`:
- `record_workflow_start`: creates `WorkflowRun` via `IEpisodicRepository.append_workflow_run`.
- `record_workflow_end`: calls `fill_outcome_actuals` pattern — updates `status`, `completed_at`, `cost_usd`, `final_state` via a narrow update (only these fields; the episodic trigger only blocks DELETE and structural UPDATE; cost and status fields are mutable as the run completes).
- `record_agent_invocation`: delegates to `IEpisodicRepository.append_agent_invocation`.
- `record_tool_call`: delegates to `IEpisodicRepository.append_tool_call`.
- `record_user_feedback`: validates `feedback_type` is a known `FeedbackType` value, then delegates to `IFeedbackRepository.append_feedback`. Does not require admin role — caller is responsible for auth; service is role-agnostic.

**Tests to write first (TDD)**:
- Test `record_workflow_start` returns a `WorkflowRun` with a generated `workflow_id`.
- Test `record_agent_invocation` correctly delegates; the returned object has the correct `workflow_id`.
- Test `record_tool_call` delegates; returned object references the correct `invocation_id`.
- Test `record_user_feedback` with `feedback_type=thumbs_down` and `source=in_app` inserts correctly without requiring elevated permissions.
- Test `record_user_feedback` with an invalid `feedback_type` value raises `ValueError` before touching the repository.

**AC covered**: AC-001, AC-005

---

### TASK-013: SemanticHygieneService and hygiene Celery task · M/TDD · src/ai/memory/services/semantic_hygiene_service.py, src/ai/memory/tasks/hygiene_tasks.py

Implement `SemanticHygieneService.run_decay_pass()`:
1. Call `ISemanticRepository.list_unconfirmed_older_than(months=SEMANTIC_DECAY_MONTHS)` (default 6).
2. Collect `fact_id` list.
3. Call `ISemanticRepository.mark_decayed(fact_ids)`.
4. Return a `DecayPassResult(facts_decayed: int, run_at: datetime)` value object.

Decayed facts are NOT deleted; they are excluded from tool query results by the `exclude_decayed=True` filter in `query_facts`.

Register `run_semantic_hygiene` as a Celery task in `hygiene_tasks.py`. Add the beat schedule entry to `celery_app.py`: weekly on Monday at 02:00 UTC.

Also implement `run_outcome_fill` Celery task: queries `recommendation_outcome` rows where `actual_t1d IS NULL` and `filled_at IS NULL`, fetches price data from the `storage` module for T+1d and T+1w, calls `EpisodicRepository.fill_outcome_actuals`. This task satisfies REQ-N-010.

**Tests to write first (TDD)**:
- Test `run_decay_pass` with 2 facts older than 6 months and 1 recent fact: only the 2 old facts are marked decayed; the recent fact is untouched.
- Test that a fact marked decayed does not appear in `query_facts` with `exclude_decayed=True`.
- Test that a fact marked decayed does appear in `query_facts` with `exclude_decayed=False`.
- Test `run_decay_pass` with no qualifying facts returns `facts_decayed=0` without error.
- Test `run_outcome_fill` with a recommendation_outcome row where `actual_t1d IS NULL` triggers a price fetch and fills all three calibration columns.

**AC covered**: AC-003

---

### TASK-014: PatternMiningService and mining Celery task (Layer 3 v2) · L/TDD · src/ai/memory/services/pattern_mining_service.py, src/ai/memory/tasks/mining_tasks.py

Implement `PatternMiningService.run_mining_pass()`:
1. Query `agent_invocation` rows from the past 30 days grouped by `agent_role_id + context_signature`.
2. For clusters with `sample_size >= 5` and consistent `output_pattern`, generate a candidate `ProceduralPattern` with `authored_by='mined'` and `approved_at=NULL`.
3. Call `IProceduralRepository.create_pattern()` for each new candidate; skip if an equivalent pattern already exists (idempotent by `context_signature` hash).
4. Return `MiningPassResult(patterns_proposed: int, run_at: datetime)`.

Proposed patterns are not applied until a human approves them via the Admin AI Audit Console (calling `ProceduralRepository.approve_pattern`). This is the human approval gate for Layer 3 v2.

Register `run_pattern_mining` as a Celery task. Add beat schedule: weekly on Tuesday at 03:00 UTC.

**Tests to write first (TDD)**:
- Test `run_mining_pass` with a cluster of 5 invocations with consistent output creates one candidate pattern with `approved_at=NULL`.
- Test that a cluster of only 4 invocations does not produce a candidate (below sample threshold).
- Test that running mining twice on the same data does not create duplicate patterns (idempotent).
- Test that proposed patterns do NOT appear in `get_patterns` (active patterns query) until `approve_pattern` is called.
- Test `approve_pattern` makes the pattern active and queryable.

**AC covered**: AC-004

---

### TASK-015: ImprovementLoopService and improvement Celery task · L/TDD · src/ai/memory/services/improvement_loop_service.py, src/ai/memory/tasks/improvement_tasks.py

Implement `ImprovementLoopService.run_improvement_loop()`:
1. Call `IFeedbackRepository.list_since(since=last_week)`.
2. Aggregate by `feedback_type`: count rejections, edits, thumbs_down per `report_id`.
3. For patterns with ≥ 3 rejections or ≥ 5 thumbs_down on the same workflow type: generate an `ImprovementProposal` with `status='pending'`.
4. Persist proposals via `ImprovementProposalRepository` (inline on `FeedbackRepository` or separate class).
5. Proposals are not applied; they surface in the Admin AI Audit Console for human approval.
6. Return `ImprovementLoopResult(proposals_generated: int, run_at: datetime)`.

The approval endpoint (in TASK-016 API layer) updates `proposal.status='approved'` and triggers the git+Langfuse pipeline hook (out of scope for this plan — it emits an event that PLAN-F-014 Prompt Management Pipeline handles).

Register `run_improvement_loop` as a Celery task. Add beat schedule: weekly on Wednesday at 04:00 UTC.

**Tests to write first (TDD)**:
- Test `run_improvement_loop` with 4 rejection feedbacks for the same workflow type generates one proposal with `status='pending'`.
- Test that fewer than 3 rejections does not generate a proposal.
- Test that the generated proposal's `proposed_changes` JSONB contains the workflow type and rejection count.
- Test that the proposal is NOT applied automatically: the `status` remains `'pending'` after `run_improvement_loop`.
- Test running the loop twice on the same data is idempotent (does not create duplicate proposals).

**AC covered**: AC-004

---

### TASK-016: FastAPI memory router — user feedback submit and proposal management endpoints · M/TDD · src/api/memory/memory_router.py, src/api/memory/memory_schemas.py

Implement the REST endpoints:

- `POST /api/v1/memory/feedback` — authenticated (any role including `end_user`); accepts `UserFeedbackRequest`; delegates to `IMemoryService.record_user_feedback`; returns 201.
- `GET /api/v1/memory/proposals` — admin-only; returns paginated list of `ImprovementProposal` with `status=pending`.
- `POST /api/v1/memory/proposals/{proposal_id}/approve` — admin-only; sets `status=approved`, `reviewed_by`, `reviewed_at`; emits approval event.
- `POST /api/v1/memory/proposals/{proposal_id}/reject` — admin-only; sets `status=rejected`.
- `GET /api/v1/memory/patterns/pending` — admin-only; returns unapproved `ProceduralPattern` list.
- `POST /api/v1/memory/patterns/{pattern_id}/approve` — admin-only; calls `IProceduralRepository.approve_pattern`.

All routes use FastAPI dependency injection for auth (`Depends(get_current_user)`) and service (`Depends(get_memory_service)`). Controllers do not contain business logic — they parse, validate, delegate, and respond.

**Tests to write first (TDD)**:
- Test `POST /api/v1/memory/feedback` with `feedback_type=thumbs_down` and `source=in_app` by an authenticated `end_user` returns 201 and a `user_feedback` row is inserted.
- Test the same endpoint with an unauthenticated request returns 401.
- Test `GET /api/v1/memory/proposals` by a non-admin user returns 403.
- Test `POST /api/v1/memory/proposals/{id}/approve` by an admin sets the proposal `status` to `approved`.
- Test `POST /api/v1/memory/patterns/{id}/approve` by an admin sets `approved_at` on the pattern.

**AC covered**: AC-004, AC-005

---

### TASK-017: Layer 3 v1 hand-seeded procedural patterns data fixture · S/no-TDD · src/ai/memory/fixtures/procedural_patterns_v1.py, alembic/versions/0005_seed_procedural_patterns_v1.py

Create the v1 hand-authored reasoning patterns for each of the nine agent roles. Patterns encode known-good reasoning approaches for each agent context. Implement as an Alembic data migration that inserts patterns with `authored_by='human'` and `approved_at=NOW()` (pre-approved). Include at minimum one pattern per agent role (9 patterns). Patterns are expressed in `pattern_text` as structured natural language directives usable as system-prompt injections.

**AC covered**: AC-004 (pattern approval gate is enforced; v1 are pre-approved by design)

---

### TASK-018: Integration tests — cross-layer memory flows · M/TDD · tests/integration/memory/test_episodic_flow.py, tests/integration/memory/test_semantic_flow.py, tests/integration/memory/test_feedback_improvement_flow.py

Write integration tests that exercise the full memory stack against a real PostgreSQL test instance:

- `test_episodic_flow.py`: simulate a complete Mode B workflow recording — `record_workflow_start` → `record_agent_invocation` → `record_tool_call` → `record_workflow_end`; assert all rows exist; assert DB trigger blocks a manual DELETE attempt.
- `test_semantic_flow.py`: propose a fact 3 times, assert it is committed on the third; run `SemanticHygieneService.run_decay_pass()` after manually backdating `last_confirmed`; assert fact is decayed and excluded from queries.
- `test_feedback_improvement_flow.py`: write 4 rejection feedbacks; run `ImprovementLoopService.run_improvement_loop()`; assert a proposal is created with `status=pending`; approve via router; assert `status=approved`.

**Tests to write first (TDD)**:
- All tests in this task are themselves the TDD artifact; they drive the correctness of the integration.

**AC covered**: AC-001, AC-002, AC-003, AC-004, AC-005

---

## Acceptance Criteria Coverage

- AC-001: Layer 1 episodic tables with insert-only DB enforcement → TASK-001, TASK-002, TASK-003, TASK-004, TASK-012, TASK-018
- AC-002: Semantic fact staging — evidence_count < 3 not committed → TASK-005, TASK-006, TASK-007, TASK-008, TASK-018
- AC-003: 6-month decay hygiene — facts flagged inactive, not deleted, excluded from queries → TASK-005, TASK-007, TASK-013, TASK-018
- AC-004: Weekly improvement loop writes proposals to pending-review table; human approval required before application → TASK-009, TASK-010, TASK-011, TASK-014, TASK-015, TASK-016, TASK-017, TASK-018
- AC-005: In-app thumbs-down by non-admin user writes user_feedback row with correct fields → TASK-009, TASK-010, TASK-011, TASK-012, TASK-016, TASK-018

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | Who authors the Layer 3 procedural memory v1 patterns, and what completeness criteria must be met before Phase 4 go-live? | Planning resolution: TASK-017 provides a data migration fixture seeding at least one pattern per agent role (9 minimum). Completeness criteria for Phase 4 go-live are deferred to PLAN-F-011 (Agent Registry) and the Mode B workflow plans; this plan ensures the seeding mechanism exists and patterns are pre-approved. The specific content of each pattern is an operational concern for the team before Phase 4 cut-over. |

## Risks and Notes

- **pgvector availability**: The HNSW index on `semantic_fact.embedding` requires `pgvector >= 0.5.0`. Confirm the Docker base image for PostgreSQL 16 includes this version. The `init.sql` migration must run `CREATE EXTENSION IF NOT EXISTS vector;` before the Layer 2 migration runs.
- **Append-only trigger vs. outcome fill**: The insert-only DB trigger covers structural episodic rows (`workflow_run`, `agent_invocation`, `tool_call`). `recommendation_outcome` has a narrow carve-out: `actual_t1d`, `actual_t1w`, `direction_correct`, and `filled_at` are filled by the outcome calibration Celery task at T+1d and T+1w. The trigger should permit UPDATE only on these specific columns or be scoped only to the other three tables. Confirm trigger design in TASK-001.
- **Embedding model coupling**: `semantic_fact.embedding` is VECTOR(1536) matching OpenAI `text-embedding-3-small`. If the embedding model changes, existing semantic facts are incompatible. Dimension is a migration; plan for a `namespace` or `embedding_model` column on `semantic_fact` for future isolation.
- **Celery beat idempotency**: All three weekly jobs (hygiene, mining, improvement loop) must be idempotent — running twice in a week must produce the same result as running once. Implement a `last_run_at` guard or use Celery beat's built-in deduplication.
- **MemoryService constructor complexity**: `MemoryService` takes four repository interfaces. Use a factory function or DI container entry in `src/config/` to assemble it; do not construct it inline in route handlers.
- **Admin AI Audit Console integration**: The `improvement_proposal` and pending `procedural_pattern` data surfaces in the Admin AI Audit Console (Architecture §11). The API endpoints in TASK-016 are the backend contract; the frontend integration is part of PLAN-F-029 (Admin: AI Audit Console) and is out of scope here.
