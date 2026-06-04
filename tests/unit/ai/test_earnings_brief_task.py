"""
Unit tests for earnings_brief_task Celery task.

TDD — PLAN-F-009 TASK-005.

Tests cover:
- Completes successfully → status='completed', confidence set
- Sets hil_status when confidence < 0.70 (requires_hil=True) → status='hil'
- Updates run status to 'failed' on unexpected exception
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_brief_run_orm(run_id: uuid.UUID | None = None) -> MagicMock:
    m = MagicMock()
    m.run_id = run_id or uuid.uuid4()
    m.workflow_id = uuid.uuid4()
    return m


class TestRunEarningsBriefAsync:
    """_run_earnings_brief_async — async core of earnings_brief_task."""

    def _make_patch_context(
        self,
        *,
        overall_confidence: float = 0.85,
        requires_hil: bool = False,
        cost_usd: float = 0.10,
        run_id: uuid.UUID | None = None,
    ):
        """Build all required mocks for a successful task run."""
        brief_run = _make_brief_run_orm(run_id=run_id)

        mock_session = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_run_repo.insert = AsyncMock(return_value=brief_run)
        mock_run_repo.update_status = AsyncMock()

        from src.ai.workflows.earnings_brief.state import EarningsBriefState

        final_state = EarningsBriefState(
            workflow_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            earnings_date=date.today(),
            started_at=datetime.now(tz=timezone.utc),
            overall_confidence=overall_confidence,
            requires_hil=requires_hil,
            cost_usd=cost_usd,
        )

        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(return_value=final_state)

        return brief_run, mock_session, mock_run_repo, mock_workflow

    @pytest.mark.asyncio
    async def test_completes_successfully_high_confidence(self):
        """Task returns status='completed' when overall_confidence >= 0.70."""
        from src.ai.tasks.earnings_brief_task import _run_earnings_brief_async

        run_id = uuid.uuid4()
        brief_run, mock_session, mock_run_repo, mock_workflow = self._make_patch_context(
            overall_confidence=0.85,
            requires_hil=False,
            run_id=run_id,
        )

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunCreate",
        ), patch(
            "src.ai.tasks.earnings_brief_task.build_earnings_brief_workflow",
            return_value=mock_workflow,
        ), patch(
            "src.ai.tasks.earnings_brief_task._get_registry",
            return_value=MagicMock(),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _run_earnings_brief_async(
                company_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                earnings_date_str=date.today().isoformat(),
                user_id=str(uuid.uuid4()),
            )

        assert result["status"] == "completed"
        assert result["confidence"] == 0.85
        mock_run_repo.update_status.assert_called()

    @pytest.mark.asyncio
    async def test_sets_hil_status_on_low_confidence(self):
        """Task returns status='hil' when requires_hil=True (confidence 0.40-0.69)."""
        from src.ai.tasks.earnings_brief_task import _run_earnings_brief_async

        run_id = uuid.uuid4()
        brief_run, mock_session, mock_run_repo, mock_workflow = self._make_patch_context(
            overall_confidence=0.55,
            requires_hil=True,
            run_id=run_id,
        )

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunCreate",
        ), patch(
            "src.ai.tasks.earnings_brief_task.build_earnings_brief_workflow",
            return_value=mock_workflow,
        ), patch(
            "src.ai.tasks.earnings_brief_task._get_registry",
            return_value=MagicMock(),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _run_earnings_brief_async(
                company_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                earnings_date_str=date.today().isoformat(),
                user_id=str(uuid.uuid4()),
            )

        assert result["status"] == "hil"
        assert result["confidence"] == 0.55

    @pytest.mark.asyncio
    async def test_updates_run_status_on_completion(self):
        """update_status is called on the brief run repo after workflow completion."""
        from src.ai.tasks.earnings_brief_task import _run_earnings_brief_async

        brief_run, mock_session, mock_run_repo, mock_workflow = self._make_patch_context(
            overall_confidence=0.85,
            requires_hil=False,
        )

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunCreate",
        ), patch(
            "src.ai.tasks.earnings_brief_task.build_earnings_brief_workflow",
            return_value=mock_workflow,
        ), patch(
            "src.ai.tasks.earnings_brief_task._get_registry",
            return_value=MagicMock(),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _run_earnings_brief_async(
                company_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                earnings_date_str=date.today().isoformat(),
                user_id=str(uuid.uuid4()),
            )

        # update_status must be called once after workflow completion
        mock_run_repo.update_status.assert_called_once()
        call_kwargs = mock_run_repo.update_status.call_args
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_failed_status_on_workflow_exception(self):
        """Returns status='failed' when the workflow raises an unexpected exception."""
        from src.ai.tasks.earnings_brief_task import _run_earnings_brief_async

        brief_run = _make_brief_run_orm()
        mock_session = AsyncMock()
        mock_run_repo = AsyncMock()
        mock_run_repo.insert = AsyncMock(return_value=brief_run)
        mock_run_repo.update_status = AsyncMock()

        mock_workflow = AsyncMock()
        mock_workflow.ainvoke = AsyncMock(side_effect=RuntimeError("LLM error"))

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunCreate",
        ), patch(
            "src.ai.tasks.earnings_brief_task.build_earnings_brief_workflow",
            return_value=mock_workflow,
        ), patch(
            "src.ai.tasks.earnings_brief_task._get_registry",
            return_value=MagicMock(),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _run_earnings_brief_async(
                company_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                earnings_date_str=date.today().isoformat(),
                user_id=str(uuid.uuid4()),
            )

        assert result["status"] == "failed"
        # update_status still called to record failure
        mock_run_repo.update_status.assert_called_once()
