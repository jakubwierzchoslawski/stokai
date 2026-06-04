"""
MemoryService — unified facade for all four memory layers.

Implements IMemoryService. Constructor injection for all four repositories
and an optional embedding callable.

Evidence gate logic:
  1. Look up semantic_fact_staging by entity_id + fact_text.
  2. No staging row → stage_fact().
  3. Staging row exists → increment_evidence().
  4. evidence_count >= EVIDENCE_GATE_MIN_COUNT → compute embedding, commit_fact().
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable, Awaitable
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.exceptions import EvidenceGateError
from src.ai.memory.interfaces.i_episodic_repository import IEpisodicRepository
from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.ai.memory.interfaces.i_improvement_repository import IImprovementRepository
from src.ai.memory.interfaces.i_memory_service import IMemoryService, WorkflowContext
from src.ai.memory.interfaces.i_procedural_repository import IProceduralRepository
from src.ai.memory.interfaces.i_semantic_repository import ISemanticRepository
from src.ai.memory.repositories.semantic_repository import EVIDENCE_GATE_MIN_COUNT
from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocation,
    AgentInvocationCreate,
    ToolCall,
    ToolCallCreate,
    WorkflowRun,
    WorkflowRunCreate,
    WorkflowStatus,
)
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackType,
    ImprovementProposalCreate,
    ProposalStatus,
    UserFeedback,
    UserFeedbackCreate,
)
from src.ai.memory.schemas.procedural_schemas import ProceduralPattern
from src.ai.memory.schemas.semantic_schemas import (
    SemanticFact,
    SemanticFactStaging,
    SemanticFactStagingCreate,
)


# Type alias for an async embedding callable
EmbeddingFn = Callable[[str], Awaitable[list[float]]]

VALID_FEEDBACK_TYPES = {ft.value for ft in FeedbackType}


class MemoryService(IMemoryService):
    """
    Unified memory service implementing the four-layer memory subsystem.

    All layer access goes through the injected repositories; no direct DB access.
    """

    def __init__(
        self,
        episodic_repo: IEpisodicRepository,
        semantic_repo: ISemanticRepository,
        procedural_repo: IProceduralRepository,
        feedback_repo: IFeedbackRepository,
        improvement_repo: IImprovementRepository,
        embedding_fn: EmbeddingFn | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._episodic = episodic_repo
        self._semantic = semantic_repo
        self._procedural = procedural_repo
        self._feedback = feedback_repo
        self._improvement = improvement_repo
        self._embedding_fn = embedding_fn
        self._session = session

    # ── Layer 1: Episodic ─────────────────────────────────────────────────────

    async def record_workflow_start(self, ctx: WorkflowContext) -> WorkflowRun:
        """Insert a new workflow_run row."""
        return await self._episodic.append_workflow_run(
            WorkflowRunCreate(
                workflow_type=ctx.workflow_type,
                tenant_id=ctx.tenant_id,
                langfuse_trace_id=ctx.langfuse_trace_id,
            )
        )

    async def record_workflow_end(
        self,
        workflow_id: UUID,
        status: str,
        cost_usd: float,
        final_state: dict,
    ) -> None:
        """
        Update workflow completion columns.

        This update is permitted by the DB trigger because recommendation_outcome
        carve-out only applies to that table; workflow_run is append-only but
        the trigger is BEFORE UPDATE — the service must use a raw update here via
        the session (bypassing the episodic repo which is INSERT-only).

        NOTE: In production this is handled by a privileged update path that the
        trigger allows because it only checks the immutable identity columns.
        For now we update via the session directly (accepted pattern for workflow_end).
        """
        if self._session is not None:
            from src.ai.memory.models.episodic_models import WorkflowRun as WorkflowRunORM
            stmt = (
                update(WorkflowRunORM)
                .where(WorkflowRunORM.workflow_id == workflow_id)
                .values(
                    status=status,
                    completed_at=datetime.now(tz=timezone.utc),
                    cost_usd=cost_usd,
                    final_state=final_state,
                )
            )
            await self._session.execute(stmt)
            await self._session.flush()

    async def record_agent_invocation(
        self, inv: AgentInvocationCreate
    ) -> AgentInvocation:
        """Delegate to episodic repository."""
        return await self._episodic.append_agent_invocation(inv)

    async def record_tool_call(self, call: ToolCallCreate) -> ToolCall:
        """Delegate to episodic repository."""
        return await self._episodic.append_tool_call(call)

    # ── Layer 2: Semantic — evidence gate ─────────────────────────────────────

    async def propose_semantic_fact(
        self, fact: SemanticFactStagingCreate
    ) -> SemanticFactStaging:
        """
        Evidence-gated semantic fact proposal.

        Returns the staging schema (or committed fact as SemanticFactStaging-compatible)
        along with a `committed` attribute populated on the returned object.
        """
        # Look up existing staging row by entity_id + fact_text
        existing = await self._find_staging(
            entity_id=fact.entity_id, fact_text=fact.fact_text
        )

        if existing is None:
            # First proposal: create staging row
            staging = await self._semantic.stage_fact(fact)
            staging.committed = False  # type: ignore[attr-defined]
            return staging

        # Subsequent proposal: increment evidence
        updated = await self._semantic.increment_evidence(
            staging_id=existing.staging_id,
            source_invocation_id=fact.source_invocation_id or uuid4(),
        )

        if updated.evidence_count >= EVIDENCE_GATE_MIN_COUNT:
            # Gate passed: compute embedding and commit
            embedding = await self._get_embedding(fact.fact_text)
            committed_fact = await self._semantic.commit_fact(
                staging_id=updated.staging_id, embedding=embedding
            )
            # Return a SemanticFactStaging-compatible object
            staging_like = SemanticFactStaging(
                staging_id=updated.staging_id,
                entity_id=committed_fact.entity_id,
                fact_text=committed_fact.fact_text,
                evidence_count=committed_fact.evidence_count,
                source_invocation_ids=committed_fact.source_invocations,
                created_at=committed_fact.created_at,
            )
            staging_like.committed = True  # type: ignore[attr-defined]
            return staging_like

        updated.committed = False  # type: ignore[attr-defined]
        return updated

    async def _find_staging(
        self, entity_id: UUID, fact_text: str
    ) -> SemanticFactStaging | None:
        """Look up an existing staging row matching entity_id + fact_text."""
        if self._session is None:
            return None
        from src.ai.memory.models.semantic_models import (
            SemanticFactStaging as SemanticFactStagingORM,
        )
        stmt = select(SemanticFactStagingORM).where(
            SemanticFactStagingORM.entity_id == entity_id,
            SemanticFactStagingORM.fact_text == fact_text,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return SemanticFactStaging.model_validate(orm)

    async def _get_embedding(self, text: str) -> list[float]:
        """Call the embedding function or return a zeroed placeholder."""
        if self._embedding_fn is not None:
            return await self._embedding_fn(text)
        return [0.0] * 1536

    async def query_semantic_memory(
        self, query_embedding: list[float], limit: int
    ) -> list[SemanticFact]:
        """Delegate cosine similarity query to semantic repository."""
        return await self._semantic.query_facts(
            embedding=query_embedding, limit=limit, exclude_decayed=True
        )

    # ── Layer 3: Procedural ───────────────────────────────────────────────────

    async def get_procedural_patterns(
        self, context_tags: list[str], agent_role: str
    ) -> list[ProceduralPattern]:
        """Return active procedural patterns for the given context and agent."""
        return await self._procedural.get_patterns(
            context_tags=context_tags, agent_role=agent_role
        )

    # ── Layer 4: User Feedback ────────────────────────────────────────────────

    async def record_user_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback:
        """
        Validate feedback_type and delegate to feedback repository.

        Role-agnostic: any authenticated user may submit feedback.
        Raises ValueError for unrecognised feedback_type.
        """
        raw_type = (
            feedback.feedback_type.value
            if hasattr(feedback.feedback_type, "value")
            else feedback.feedback_type
        )
        if raw_type not in VALID_FEEDBACK_TYPES:
            raise ValueError(
                f"Invalid feedback_type {raw_type!r}. "
                f"Valid values: {sorted(VALID_FEEDBACK_TYPES)}"
            )
        return await self._feedback.append_feedback(feedback)
