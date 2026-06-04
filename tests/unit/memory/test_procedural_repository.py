"""
Unit tests for ProceduralRepository using mocked async sessions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.memory.repositories.procedural_repository import ProceduralRepository
from src.ai.memory.schemas.procedural_schemas import AuthoredBy, ProceduralPatternCreate


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return session


def _make_pattern_orm(approved: bool = False, retracted: bool = False):
    from src.ai.memory.models.procedural_models import ProceduralPattern as Orm
    orm = MagicMock(spec=Orm)
    orm.pattern_id = uuid.uuid4()
    orm.pattern_type = "reasoning"
    orm.context_tags = ["geopolitical", "relevance"]
    orm.pattern_text = "Step 1: identify region."
    orm.authored_by = "human"
    orm.approved_at = datetime.now(tz=timezone.utc) if approved else None
    orm.approved_by = uuid.uuid4() if approved else None
    orm.version = 1
    orm.success_rate = 0.85
    orm.sample_size = 20
    orm.confidence = 0.9
    orm.recommended_for_agents = ["relevance-analyst"]
    orm.created_at = datetime.now(tz=timezone.utc)
    orm.retracted_at = datetime.now(tz=timezone.utc) if retracted else None
    return orm


# ── get_patterns ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_patterns_returns_only_approved_non_retracted_patterns():
    session = _make_session()
    approved_orm = _make_pattern_orm(approved=True)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [approved_orm]
    session.execute.return_value = mock_result

    repo = ProceduralRepository(session)
    results = await repo.get_patterns(context_tags=["geopolitical"])

    assert len(results) == 1
    assert results[0].approved_at is not None
    assert results[0].retracted_at is None


@pytest.mark.asyncio
async def test_get_patterns_returns_empty_list_when_only_retracted():
    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    repo = ProceduralRepository(session)
    results = await repo.get_patterns(context_tags=["geopolitical"])

    assert results == []


# ── list_pending_approval ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_approval_returns_only_unapproved_patterns():
    session = _make_session()
    unapproved_orm = _make_pattern_orm(approved=False)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [unapproved_orm]
    session.execute.return_value = mock_result

    repo = ProceduralRepository(session)
    results = await repo.list_pending_approval()

    assert len(results) == 1
    assert results[0].approved_at is None


# ── approve_pattern ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_pattern_sets_approval_columns():
    session = _make_session()
    approved_orm = _make_pattern_orm(approved=True)

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = approved_orm
    session.execute.return_value = mock_result

    repo = ProceduralRepository(session)
    pattern_id = uuid.uuid4()
    approved_by = uuid.uuid4()

    result = await repo.approve_pattern(pattern_id=pattern_id, approved_by=approved_by)

    assert result.approved_at is not None
    session.flush.assert_called()


# ── retract_pattern ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retract_pattern_sets_retracted_at():
    session = _make_session()
    mock_result = MagicMock()
    session.execute.return_value = mock_result

    repo = ProceduralRepository(session)
    pattern_id = uuid.uuid4()

    await repo.retract_pattern(pattern_id=pattern_id, retracted_by=uuid.uuid4())

    session.execute.assert_called_once()
    session.flush.assert_called_once()
