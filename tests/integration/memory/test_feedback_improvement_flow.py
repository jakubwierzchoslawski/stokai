"""
Integration tests for Layer 4 feedback + improvement loop flow (TASK-018).

Tests require a real PostgreSQL instance.
Run with:
  pytest tests/integration/memory/test_feedback_improvement_flow.py -m integration

AC-004: improvement proposal pending until admin approves
AC-005: thumbs_down by any user writes feedback row
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.ai.memory.repositories.feedback_repository import FeedbackRepository
from src.ai.memory.repositories.improvement_repository import ImprovementRepository
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackSource,
    FeedbackType,
    ProposalStatus,
    UserFeedbackCreate,
)
from src.ai.memory.services.improvement_loop_service import ImprovementLoopService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    import os
    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", ""),
    )
    if not db_url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")

    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine):
    async with pg_engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def feedback_repo(pg_session):
    return FeedbackRepository(pg_session)


@pytest_asyncio.fixture
async def improvement_repo(pg_session):
    return ImprovementRepository(pg_session)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_four_rejection_feedbacks_then_run_loop_creates_pending_proposal(
    feedback_repo, improvement_repo
):
    """
    AC-004: 4 rejections → improvement_loop → 1 proposal with status='pending'.
    """
    report_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    # Write 4 rejection feedback rows
    for _ in range(4):
        await feedback_repo.append_feedback(
            UserFeedbackCreate(
                tenant_id=tenant_id,
                report_id=report_id,
                feedback_type=FeedbackType.REJECT,
                source=FeedbackSource.IN_APP,
            )
        )

    # Run improvement loop
    service = ImprovementLoopService(
        feedback_repo=feedback_repo,
        improvement_repo=improvement_repo,
    )
    result = await service.run_improvement_loop()

    assert result.proposals_created >= 1

    # Check proposal is pending
    pending = await improvement_repo.list_pending()
    assert len(pending) >= 1
    assert all(p.status == ProposalStatus.PENDING for p in pending)


@pytest.mark.asyncio
async def test_approve_proposal_via_improvement_repo_changes_status(improvement_repo):
    """
    AC-004: After approval, proposal status changes from pending to approved.
    """
    from src.ai.memory.schemas.feedback_schemas import ImprovementProposalCreate

    proposal = await improvement_repo.create_proposal(
        ImprovementProposalCreate(
            proposal_type="prompt_adjustment",
            description="Integration test proposal",
            proposed_changes={"test": True},
            source_feedback_ids=[],
        )
    )
    assert proposal.status == ProposalStatus.PENDING

    admin_id = uuid.uuid4()
    approved = await improvement_repo.update_status(
        proposal_id=proposal.proposal_id,
        status=ProposalStatus.APPROVED,
        reviewed_by=admin_id,
    )
    assert approved.status == ProposalStatus.APPROVED
    assert approved.reviewed_by == admin_id


@pytest.mark.asyncio
async def test_thumbs_down_by_end_user_writes_feedback_row(feedback_repo):
    """
    AC-005: thumbs_down from end_user (no admin) inserts row without elevated perms.
    """
    tenant_id = uuid.uuid4()
    report_id = uuid.uuid4()

    feedback = await feedback_repo.append_feedback(
        UserFeedbackCreate(
            tenant_id=tenant_id,
            report_id=report_id,
            feedback_type=FeedbackType.THUMBS_DOWN,
            source=FeedbackSource.IN_APP,
        )
    )

    assert feedback.feedback_id is not None
    assert feedback.feedback_type == "thumbs_down"
    assert feedback.source == "in_app"

    # Verify retrieval
    all_for_report = await feedback_repo.get_feedback_for_report(report_id)
    assert any(f.feedback_id == feedback.feedback_id for f in all_for_report)
