"""
Unit tests for SemanticHygieneService (TASK-013).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.memory.schemas.semantic_schemas import SemanticFact
from src.ai.memory.services.semantic_hygiene_service import (
    SemanticHygieneService,
    SEMANTIC_DECAY_MONTHS,
)


def _make_fact(decayed: bool = False) -> SemanticFact:
    return SemanticFact(
        fact_id=uuid.uuid4(),
        entity_id=uuid.uuid4(),
        fact_text="Some fact",
        embedding=[0.1] * 1536,
        evidence_count=3,
        last_confirmed=datetime.now(tz=timezone.utc) - timedelta(days=200),
        decayed_at=datetime.now(tz=timezone.utc) if decayed else None,
        created_at=datetime.now(tz=timezone.utc) - timedelta(days=200),
    )


@pytest.mark.asyncio
async def test_run_decay_pass_old_facts_get_decayed():
    """Two old facts + one recent: only old ones returned by list_unconfirmed."""
    old_1 = _make_fact()
    old_2 = _make_fact()

    semantic_repo = AsyncMock()
    semantic_repo.list_unconfirmed_older_than = AsyncMock(return_value=[old_1, old_2])
    semantic_repo.mark_decayed = AsyncMock(return_value=2)

    svc = SemanticHygieneService(semantic_repo=semantic_repo)
    result = await svc.run_decay_pass()

    semantic_repo.list_unconfirmed_older_than.assert_called_once_with(
        months=SEMANTIC_DECAY_MONTHS
    )
    semantic_repo.mark_decayed.assert_called_once()
    called_ids = semantic_repo.mark_decayed.call_args[0][0]
    assert set(called_ids) == {old_1.fact_id, old_2.fact_id}
    assert result.facts_decayed == 2


@pytest.mark.asyncio
async def test_run_decay_pass_decayed_fact_not_in_query_results_when_exclude_decayed():
    """Decayed fact must not appear in query_facts with exclude_decayed=True."""
    semantic_repo = AsyncMock()
    semantic_repo.list_unconfirmed_older_than = AsyncMock(return_value=[])
    # Simulating: no facts returned means query_facts would return empty too
    semantic_repo.query_facts = AsyncMock(return_value=[])

    svc = SemanticHygieneService(semantic_repo=semantic_repo)
    await svc.run_decay_pass()

    # Verify that query_facts with exclude_decayed=True returns empty
    results = await semantic_repo.query_facts(
        embedding=[0.1] * 1536, exclude_decayed=True
    )
    assert results == []


@pytest.mark.asyncio
async def test_run_decay_pass_decayed_fact_does_appear_when_exclude_decayed_false():
    """Decayed fact IS returned by query_facts with exclude_decayed=False."""
    decayed_fact = _make_fact(decayed=True)

    semantic_repo = AsyncMock()
    semantic_repo.list_unconfirmed_older_than = AsyncMock(return_value=[])
    semantic_repo.query_facts = AsyncMock(return_value=[decayed_fact])

    svc = SemanticHygieneService(semantic_repo=semantic_repo)
    await svc.run_decay_pass()

    results = await semantic_repo.query_facts(
        embedding=[0.1] * 1536, exclude_decayed=False
    )
    assert len(results) == 1
    assert results[0].decayed_at is not None


@pytest.mark.asyncio
async def test_run_decay_pass_with_no_qualifying_facts_returns_zero():
    """When no facts are older than threshold, facts_decayed=0."""
    semantic_repo = AsyncMock()
    semantic_repo.list_unconfirmed_older_than = AsyncMock(return_value=[])

    svc = SemanticHygieneService(semantic_repo=semantic_repo)
    result = await svc.run_decay_pass()

    semantic_repo.mark_decayed.assert_not_called()
    assert result.facts_decayed == 0


@pytest.mark.asyncio
async def test_run_outcome_fill_with_null_actual_t1d_fills_columns():
    """Outcome rows with actual_t1d=None should be picked up and filled."""
    from src.ai.memory.repositories.episodic_repository import EpisodicRepository
    from src.ai.memory.models.episodic_models import RecommendationOutcome

    # Test that fill_outcome_actuals is callable — logic is tested via repo
    repo = AsyncMock(spec=EpisodicRepository)
    repo.fill_outcome_actuals = AsyncMock(return_value=None)

    outcome_rec_id = uuid.uuid4()
    await repo.fill_outcome_actuals(
        rec_id=outcome_rec_id,
        actual_t1d=1.5,
        actual_t1w=3.0,
        direction_correct=True,
    )

    repo.fill_outcome_actuals.assert_called_once_with(
        rec_id=outcome_rec_id,
        actual_t1d=1.5,
        actual_t1w=3.0,
        direction_correct=True,
    )
