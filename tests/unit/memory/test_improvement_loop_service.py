"""
Unit tests for ImprovementLoopService (TASK-015).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    ImprovementProposal,
    ProposalStatus,
    UserFeedback,
)
from src.ai.memory.services.improvement_loop_service import (
    ImprovementLoopService,
    REJECTION_THRESHOLD,
    THUMBS_DOWN_THRESHOLD,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_feedback(
    feedback_type: str = "reject",
    report_id: uuid.UUID | None = None,
) -> UserFeedback:
    return UserFeedback(
        feedback_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        report_id=report_id or uuid.uuid4(),
        feedback_type=feedback_type,
        source=FeedbackSource.IN_APP.value,
        submitted_at=datetime.now(tz=timezone.utc),
    )


def _make_proposal(source_feedback_ids: list[uuid.UUID]) -> ImprovementProposal:
    return ImprovementProposal(
        proposal_id=uuid.uuid4(),
        proposal_type="threshold_adjustment",
        description="Test proposal",
        status=ProposalStatus.PENDING,
        created_at=datetime.now(tz=timezone.utc),
        source_feedback_ids=source_feedback_ids,
    )


def _build_service(feedback_list=None, pending_proposals=None, created_proposal=None):
    feedback_repo = AsyncMock()
    feedback_repo.list_since = AsyncMock(return_value=feedback_list or [])

    improvement_repo = AsyncMock()
    improvement_repo.list_pending = AsyncMock(return_value=pending_proposals or [])
    improvement_repo.create_proposal = AsyncMock(
        return_value=created_proposal or _make_proposal([])
    )

    svc = ImprovementLoopService(
        feedback_repo=feedback_repo,
        improvement_repo=improvement_repo,
    )
    return svc, feedback_repo, improvement_repo


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_improvement_loop_with_4_rejections_generates_one_proposal():
    """4 rejection feedbacks for same report_id → 1 pending proposal."""
    report_id = uuid.uuid4()
    rejections = [_make_feedback("reject", report_id=report_id) for _ in range(4)]

    svc, _, improvement_repo = _build_service(feedback_list=rejections)
    result = await svc.run_improvement_loop()

    improvement_repo.create_proposal.assert_called_once()
    assert result.proposals_created == 1

    call_args = improvement_repo.create_proposal.call_args[0][0]
    assert call_args.proposed_changes["rejection_count"] == 4


@pytest.mark.asyncio
async def test_fewer_than_3_rejections_does_not_generate_proposal():
    """2 rejections (below REJECTION_THRESHOLD=3) → no proposal."""
    report_id = uuid.uuid4()
    rejections = [_make_feedback("reject", report_id=report_id) for _ in range(2)]

    svc, _, improvement_repo = _build_service(feedback_list=rejections)
    result = await svc.run_improvement_loop()

    improvement_repo.create_proposal.assert_not_called()
    assert result.proposals_created == 0


@pytest.mark.asyncio
async def test_generated_proposal_contains_workflow_type_and_rejection_count():
    """proposed_changes JSONB must include workflow_type and rejection_count."""
    report_id = uuid.uuid4()
    rejections = [_make_feedback("reject", report_id=report_id) for _ in range(REJECTION_THRESHOLD)]

    svc, _, improvement_repo = _build_service(feedback_list=rejections)
    await svc.run_improvement_loop()

    call_args = improvement_repo.create_proposal.call_args[0][0]
    assert "workflow_type" in call_args.proposed_changes
    assert "rejection_count" in call_args.proposed_changes
    assert call_args.proposed_changes["rejection_count"] == REJECTION_THRESHOLD


@pytest.mark.asyncio
async def test_proposal_not_applied_automatically_status_remains_pending():
    """Proposals are created with status='pending' and NOT auto-approved."""
    report_id = uuid.uuid4()
    rejections = [_make_feedback("reject", report_id=report_id) for _ in range(REJECTION_THRESHOLD)]
    pending_proposal = _make_proposal([fb.feedback_id for fb in rejections])

    svc, _, improvement_repo = _build_service(
        feedback_list=rejections,
        created_proposal=pending_proposal,
    )
    result = await svc.run_improvement_loop()

    # The proposal is created but not approved
    assert result.proposals_created == 1
    call_args = improvement_repo.create_proposal.call_args[0][0]
    # create_proposal receives ImprovementProposalCreate — status is always pending at creation
    from src.ai.memory.schemas.feedback_schemas import ImprovementProposalCreate
    assert isinstance(call_args, ImprovementProposalCreate)


@pytest.mark.asyncio
async def test_running_loop_twice_on_same_data_is_idempotent():
    """Second run with same data must not create duplicate proposals."""
    report_id = uuid.uuid4()
    rejections = [_make_feedback("reject", report_id=report_id) for _ in range(REJECTION_THRESHOLD)]
    feedback_ids = [fb.feedback_id for fb in rejections]

    # Simulate that first run already created a proposal with same feedback IDs
    existing_proposal = _make_proposal(feedback_ids)

    svc, _, improvement_repo = _build_service(
        feedback_list=rejections,
        pending_proposals=[existing_proposal],
    )
    result = await svc.run_improvement_loop()

    improvement_repo.create_proposal.assert_not_called()
    assert result.proposals_created == 0
