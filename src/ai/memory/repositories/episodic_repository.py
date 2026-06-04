"""
EpisodicRepository — SQLAlchemy 2.0 async implementation of IEpisodicRepository.

All write operations are INSERT-only. DB-level triggers in migration 0033
enforce the append-only constraint on workflow_run, agent_invocation, and
tool_call. recommendation_outcome allows calibration column updates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.interfaces.i_episodic_repository import IEpisodicRepository
from src.ai.memory.models.episodic_models import (
    AgentInvocation as AgentInvocationORM,
    RecommendationOutcome as RecommendationOutcomeORM,
    ToolCall as ToolCallORM,
    WorkflowRun as WorkflowRunORM,
)
from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocation,
    AgentInvocationCreate,
    RecommendationOutcome,
    RecommendationOutcomeCreate,
    ToolCall,
    ToolCallCreate,
    WorkflowRun,
    WorkflowRunCreate,
    WorkflowStatus,
)


class EpisodicRepository(IEpisodicRepository):
    """SQLAlchemy 2.0 async repository for Layer 1 episodic memory."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── WorkflowRun ───────────────────────────────────────────────────────────

    async def append_workflow_run(self, run: WorkflowRunCreate) -> WorkflowRun:
        """INSERT a new workflow_run row."""
        orm = WorkflowRunORM(
            workflow_id=uuid4(),
            workflow_type=run.workflow_type,
            tenant_id=run.tenant_id,
            started_at=datetime.now(tz=timezone.utc),
            status=WorkflowStatus.RUNNING,
            cost_usd=run.cost_usd,
            langfuse_trace_id=run.langfuse_trace_id,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return WorkflowRun.model_validate(orm)

    async def get_workflow_run(self, workflow_id: UUID) -> WorkflowRun | None:
        """Return a single WorkflowRun by ID or None."""
        stmt = select(WorkflowRunORM).where(
            WorkflowRunORM.workflow_id == workflow_id
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return WorkflowRun.model_validate(orm)

    async def list_recent_runs(
        self, tenant_id: UUID, limit: int = 50
    ) -> list[WorkflowRun]:
        """Return the most recent runs for a tenant, ordered by started_at DESC."""
        stmt = (
            select(WorkflowRunORM)
            .where(WorkflowRunORM.tenant_id == tenant_id)
            .order_by(WorkflowRunORM.started_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [WorkflowRun.model_validate(r) for r in rows]

    # ── AgentInvocation ───────────────────────────────────────────────────────

    async def append_agent_invocation(
        self, inv: AgentInvocationCreate
    ) -> AgentInvocation:
        """INSERT a new agent_invocation row."""
        orm = AgentInvocationORM(
            invocation_id=inv.invocation_id,
            workflow_id=inv.workflow_id,
            agent_role_id=inv.agent_role_id,
            started_at=datetime.now(tz=timezone.utc),
            duration_ms=inv.duration_ms,
            model_used=inv.model_used,
            prompt_version=inv.prompt_version,
            input_tokens=inv.input_tokens,
            output_tokens=inv.output_tokens,
            cost_usd=inv.cost_usd,
            confidence=inv.confidence,
            output=inv.output,
            tools_called=inv.tools_called,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return AgentInvocation.model_validate(orm)

    # ── ToolCall ──────────────────────────────────────────────────────────────

    async def append_tool_call(self, call: ToolCallCreate) -> ToolCall:
        """INSERT a new tool_call row."""
        orm = ToolCallORM(
            tool_call_id=call.tool_call_id,
            invocation_id=call.invocation_id,
            tool_name=call.tool_name,
            arguments=call.arguments,
            result=call.result,
            duration_ms=call.duration_ms,
            cost_tier=call.cost_tier,
            cached=call.cached,
            called_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return ToolCall.model_validate(orm)

    # ── RecommendationOutcome ─────────────────────────────────────────────────

    async def append_recommendation_outcome(
        self, outcome: RecommendationOutcomeCreate
    ) -> RecommendationOutcome:
        """INSERT a new recommendation_outcome row."""
        orm = RecommendationOutcomeORM(
            rec_id=outcome.rec_id,
            workflow_id=outcome.workflow_id,
            company_id=outcome.company_id,
            action_signal=outcome.action_signal,
            confidence=outcome.confidence,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return RecommendationOutcome.model_validate(orm)

    async def list_outcomes_by_date(
        self, reference_date: date
    ) -> list[RecommendationOutcome]:
        """Return recommendation_outcome rows for a date where filled_at IS NOT NULL."""
        stmt = select(RecommendationOutcomeORM).where(
            func.date(RecommendationOutcomeORM.created_at) == reference_date,
            RecommendationOutcomeORM.filled_at.isnot(None),
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [RecommendationOutcome.model_validate(r) for r in rows]

    async def fill_outcome_actuals(
        self,
        rec_id: UUID,
        actual_t1d: float,
        actual_t1w: float,
        direction_correct: bool,
    ) -> None:
        """
        Update only the calibration columns on recommendation_outcome.

        This is the permitted partial update: actual_t1d, actual_t1w,
        direction_correct, and filled_at. All other columns are untouched.
        """
        stmt = (
            update(RecommendationOutcomeORM)
            .where(RecommendationOutcomeORM.rec_id == rec_id)
            .values(
                actual_t1d=actual_t1d,
                actual_t1w=actual_t1w,
                direction_correct=direction_correct,
                filled_at=datetime.now(tz=timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()
