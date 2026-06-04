"""
Unit tests for on_demand_analysis_task Celery task.

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


class TestOnDemandAnalysisTask:
    def test_task_has_correct_name(self):
        """Task must be registered as 'ai.on_demand_analysis'."""
        from src.ai.workflows.on_demand.tasks import on_demand_analysis_task

        assert on_demand_analysis_task.name == "ai.on_demand_analysis"

    def test_task_has_correct_time_limits(self):
        """Task must have time_limit=360 and soft_time_limit=300."""
        from src.ai.workflows.on_demand.tasks import on_demand_analysis_task

        # Celery task metadata
        assert on_demand_analysis_task.time_limit == 360
        assert on_demand_analysis_task.soft_time_limit == 300

    def test_task_has_max_retries_zero(self):
        """Task must have max_retries=0 (no automatic retries)."""
        from src.ai.workflows.on_demand.tasks import on_demand_analysis_task

        assert on_demand_analysis_task.max_retries == 0

    @pytest.mark.asyncio
    async def test_task_returns_dict_with_workflow_id(self):
        """Task must return a dict containing 'workflow_id' key."""
        from src.ai.workflows.on_demand.tasks import _run_on_demand_analysis

        workflow_id = uuid.uuid4()
        company_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        final_state = _make_state(
            workflow_id=workflow_id,
            company_id=company_id,
            tenant_id=tenant_id,
            user_id=user_id,
            status=WorkflowStatus.COMPLETED,
        )

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state.model_dump())

        mock_repo = AsyncMock()
        mock_repo.create = AsyncMock(return_value=MagicMock())
        mock_repo.save_final_state = AsyncMock()
        mock_repo.update_status = AsyncMock()

        with patch(
            "src.ai.workflows.on_demand.tasks.build_on_demand_graph",
            return_value=mock_graph,
        ), patch(
            "src.ai.workflows.on_demand.tasks.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.ai.workflows.on_demand.tasks._get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "src.ai.workflows.on_demand.tasks.LangfuseWorkflowTracer",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.ai.workflows.on_demand.tasks.WorkflowNotifier",
        ):
            result = await _run_on_demand_analysis(
                workflow_id=str(workflow_id),
                company_id=str(company_id),
                tenant_id=str(tenant_id),
                user_id=str(user_id),
            )

        assert "workflow_id" in result

    @pytest.mark.asyncio
    async def test_task_handles_soft_time_limit_exceeded(self):
        """SoftTimeLimitExceeded → status=TIMEOUT in persisted state."""
        from celery.exceptions import SoftTimeLimitExceeded
        from src.ai.workflows.on_demand.tasks import _run_on_demand_analysis

        workflow_id = uuid.uuid4()

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=SoftTimeLimitExceeded())

        mock_repo = AsyncMock()
        mock_repo.create = AsyncMock(return_value=MagicMock())
        mock_repo.save_final_state = AsyncMock()
        mock_repo.update_status = AsyncMock()

        with patch(
            "src.ai.workflows.on_demand.tasks.build_on_demand_graph",
            return_value=mock_graph,
        ), patch(
            "src.ai.workflows.on_demand.tasks.WorkflowRunRepository",
            return_value=mock_repo,
        ), patch(
            "src.ai.workflows.on_demand.tasks._get_db_session",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=AsyncMock()),
                __aexit__=AsyncMock(return_value=False),
            ),
        ), patch(
            "src.ai.workflows.on_demand.tasks.LangfuseWorkflowTracer",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=MagicMock()),
                __exit__=MagicMock(return_value=False),
            ),
        ), patch(
            "src.ai.workflows.on_demand.tasks.WorkflowNotifier",
        ):
            result = await _run_on_demand_analysis(
                workflow_id=str(workflow_id),
                company_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
            )

        assert result.get("status") == "TIMEOUT"
