"""
Integration tests for Layer 2 semantic memory flow (TASK-018).

Tests require a real PostgreSQL instance with pgvector extension enabled.
Run with:
  pytest tests/integration/memory/test_semantic_flow.py -m integration

AC-002: evidence_count >= 3 gate
AC-003: 6-month decay
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.ai.memory.repositories.semantic_repository import SemanticRepository
from src.ai.memory.schemas.semantic_schemas import SemanticFactStagingCreate
from src.ai.memory.services.semantic_hygiene_service import SemanticHygieneService

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
async def repo(pg_session):
    return SemanticRepository(pg_session)


@pytest_asyncio.fixture
async def hygiene(repo):
    return SemanticHygieneService(semantic_repo=repo)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_propose_fact_three_times_commits_on_third(repo, pg_session):
    """
    AC-002: proposing the same fact 3 times commits to semantic_fact.
    """
    from src.ai.memory.models.semantic_models import SemanticFactStaging as StagingORM
    from src.ai.memory.exceptions import EvidenceGateError
    from sqlalchemy import select

    entity_id = uuid.uuid4()
    fact_text = f"Integration test fact {uuid.uuid4()}"

    create = SemanticFactStagingCreate(
        entity_id=entity_id,
        fact_text=fact_text,
        source_invocation_id=uuid.uuid4(),
    )

    # Proposal 1 → staging, evidence_count=1
    staging_1 = await repo.stage_fact(create)
    assert staging_1.evidence_count == 1

    # Proposal 2 → evidence_count=2
    staging_2 = await repo.increment_evidence(
        staging_id=staging_1.staging_id,
        source_invocation_id=uuid.uuid4(),
    )
    assert staging_2.evidence_count == 2

    # Verify commit_fact raises when evidence_count=2 (< 3)
    with pytest.raises(EvidenceGateError):
        await repo.commit_fact(
            staging_id=staging_1.staging_id, embedding=[0.0] * 1536
        )

    # Proposal 3 → evidence_count=3
    staging_3 = await repo.increment_evidence(
        staging_id=staging_1.staging_id,
        source_invocation_id=uuid.uuid4(),
    )
    assert staging_3.evidence_count == 3

    # Now commit should succeed
    committed = await repo.commit_fact(
        staging_id=staging_1.staging_id, embedding=[0.1] * 1536
    )
    assert committed.evidence_count == 3
    assert committed.decayed_at is None

    # Staging row should be removed
    result = await pg_session.execute(
        select(StagingORM).where(StagingORM.staging_id == staging_1.staging_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_decay_pass_marks_old_facts_excluded_from_query(repo, hygiene, pg_session):
    """
    AC-003: run_decay_pass marks old facts as decayed; excluded from query.
    """
    from src.ai.memory.models.semantic_models import SemanticFact as SemanticFactORM

    entity_id = uuid.uuid4()
    fact_text = f"Decay test fact {uuid.uuid4()}"

    # Stage and commit (shortcut: insert directly with evidence_count=3)
    staging = await repo.stage_fact(
        SemanticFactStagingCreate(
            entity_id=entity_id,
            fact_text=fact_text,
            source_invocation_id=uuid.uuid4(),
        )
    )
    # increment to 3
    await repo.increment_evidence(staging.staging_id, uuid.uuid4())
    await repo.increment_evidence(staging.staging_id, uuid.uuid4())
    committed = await repo.commit_fact(
        staging_id=staging.staging_id, embedding=[0.2] * 1536
    )

    # Backdate last_confirmed to 7 months ago
    seven_months_ago = datetime.now(tz=timezone.utc) - timedelta(days=210)
    await pg_session.execute(
        update(SemanticFactORM)
        .where(SemanticFactORM.fact_id == committed.fact_id)
        .values(last_confirmed=seven_months_ago)
    )
    await pg_session.flush()

    # Run decay pass
    result = await hygiene.run_decay_pass()
    assert result.facts_decayed >= 1

    # Fact should no longer appear with exclude_decayed=True
    results_filtered = await repo.query_facts(
        embedding=[0.2] * 1536, exclude_decayed=True
    )
    fact_ids_filtered = [f.fact_id for f in results_filtered]
    assert committed.fact_id not in fact_ids_filtered

    # But fact DOES appear with exclude_decayed=False
    results_all = await repo.query_facts(
        embedding=[0.2] * 1536, exclude_decayed=False
    )
    fact_ids_all = [f.fact_id for f in results_all]
    assert committed.fact_id in fact_ids_all
