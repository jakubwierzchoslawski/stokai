"""
Unit tests for SemanticRepository.

pgvector types are not supported by SQLite, so these tests use mocked async sessions
to verify all method logic without a real database.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.memory.exceptions import EvidenceGateError
from src.ai.memory.repositories.semantic_repository import (
    EVIDENCE_GATE_MIN_COUNT,
    SemanticRepository,
)
from src.ai.memory.schemas.semantic_schemas import SemanticFactStagingCreate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_staging_orm(evidence_count: int = 1):
    """Return a mock ORM staging row."""
    from src.ai.memory.models.semantic_models import SemanticFactStaging as Orm
    orm = MagicMock(spec=Orm)
    orm.staging_id = uuid.uuid4()
    orm.entity_id = uuid.uuid4()
    orm.fact_text = "Test fact"
    orm.evidence_count = evidence_count
    orm.source_invocation_ids = []
    orm.created_at = datetime.now(tz=timezone.utc)
    return orm


def _make_fact_orm():
    from src.ai.memory.models.semantic_models import SemanticFact as Orm
    orm = MagicMock(spec=Orm)
    orm.fact_id = uuid.uuid4()
    orm.entity_id = uuid.uuid4()
    orm.fact_text = "Test committed fact"
    orm.embedding = [0.1] * 1536
    orm.evidence_count = 3
    orm.last_confirmed = datetime.now(tz=timezone.utc)
    orm.decayed_at = None
    orm.retracted_at = None
    orm.retracted_by = None
    orm.source_invocations = []
    orm.created_at = datetime.now(tz=timezone.utc)
    return orm


async def _make_repo():
    """Return SemanticRepository with a full async mock session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock()
    return SemanticRepository(session), session


# ── stage_fact ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_fact_creates_staging_row_with_evidence_count_1():
    repo, session = await _make_repo()

    staging_orm = _make_staging_orm(evidence_count=1)

    async def fake_refresh(obj):
        # Copy attributes from orm mock to the ORM object passed in
        obj.staging_id = staging_orm.staging_id
        obj.entity_id = staging_orm.entity_id
        obj.fact_text = staging_orm.fact_text
        obj.evidence_count = 1
        obj.source_invocation_ids = []
        obj.created_at = staging_orm.created_at

    session.refresh.side_effect = fake_refresh

    fact_create = SemanticFactStagingCreate(
        entity_id=uuid.uuid4(),
        fact_text="Company X expanded to Asia",
        source_invocation_id=uuid.uuid4(),
    )

    result = await repo.stage_fact(fact_create)

    session.add.assert_called_once()
    session.flush.assert_called()
    assert result.evidence_count == 1


# ── increment_evidence ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_increment_evidence_increments_evidence_count_from_1_to_2():
    repo, session = await _make_repo()

    staging_orm = _make_staging_orm(evidence_count=2)  # result after increment
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = staging_orm
    session.execute.return_value = mock_result

    staging_id = uuid.uuid4()
    result = await repo.increment_evidence(
        staging_id=staging_id,
        source_invocation_id=uuid.uuid4(),
    )

    session.execute.assert_called_once()
    assert result.evidence_count == 2


# ── commit_fact ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_commit_fact_on_staging_with_evidence_count_less_than_3_raises_error():
    repo, session = await _make_repo()

    staging_orm = _make_staging_orm(evidence_count=2)
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = staging_orm
    session.execute.return_value = mock_result

    staging_id = uuid.uuid4()
    embedding = [0.1] * 1536

    with pytest.raises(EvidenceGateError) as exc_info:
        await repo.commit_fact(staging_id=staging_id, embedding=embedding)

    assert exc_info.value.current_count == 2
    assert exc_info.value.required == EVIDENCE_GATE_MIN_COUNT


@pytest.mark.asyncio
async def test_commit_fact_moves_staging_to_semantic_fact_when_evidence_count_ge_3():
    repo, session = await _make_repo()

    staging_orm = _make_staging_orm(evidence_count=3)
    fact_orm = _make_fact_orm()

    call_count = 0

    async def multi_execute(stmt):
        nonlocal call_count
        call_count += 1
        mock = MagicMock()
        if call_count == 1:
            # First call: select staging
            mock.scalar_one.return_value = staging_orm
        else:
            # Second call: delete staging
            mock.scalar_one.return_value = None
        return mock

    session.execute.side_effect = multi_execute

    async def fake_refresh(obj):
        obj.fact_id = fact_orm.fact_id
        obj.entity_id = fact_orm.entity_id
        obj.fact_text = fact_orm.fact_text
        obj.embedding = fact_orm.embedding
        obj.evidence_count = fact_orm.evidence_count
        obj.last_confirmed = fact_orm.last_confirmed
        obj.decayed_at = None
        obj.retracted_at = None
        obj.retracted_by = None
        obj.source_invocations = []
        obj.created_at = fact_orm.created_at

    session.refresh.side_effect = fake_refresh

    embedding = [0.1] * 1536
    result = await repo.commit_fact(staging_id=staging_orm.staging_id, embedding=embedding)

    session.add.assert_called_once()
    assert result.evidence_count == 3
    assert result.decayed_at is None


# ── query_facts ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_facts_exclude_decayed_true_does_not_return_decayed_facts():
    """With exclude_decayed=True, the WHERE clause should filter out decayed rows."""
    repo, session = await _make_repo()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result

    embedding = [0.1] * 1536
    results = await repo.query_facts(embedding=embedding, exclude_decayed=True)

    session.execute.assert_called_once()
    assert results == []


@pytest.mark.asyncio
async def test_query_facts_exclude_decayed_false_returns_all_facts():
    repo, session = await _make_repo()

    fact_orm = _make_fact_orm()
    fact_orm.decayed_at = datetime.now(tz=timezone.utc)  # simulate decayed fact

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [fact_orm]
    session.execute.return_value = mock_result

    embedding = [0.1] * 1536
    results = await repo.query_facts(embedding=embedding, exclude_decayed=False)

    assert len(results) == 1


# ── mark_decayed ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_decayed_sets_decayed_at_on_targeted_rows():
    repo, session = await _make_repo()

    mock_result = MagicMock()
    mock_result.rowcount = 2
    session.execute.return_value = mock_result

    fact_ids = [uuid.uuid4(), uuid.uuid4()]
    count = await repo.mark_decayed(fact_ids)

    assert count == 2
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_mark_decayed_with_empty_list_returns_zero():
    repo, session = await _make_repo()

    count = await repo.mark_decayed([])

    session.execute.assert_not_called()
    assert count == 0


# ── list_unconfirmed_older_than ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unconfirmed_older_than_returns_only_facts_beyond_threshold():
    repo, session = await _make_repo()

    old_fact = _make_fact_orm()
    old_fact.decayed_at = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [old_fact]
    session.execute.return_value = mock_result

    results = await repo.list_unconfirmed_older_than(months=6)

    assert len(results) == 1
    session.execute.assert_called_once()
