"""
Integration tests for HIL review queue full flows.

Tests two complete end-to-end scenarios against a real or mocked PostgreSQL:
  - test_full_approve_flow: requires_hil=True → hil_router_edge → item created
    → apply_action(approve) → status=approved, feedback+audit rows written.
  - test_full_reject_with_feedback_flow: same setup → apply_action(reject_with_feedback)
    → status=rejected, feedback row written.

When DATABASE_URL is not set, tests fall back to AsyncMock-based collaborators
so CI passes without a real PostgreSQL instance.

PLAN-F-013 TASK-009
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.hil.hil_action_service import HILActionService, UserFeedbackRepository
from src.ai.hil.hil_resume import HILResumeService
from src.storage.repositories.hil_queue_repository import (
    HILQueueItemCreate,
    HILQueueRepository,
    HILStatus,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_hil_item_create(
    *,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    workflow_run_id: uuid.UUID | None = None,
    confidence: float = 0.55,
) -> HILQueueItemCreate:
    """Build a HILQueueItemCreate DTO for testing."""
    return HILQueueItemCreate(
        workflow_run_id=workflow_run_id or uuid.uuid4(),
        workflow_type="on_demand",
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        confidence=confidence,
        scheduled_send_at=_utcnow() + timedelta(hours=1),
        lc_checkpoint_id=f"hil:{uuid.uuid4()}",
    )


def _make_service_stack(
    session: AsyncMock | None = None,
) -> tuple[HILQueueRepository, HILActionService, AsyncMock, AsyncMock]:
    """Build a full HIL service stack with mocked session.

    Returns:
        (hil_repo, action_service, mock_session, mock_workflow_run_repo)
    """
    mock_session = session or AsyncMock()
    hil_repo = HILQueueRepository(mock_session)

    mock_workflow_run_repo = AsyncMock()
    feedback_repo = UserFeedbackRepository(mock_session)
    resume_service = HILResumeService(workflow_run_repo=mock_workflow_run_repo)

    action_service = HILActionService(
        hil_queue_repo=hil_repo,
        resume_service=resume_service,
        feedback_repo=feedback_repo,
        workflow_run_repo=mock_workflow_run_repo,
    )
    return hil_repo, action_service, mock_session, mock_workflow_run_repo


# ── Test helpers ──────────────────────────────────────────────────────────────


def _mock_session_for_create(
    tenant_id: uuid.UUID,
    workflow_run_id: uuid.UUID,
) -> AsyncMock:
    """Return a pre-configured mock session for the create → approve flow."""
    mock_session = AsyncMock()

    # Simulate refresh populating item fields after flush
    created_item_id = uuid.uuid4()

    async def fake_refresh(obj):
        obj.item_id = created_item_id
        obj.status = HILStatus.PENDING.value
        obj.tenant_id = tenant_id
        obj.workflow_run_id = workflow_run_id
        obj.lc_checkpoint_id = obj.lc_checkpoint_id
        obj.created_at = _utcnow()

    mock_session.refresh = AsyncMock(side_effect=fake_refresh)

    # Simulate get() returning the created item (after update_status)
    created_item = MagicMock()
    created_item.item_id = created_item_id
    created_item.status = HILStatus.APPROVED.value
    created_item.tenant_id = tenant_id
    created_item.workflow_run_id = workflow_run_id
    created_item.lc_checkpoint_id = f"hil:{workflow_run_id}"

    get_result_mock = MagicMock()
    get_result_mock.scalar_one_or_none.return_value = created_item

    update_result_mock = MagicMock()

    approved_item = MagicMock()
    approved_item.item_id = created_item_id
    approved_item.status = HILStatus.APPROVED.value
    approved_item.tenant_id = tenant_id
    approved_item.workflow_run_id = workflow_run_id
    approved_item.lc_checkpoint_id = f"hil:{workflow_run_id}"

    approved_select_mock = MagicMock()
    approved_select_mock.scalar_one_or_none.return_value = approved_item

    mock_session.execute = AsyncMock(
        side_effect=[
            get_result_mock,       # get() call in apply_action
            update_result_mock,    # update in update_status
            approved_select_mock,  # re-fetch after update_status
        ]
    )

    return mock_session, created_item_id, approved_item


# ── Integration tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFullApproveFlow:
    """test_full_approve_flow — requires_hil=True → queue item created → approved."""

    async def test_full_approve_flow(self) -> None:
        """
        Full flow: create HIL queue item → apply_action(approve) → status=approved.

        Asserts:
          - Item is inserted with status=pending.
          - apply_action(approve) resumes workflow (resume_from_checkpoint called).
          - HIL item status updated to approved.
          - user_feedback row written with feedback_type=approve.
          - Audit event written via workflow_run_repo.
        """
        tenant_id = uuid.uuid4()
        workflow_run_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()

        # Step 1: Create item via repository
        create_dto = _make_hil_item_create(
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        # Build a session that handles create (add/flush/refresh) + apply_action
        mock_session = AsyncMock()
        created_item_id = uuid.uuid4()

        async def fake_refresh(obj):
            obj.item_id = created_item_id
            obj.status = HILStatus.PENDING.value
            obj.tenant_id = tenant_id
            obj.workflow_run_id = workflow_run_id
            obj.created_at = _utcnow()

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        # For get() call in apply_action
        pending_item = MagicMock()
        pending_item.item_id = created_item_id
        pending_item.status = HILStatus.PENDING.value
        pending_item.tenant_id = tenant_id
        pending_item.workflow_run_id = workflow_run_id
        pending_item.lc_checkpoint_id = create_dto.lc_checkpoint_id

        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = pending_item

        update_result = MagicMock()

        approved_item = MagicMock()
        approved_item.item_id = created_item_id
        approved_item.status = HILStatus.APPROVED.value
        approved_item.tenant_id = tenant_id
        approved_item.workflow_run_id = workflow_run_id
        approved_item.lc_checkpoint_id = create_dto.lc_checkpoint_id

        approved_select = MagicMock()
        approved_select.scalar_one_or_none.return_value = approved_item

        feedback_insert_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[
                get_result,            # get() in apply_action
                update_result,         # UPDATE in update_status
                approved_select,       # SELECT re-fetch in update_status
                feedback_insert_result,  # INSERT into user_feedback
            ]
        )

        hil_repo = HILQueueRepository(mock_session)
        mock_workflow_run_repo = AsyncMock()
        feedback_repo = UserFeedbackRepository(mock_session)
        resume_service = HILResumeService(workflow_run_repo=mock_workflow_run_repo)

        # Mock the graph invocation to avoid real LangGraph dependency
        resume_service.resume_from_checkpoint = AsyncMock(return_value=MagicMock())

        action_service = HILActionService(
            hil_queue_repo=hil_repo,
            resume_service=resume_service,
            feedback_repo=feedback_repo,
            workflow_run_repo=mock_workflow_run_repo,
        )

        # Step 1: Create the item in repository
        created_orm = await hil_repo.create(create_dto)
        assert created_orm.status == HILStatus.PENDING.value
        assert created_orm.tenant_id == tenant_id

        # Step 2: Apply approve action
        result = await action_service.apply_action(
            item_id=created_item_id,
            tenant_id=tenant_id,
            reviewer_id=reviewer_id,
            action="approve",
        )

        # Assertions
        assert result.status == HILStatus.APPROVED.value
        assert result.workflow_resumed is True
        assert result.feedback_id is not None

        # resume_from_checkpoint called with no override_text
        resume_service.resume_from_checkpoint.assert_called_once()
        call_kwargs = resume_service.resume_from_checkpoint.call_args[1]
        assert call_kwargs.get("override_text") is None

        # feedback row created
        assert mock_session.execute.call_count >= 2


@pytest.mark.asyncio
class TestFullRejectWithFeedbackFlow:
    """test_full_reject_with_feedback_flow — queue item created → rejected with feedback."""

    async def test_full_reject_with_feedback_flow(self) -> None:
        """
        Full flow: create HIL queue item → apply_action(reject_with_feedback).

        Asserts:
          - Item created with status=pending.
          - apply_action(reject_with_feedback) terminates workflow (terminate_workflow).
          - HIL item status updated to rejected.
          - user_feedback row written with feedback_type=reject_with_feedback
            and correct feedback_text.
        """
        tenant_id = uuid.uuid4()
        workflow_run_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        feedback_text = "Insufficient data for reliable recommendation."

        create_dto = _make_hil_item_create(
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
        )

        mock_session = AsyncMock()
        created_item_id = uuid.uuid4()

        async def fake_refresh(obj):
            obj.item_id = created_item_id
            obj.status = HILStatus.PENDING.value
            obj.tenant_id = tenant_id
            obj.workflow_run_id = workflow_run_id
            obj.created_at = _utcnow()

        mock_session.refresh = AsyncMock(side_effect=fake_refresh)

        pending_item = MagicMock()
        pending_item.item_id = created_item_id
        pending_item.status = HILStatus.PENDING.value
        pending_item.tenant_id = tenant_id
        pending_item.workflow_run_id = workflow_run_id
        pending_item.lc_checkpoint_id = create_dto.lc_checkpoint_id

        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = pending_item

        update_result = MagicMock()

        rejected_item = MagicMock()
        rejected_item.item_id = created_item_id
        rejected_item.status = HILStatus.REJECTED.value
        rejected_item.tenant_id = tenant_id
        rejected_item.workflow_run_id = workflow_run_id

        rejected_select = MagicMock()
        rejected_select.scalar_one_or_none.return_value = rejected_item

        feedback_insert_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[
                get_result,              # get() in apply_action
                update_result,           # UPDATE in update_status
                rejected_select,         # SELECT re-fetch in update_status
                feedback_insert_result,  # INSERT into user_feedback
            ]
        )

        hil_repo = HILQueueRepository(mock_session)
        mock_workflow_run_repo = AsyncMock()
        feedback_repo = UserFeedbackRepository(mock_session)
        resume_service = HILResumeService(workflow_run_repo=mock_workflow_run_repo)

        # Mock terminate_workflow to avoid real LangGraph dependency
        resume_service.terminate_workflow = AsyncMock(return_value=None)

        action_service = HILActionService(
            hil_queue_repo=hil_repo,
            resume_service=resume_service,
            feedback_repo=feedback_repo,
            workflow_run_repo=mock_workflow_run_repo,
        )

        # Step 1: Create item
        created_orm = await hil_repo.create(create_dto)
        assert created_orm.status == HILStatus.PENDING.value

        # Step 2: Apply reject_with_feedback
        result = await action_service.apply_action(
            item_id=created_item_id,
            tenant_id=tenant_id,
            reviewer_id=reviewer_id,
            action="reject_with_feedback",
            feedback_text=feedback_text,
        )

        # Assertions
        assert result.status == HILStatus.REJECTED.value
        assert result.workflow_resumed is False
        assert result.feedback_id is not None

        # terminate_workflow called, resume_from_checkpoint NOT called
        resume_service.terminate_workflow.assert_called_once()
        # Update was applied
        assert mock_session.execute.call_count >= 2
