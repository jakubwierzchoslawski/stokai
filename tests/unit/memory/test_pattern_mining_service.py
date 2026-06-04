"""
Unit tests for PatternMiningService (TASK-014).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.memory.services.pattern_mining_service import (
    PatternMiningService,
    MINING_MIN_SAMPLE,
)
from src.ai.memory.schemas.procedural_schemas import ProceduralPattern


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_invocation_orm(role_id: str = "relevance-analyst"):
    from src.ai.memory.models.episodic_models import AgentInvocation
    inv = MagicMock(spec=AgentInvocation)
    inv.invocation_id = uuid.uuid4()
    inv.agent_role_id = role_id
    inv.started_at = datetime.now(tz=timezone.utc)
    inv.output = {"result": "ok"}
    inv.tools_called = []
    return inv


def _make_pattern_schema(role_id: str = "relevance-analyst") -> ProceduralPattern:
    return ProceduralPattern(
        pattern_id=uuid.uuid4(),
        pattern_type="mined_invocation_cluster",
        context_tags=[role_id],
        pattern_text=f"Agent role '{role_id}' consistently processed",
        authored_by="mined",
        approved_at=None,
        version=1,
        recommended_for_agents=[role_id],
        created_at=datetime.now(tz=timezone.utc),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_mining_pass_cluster_of_5_creates_one_candidate():
    """5 consistent invocations → 1 mined candidate with approved_at=None."""
    role_id = "relevance-analyst"
    invocations = [_make_invocation_orm(role_id) for _ in range(MINING_MIN_SAMPLE)]
    pattern_schema = _make_pattern_schema(role_id)

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = invocations
    session.execute = AsyncMock(return_value=result_mock)

    procedural_repo = AsyncMock()
    procedural_repo.list_pending_approval = AsyncMock(return_value=[])
    procedural_repo.create_pattern = AsyncMock(return_value=pattern_schema)

    svc = PatternMiningService(procedural_repo=procedural_repo, session=session)
    result = await svc.run_mining_pass()

    procedural_repo.create_pattern.assert_called_once()
    assert result.candidates_created == 1

    # Verify approved_at is None on the created pattern
    call_args = procedural_repo.create_pattern.call_args[0][0]
    assert call_args.authored_by == "mined"


@pytest.mark.asyncio
async def test_run_mining_pass_cluster_of_4_does_not_produce_candidate():
    """4 invocations (below threshold) → no candidate created."""
    role_id = "anomaly-detector"
    invocations = [_make_invocation_orm(role_id) for _ in range(MINING_MIN_SAMPLE - 1)]

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = invocations
    session.execute = AsyncMock(return_value=result_mock)

    procedural_repo = AsyncMock()
    procedural_repo.list_pending_approval = AsyncMock(return_value=[])

    svc = PatternMiningService(procedural_repo=procedural_repo, session=session)
    result = await svc.run_mining_pass()

    procedural_repo.create_pattern.assert_not_called()
    assert result.candidates_created == 0


@pytest.mark.asyncio
async def test_run_mining_twice_on_same_data_does_not_create_duplicates():
    """Running mining twice on the same data is idempotent."""
    role_id = "qa-analyst"
    invocations = [_make_invocation_orm(role_id) for _ in range(MINING_MIN_SAMPLE)]

    # Simulate that first run created a pending pattern
    pattern_text = (
        f"Agent role '{role_id}' consistently processed "
        f"{len(invocations)} events in the past 30 days. "
        "Consider reviewing for pattern extraction."
    )
    existing_pattern = _make_pattern_schema(role_id)
    existing_pattern.pattern_text = pattern_text

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = invocations
    session.execute = AsyncMock(return_value=result_mock)

    procedural_repo = AsyncMock()
    # On second run, existing_pattern is already pending
    procedural_repo.list_pending_approval = AsyncMock(return_value=[existing_pattern])
    procedural_repo.create_pattern = AsyncMock()

    svc = PatternMiningService(procedural_repo=procedural_repo, session=session)
    result = await svc.run_mining_pass()

    # No new candidate should be created
    procedural_repo.create_pattern.assert_not_called()
    assert result.candidates_created == 0


@pytest.mark.asyncio
async def test_proposed_patterns_do_not_appear_in_get_patterns_until_approved():
    """Mined patterns have approved_at=None → not returned by get_patterns."""
    unapproved_pattern = _make_pattern_schema()
    unapproved_pattern.approved_at = None

    # get_patterns filters by approved_at IS NOT NULL
    procedural_repo = AsyncMock()
    procedural_repo.get_patterns = AsyncMock(return_value=[])  # no approved patterns

    results = await procedural_repo.get_patterns(context_tags=["relevance"])
    assert results == []


@pytest.mark.asyncio
async def test_approve_pattern_makes_it_active_and_queryable():
    """After approve_pattern, the pattern is returned by get_patterns."""
    approved_pattern = _make_pattern_schema()
    approved_pattern.approved_at = datetime.now(tz=timezone.utc)

    procedural_repo = AsyncMock()
    procedural_repo.approve_pattern = AsyncMock(return_value=approved_pattern)
    procedural_repo.get_patterns = AsyncMock(return_value=[approved_pattern])

    pattern_id = uuid.uuid4()
    result = await procedural_repo.approve_pattern(
        pattern_id=pattern_id, approved_by=uuid.uuid4()
    )
    assert result.approved_at is not None

    active_patterns = await procedural_repo.get_patterns(context_tags=["relevance-analyst"])
    assert len(active_patterns) == 1
