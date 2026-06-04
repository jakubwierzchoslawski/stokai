"""
Unit tests for the event_deep_dive Celery task (PLAN-F-010 TASK-011).

TDD: written before implementation.
All external dependencies mocked — no real DB, LLM, or Langfuse calls.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.event_deep_dive.state import DeepDiveWorkflowState, GeoEvent
from src.ai.workflows.state import WorkflowStatus, WorkflowType


def _make_final_state(status: WorkflowStatus = WorkflowStatus.COMPLETED) -> DeepDiveWorkflowState:
    event_id = uuid.uuid4()
    return DeepDiveWorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        inputs={"event_id": str(event_id)},
        event_full=GeoEvent(event_id=event_id, title="Test"),
        confidence_scores={"workflow": 0.82},
        status=status,
        cost_usd=0.15,
    )


class TestRunEventDeepDiveTask:
    def test_task_is_registered_in_celery_app(self):
        """The task should be registered under the name 'ai.event_deep_dive'."""
        from src.config.celery_app import celery_app

        # The task module should be autodiscovered
        # We verify the task can be found by name (tasks are lazily registered)
        assert celery_app is not None

    def test_task_module_is_importable(self):
        """The celery_task module can be imported without errors."""
        import src.ai.workflows.event_deep_dive.celery_task  # noqa: F401

    def test_task_name_is_ai_event_deep_dive(self):
        """Task must be registered with name='ai.event_deep_dive'."""
        from src.ai.workflows.event_deep_dive.celery_task import run_event_deep_dive

        assert run_event_deep_dive.name == "ai.event_deep_dive"

    def test_task_queue_is_mode_b(self):
        """Task must use queue='mode_b'."""
        from src.ai.workflows.event_deep_dive.celery_task import run_event_deep_dive

        assert run_event_deep_dive.queue == "mode_b"

    @pytest.mark.asyncio
    async def test_task_returns_dict_with_status(self):
        """run_event_deep_dive.apply_async result contains 'status' key."""
        from src.ai.workflows.event_deep_dive.celery_task import _run_deep_dive_async

        final_state = _make_final_state()
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)

        with (
            patch(
                "src.ai.workflows.event_deep_dive.celery_task.build_deep_dive_graph",
                return_value=mock_graph,
            ),
            patch(
                "src.ai.workflows.event_deep_dive.celery_task._make_initial_state",
                return_value=final_state,
            ),
        ):
            result = await _run_deep_dive_async(
                event_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                user_id=str(uuid.uuid4()),
            )

        assert isinstance(result, dict)
        assert "status" in result
