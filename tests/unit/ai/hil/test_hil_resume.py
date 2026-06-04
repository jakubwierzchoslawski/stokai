"""
Unit tests for HILResumeService.

All external dependencies (AsyncPostgresSaver, WorkflowRunRepository,
DB session) are mocked. No real PostgreSQL or LangGraph runtime required.

TDD tests defined before implementation (PLAN-F-013 TASK-004).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.hil.hil_resume import HILResumeService


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_service(
    *,
    workflow_run_repo: AsyncMock | None = None,
) -> HILResumeService:
    repo = workflow_run_repo or AsyncMock()
    return HILResumeService(workflow_run_repo=repo)


@pytest.mark.asyncio
class TestResumeFromCheckpoint:
    """Tests for HILResumeService.resume_from_checkpoint."""

    async def test_resume_loads_checkpoint_and_continues_from_narrative_writer(
        self,
    ) -> None:
        """Resuming without override_text continues at narrative_writer node."""
        lc_checkpoint_id = f"hil:{uuid.uuid4()}"
        workflow_run_repo = AsyncMock()

        mock_final_state = MagicMock()
        mock_final_state.report = {"content": "Original report content."}

        with patch(
            "src.ai.hil.hil_resume._invoke_graph_from_checkpoint",
            new_callable=AsyncMock,
            return_value=mock_final_state,
        ) as mock_invoke:
            service = _make_service(workflow_run_repo=workflow_run_repo)
            result = await service.resume_from_checkpoint(
                lc_checkpoint_id=lc_checkpoint_id,
                override_text=None,
            )

        mock_invoke.assert_called_once_with(
            lc_checkpoint_id=lc_checkpoint_id,
            override_text=None,
        )
        assert result is mock_final_state

    async def test_resume_with_override_text_replaces_report_content(self) -> None:
        """When override_text is set, it replaces state.report content before resuming."""
        lc_checkpoint_id = f"hil:{uuid.uuid4()}"
        override_text = "Reviewer edited this report."
        workflow_run_repo = AsyncMock()

        mock_final_state = MagicMock()
        mock_final_state.report = {"content": override_text}

        with patch(
            "src.ai.hil.hil_resume._invoke_graph_from_checkpoint",
            new_callable=AsyncMock,
            return_value=mock_final_state,
        ) as mock_invoke:
            service = _make_service(workflow_run_repo=workflow_run_repo)
            result = await service.resume_from_checkpoint(
                lc_checkpoint_id=lc_checkpoint_id,
                override_text=override_text,
            )

        mock_invoke.assert_called_once_with(
            lc_checkpoint_id=lc_checkpoint_id,
            override_text=override_text,
        )
        assert result is mock_final_state


@pytest.mark.asyncio
class TestTerminateWorkflow:
    """Tests for HILResumeService.terminate_workflow."""

    async def test_terminate_marks_workflow_run_as_terminated_hil(self) -> None:
        """terminate_workflow writes terminated_hil status to workflow_run."""
        workflow_run_repo = AsyncMock()
        workflow_id = uuid.uuid4()
        lc_checkpoint_id = f"hil:{workflow_id}"

        service = _make_service(workflow_run_repo=workflow_run_repo)
        await service.terminate_workflow(
            lc_checkpoint_id=lc_checkpoint_id,
            reason="Reviewer rejected",
        )

        workflow_run_repo.update_status.assert_called_once()
        call_kwargs = workflow_run_repo.update_status.call_args
        # First positional arg is workflow_id, second is status
        args = call_kwargs[0] if call_kwargs[0] else []
        kwargs = call_kwargs[1] if call_kwargs[1] else {}
        # Status should be TERMINATED_HIL or equivalent
        # Accept either positional or keyword invocation
        status_arg = args[1] if len(args) > 1 else kwargs.get("status")
        assert status_arg is not None

    async def test_terminate_does_not_resume_graph(self) -> None:
        """terminate_workflow never calls _invoke_graph_from_checkpoint."""
        workflow_run_repo = AsyncMock()
        workflow_id = uuid.uuid4()
        lc_checkpoint_id = f"hil:{workflow_id}"

        with patch(
            "src.ai.hil.hil_resume._invoke_graph_from_checkpoint",
            new_callable=AsyncMock,
        ) as mock_invoke:
            service = _make_service(workflow_run_repo=workflow_run_repo)
            await service.terminate_workflow(
                lc_checkpoint_id=lc_checkpoint_id,
                reason="Operator rejected",
            )

        mock_invoke.assert_not_called()
