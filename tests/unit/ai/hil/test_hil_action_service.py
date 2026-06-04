"""
Unit tests for HILActionService.

All repositories and external services are mocked. No real DB or LangGraph required.

TDD tests defined before implementation (PLAN-F-013 TASK-005).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.hil.hil_action_service import HILActionService, HILValidationError


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_service() -> tuple[HILActionService, MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (service, mock_hil_repo, mock_resume_service, mock_feedback_repo, mock_workflow_run_repo)."""
    mock_hil_repo = AsyncMock()
    mock_resume_service = AsyncMock()
    mock_feedback_repo = AsyncMock()
    mock_workflow_run_repo = AsyncMock()

    # Default: get returns a queue item
    item = MagicMock()
    item.item_id = uuid.uuid4()
    item.workflow_run_id = uuid.uuid4()
    item.tenant_id = uuid.uuid4()
    item.lc_checkpoint_id = f"hil:{uuid.uuid4()}"
    item.status = "pending"
    mock_hil_repo.get = AsyncMock(return_value=item)
    mock_hil_repo.update_status = AsyncMock(return_value=item)

    # Feedback repo returns a feedback object
    feedback = MagicMock()
    feedback.feedback_id = uuid.uuid4()
    mock_feedback_repo.create = AsyncMock(return_value=feedback)

    # Resume service returns a final state
    final_state = MagicMock()
    mock_resume_service.resume_from_checkpoint = AsyncMock(return_value=final_state)
    mock_resume_service.terminate_workflow = AsyncMock(return_value=None)

    service = HILActionService(
        hil_queue_repo=mock_hil_repo,
        resume_service=mock_resume_service,
        feedback_repo=mock_feedback_repo,
        workflow_run_repo=mock_workflow_run_repo,
    )
    return service, mock_hil_repo, mock_resume_service, mock_feedback_repo, mock_workflow_run_repo


@pytest.mark.asyncio
class TestApprove:
    """test_approve_resumes_workflow_and_writes_user_feedback"""

    async def test_approve_resumes_workflow_and_writes_user_feedback(self) -> None:
        service, hil_repo, resume_service, feedback_repo, wf_repo = _make_service()
        item_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()

        result = await service.apply_action(
            item_id=item_id,
            tenant_id=tenant_id,
            reviewer_id=reviewer_id,
            action="approve",
        )

        resume_service.resume_from_checkpoint.assert_called_once()
        call_kwargs = resume_service.resume_from_checkpoint.call_args[1]
        assert call_kwargs.get("override_text") is None

        feedback_repo.create.assert_called_once()
        fb_arg = feedback_repo.create.call_args[0][0]
        assert fb_arg.feedback_type == "approve"

        assert result.workflow_resumed is True
        assert result.feedback_id is not None


@pytest.mark.asyncio
class TestEditApprove:
    """test_edit_approve_resumes_with_override_text_and_writes_edit_feedback"""

    async def test_edit_approve_resumes_with_override_text_and_writes_edit_feedback(
        self,
    ) -> None:
        service, hil_repo, resume_service, feedback_repo, wf_repo = _make_service()
        item_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        edited_text = "Reviewer's improved report text."

        result = await service.apply_action(
            item_id=item_id,
            tenant_id=tenant_id,
            reviewer_id=reviewer_id,
            action="edit_approve",
            edited_text=edited_text,
        )

        resume_service.resume_from_checkpoint.assert_called_once()
        call_kwargs = resume_service.resume_from_checkpoint.call_args[1]
        assert call_kwargs.get("override_text") == edited_text

        feedback_repo.create.assert_called_once()
        fb_arg = feedback_repo.create.call_args[0][0]
        assert fb_arg.feedback_type == "edit_approve"
        assert fb_arg.user_edit == edited_text

        assert result.workflow_resumed is True

    async def test_edit_approve_raises_when_edited_text_missing(self) -> None:
        service, *_ = _make_service()

        with pytest.raises(HILValidationError, match="edited_text"):
            await service.apply_action(
                item_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                action="edit_approve",
                edited_text=None,
            )


@pytest.mark.asyncio
class TestReject:
    """test_reject_terminates_workflow_and_writes_reject_feedback"""

    async def test_reject_terminates_workflow_and_writes_reject_feedback(self) -> None:
        service, hil_repo, resume_service, feedback_repo, wf_repo = _make_service()

        result = await service.apply_action(
            item_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            action="reject",
        )

        resume_service.terminate_workflow.assert_called_once()
        resume_service.resume_from_checkpoint.assert_not_called()

        feedback_repo.create.assert_called_once()
        fb_arg = feedback_repo.create.call_args[0][0]
        assert fb_arg.feedback_type == "reject"

        assert result.workflow_resumed is False

    async def test_reject_with_feedback_stores_feedback_text(self) -> None:
        service, hil_repo, resume_service, feedback_repo, wf_repo = _make_service()
        feedback_text = "Insufficient data for recommendation."

        result = await service.apply_action(
            item_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            action="reject_with_feedback",
            feedback_text=feedback_text,
        )

        feedback_repo.create.assert_called_once()
        fb_arg = feedback_repo.create.call_args[0][0]
        assert fb_arg.feedback_type == "reject_with_feedback"
        assert fb_arg.feedback_text == feedback_text
        assert result.workflow_resumed is False

    async def test_reject_with_feedback_raises_when_feedback_text_missing(self) -> None:
        service, *_ = _make_service()

        with pytest.raises(HILValidationError, match="feedback_text"):
            await service.apply_action(
                item_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                action="reject_with_feedback",
                feedback_text=None,
            )


@pytest.mark.asyncio
class TestAuditRow:
    """test_every_action_writes_layer1_audit_row"""

    async def test_every_action_writes_layer1_audit_row(self) -> None:
        service, hil_repo, resume_service, feedback_repo, wf_repo = _make_service()

        for action in ("approve", "reject"):
            wf_repo.reset_mock()
            await service.apply_action(
                item_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                action=action,
            )
            # audit row is written via workflow_run_repo.append_audit_event or update_status
            # At minimum update_status must be called to record the HIL action
            assert (
                wf_repo.append_audit_event.called or wf_repo.update_status.called
            ), f"No audit call for action={action}"
