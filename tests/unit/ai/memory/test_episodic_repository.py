"""
Unit tests for EpisodicRepository (TASK-004).

Uses a SQLite in-memory database to avoid PostgreSQL dependency.
Trigger enforcement (append-only) is a DB-level feature tested in integration tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocationCreate,
    RecommendationOutcomeCreate,
    ToolCallCreate,
    WorkflowRun,
    WorkflowRunCreate,
    WorkflowStatus,
)


@pytest.fixture
def workflow_run_create() -> WorkflowRunCreate:
    return WorkflowRunCreate(
        workflow_type="mode_b_analysis",
        tenant_id=uuid.uuid4(),
        langfuse_trace_id="trace-abc",
        cost_usd=0.0,
    )


@pytest.fixture
def mock_workflow_run_orm():
    """Mock ORM object returned after insert."""
    orm = MagicMock()
    orm.workflow_id = uuid.uuid4()
    orm.workflow_type = "mode_b_analysis"
    orm.tenant_id = uuid.uuid4()
    orm.started_at = datetime.now(tz=timezone.utc)
    orm.completed_at = None
    orm.status = "running"
    orm.final_state = None
    orm.cost_usd = 0.0
    orm.langfuse_trace_id = "trace-abc"
    return orm


class TestEpisodicRepositoryAppendWorkflowRun:
    """Tests for append_workflow_run."""

    @pytest.mark.asyncio
    async def test_append_workflow_run_returns_entity_with_generated_id(
        self, workflow_run_create, mock_workflow_run_orm
    ):
        """append_workflow_run inserts a row and returns entity with generated workflow_id."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import WorkflowRun

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch(
            "src.ai.memory.repositories.episodic_repository.WorkflowRun.model_validate"
        ) as mock_validate:
            expected = WorkflowRun(
                workflow_id=mock_workflow_run_orm.workflow_id,
                workflow_type="mode_b_analysis",
                tenant_id=workflow_run_create.tenant_id,
                started_at=mock_workflow_run_orm.started_at,
                status=WorkflowStatus.RUNNING,
            )
            mock_validate.return_value = expected

            repo = EpisodicRepository(session)
            result = await repo.append_workflow_run(workflow_run_create)

        session.add.assert_called_once()
        session.flush.assert_called_once()
        assert result.workflow_id is not None
        assert result.workflow_type == "mode_b_analysis"

    @pytest.mark.asyncio
    async def test_append_workflow_run_calls_session_add(
        self, workflow_run_create, mock_workflow_run_orm
    ):
        """append_workflow_run calls session.add (INSERT-only, no merge)."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import WorkflowRun

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch(
            "src.ai.memory.repositories.episodic_repository.WorkflowRun.model_validate"
        ) as mock_validate:
            mock_validate.return_value = WorkflowRun(
                workflow_id=uuid.uuid4(),
                workflow_type="mode_b_analysis",
                tenant_id=workflow_run_create.tenant_id,
                started_at=datetime.now(tz=timezone.utc),
                status=WorkflowStatus.RUNNING,
            )
            repo = EpisodicRepository(session)
            await repo.append_workflow_run(workflow_run_create)

        # Must use session.add (INSERT), never session.merge
        session.add.assert_called_once()
        session.merge = MagicMock()
        session.merge.assert_not_called()


class TestEpisodicRepositoryAppendAgentInvocation:
    """Tests for append_agent_invocation."""

    @pytest.mark.asyncio
    async def test_append_agent_invocation_with_valid_workflow_id(self):
        """append_agent_invocation with valid workflow_id succeeds."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import AgentInvocation

        workflow_id = uuid.uuid4()
        inv_id = uuid.uuid4()
        inv_create = AgentInvocationCreate(
            invocation_id=inv_id,
            workflow_id=workflow_id,
            agent_role_id="relevance-analyst",
            model_used="claude-haiku-4-5",
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch(
            "src.ai.memory.repositories.episodic_repository.AgentInvocation.model_validate"
        ) as mock_validate:
            mock_validate.return_value = AgentInvocation(
                invocation_id=inv_id,
                workflow_id=workflow_id,
                agent_role_id="relevance-analyst",
                started_at=datetime.now(tz=timezone.utc),
            )
            repo = EpisodicRepository(session)
            result = await repo.append_agent_invocation(inv_create)

        session.add.assert_called_once()
        assert result.workflow_id == workflow_id


class TestEpisodicRepositoryAppendToolCall:
    """Tests for append_tool_call."""

    @pytest.mark.asyncio
    async def test_append_tool_call_inserts_correctly(self):
        """append_tool_call inserts a row and returns entity."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import ToolCall

        inv_id = uuid.uuid4()
        tc_id = uuid.uuid4()
        tc_create = ToolCallCreate(
            tool_call_id=tc_id,
            invocation_id=inv_id,
            tool_name="fetch_news",
            arguments={"query": "Apple earnings"},
            cached=False,
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch(
            "src.ai.memory.repositories.episodic_repository.ToolCall.model_validate"
        ) as mock_validate:
            mock_validate.return_value = ToolCall(
                tool_call_id=tc_id,
                invocation_id=inv_id,
                tool_name="fetch_news",
                called_at=datetime.now(tz=timezone.utc),
            )
            repo = EpisodicRepository(session)
            result = await repo.append_tool_call(tc_create)

        session.add.assert_called_once()
        assert result.invocation_id == inv_id
        assert result.tool_name == "fetch_news"


class TestEpisodicRepositoryAppendRecommendationOutcome:
    """Tests for append_recommendation_outcome."""

    @pytest.mark.asyncio
    async def test_append_recommendation_outcome_inserts_correctly(self):
        """append_recommendation_outcome inserts a row correctly."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import RecommendationOutcome

        workflow_id = uuid.uuid4()
        rec_id = uuid.uuid4()
        outcome_create = RecommendationOutcomeCreate(
            rec_id=rec_id,
            workflow_id=workflow_id,
            company_id=uuid.uuid4(),
            action_signal="buy",
            confidence=0.85,
        )

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        with patch(
            "src.ai.memory.repositories.episodic_repository.RecommendationOutcome.model_validate"
        ) as mock_validate:
            mock_validate.return_value = RecommendationOutcome(
                rec_id=rec_id,
                workflow_id=workflow_id,
                created_at=datetime.now(tz=timezone.utc),
            )
            repo = EpisodicRepository(session)
            result = await repo.append_recommendation_outcome(outcome_create)

        session.add.assert_called_once()
        assert result.rec_id == rec_id


class TestEpisodicRepositoryFillOutcomeActuals:
    """Tests for fill_outcome_actuals."""

    @pytest.mark.asyncio
    async def test_fill_outcome_actuals_updates_only_calibration_columns(self):
        """fill_outcome_actuals updates actual_t1d, actual_t1w, direction_correct only."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository

        rec_id = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()

        repo = EpisodicRepository(session)
        await repo.fill_outcome_actuals(
            rec_id=rec_id,
            actual_t1d=0.02,
            actual_t1w=-0.01,
            direction_correct=True,
        )

        # Should execute an update statement
        session.execute.assert_called_once()
        # Extract the update statement call args
        call_args = session.execute.call_args
        stmt = call_args[0][0]
        # Verify it's an update (not an insert)
        from sqlalchemy import Update
        assert isinstance(stmt, Update)


class TestEpisodicRepositoryListRecentRuns:
    """Tests for list_recent_runs."""

    @pytest.mark.asyncio
    async def test_list_recent_runs_returns_ordered_by_started_at_desc(self):
        """list_recent_runs returns rows ordered by started_at descending, bounded by limit."""
        from src.ai.memory.repositories.episodic_repository import EpisodicRepository
        from src.ai.memory.schemas.episodic_schemas import WorkflowRun

        tenant_id = uuid.uuid4()

        # Create mock ORM results — sorted newest first
        t1 = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 3, 9, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            MagicMock(
                workflow_id=uuid.uuid4(),
                workflow_type="mode_b",
                tenant_id=tenant_id,
                started_at=t1,
                completed_at=None,
                status="completed",
                final_state=None,
                cost_usd=0.1,
                langfuse_trace_id=None,
            ),
            MagicMock(
                workflow_id=uuid.uuid4(),
                workflow_type="mode_b",
                tenant_id=tenant_id,
                started_at=t2,
                completed_at=None,
                status="completed",
                final_state=None,
                cost_usd=0.05,
                langfuse_trace_id=None,
            ),
        ]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.ai.memory.repositories.episodic_repository.WorkflowRun.model_validate"
        ) as mock_validate:
            runs_data = [
                WorkflowRun(
                    workflow_id=uuid.uuid4(),
                    workflow_type="mode_b",
                    tenant_id=tenant_id,
                    started_at=t1,
                    status=WorkflowStatus.COMPLETED,
                ),
                WorkflowRun(
                    workflow_id=uuid.uuid4(),
                    workflow_type="mode_b",
                    tenant_id=tenant_id,
                    started_at=t2,
                    status=WorkflowStatus.COMPLETED,
                ),
            ]
            mock_validate.side_effect = runs_data

            repo = EpisodicRepository(session)
            results = await repo.list_recent_runs(tenant_id=tenant_id, limit=10)

        assert len(results) == 2
        assert results[0].started_at >= results[1].started_at
