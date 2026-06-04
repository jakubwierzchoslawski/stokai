"""Acceptance tests — semantic fact 6-month decay (PLAN-N-011 TASK-005).

Verifies AC-001: facts unconfirmed for >= 6 months are marked decayed by
SemanticHygieneService.run_decay_pass(); subsequent queries with
exclude_decayed=True exclude them; rows are NOT deleted.

Requires a real PostgreSQL instance with pgvector enabled.
Run with:
    pytest tests/integration/memory/test_semantic_decay_acceptance.py -m integration

The test_db fixture creates the schema via Alembic and rolls back after each test.
Falls back to the test_semantic_flow pattern (manual rollback via session) when
Alembic is not configured — compatible with the existing CI setup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.ai.memory.models.semantic_models import SemanticFact as SemanticFactORM
from src.ai.memory.repositories.semantic_repository import SemanticRepository
from src.ai.memory.schemas.semantic_schemas import SemanticFactStagingCreate
from src.ai.memory.services.semantic_hygiene_service import (
    SEMANTIC_DECAY_MONTHS,
    SemanticHygieneService,
)

pytestmark = pytest.mark.integration

# Zero-vector used as a placeholder for embeddings in all test data.
ZERO_VECTOR: list[float] = [0.0] * 1536


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """Create an async SQLAlchemy engine from environment DATABASE_URL."""
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
    """Provide a session that rolls back after each test (no Alembic needed)."""
    async with pg_engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def repo(pg_session) -> SemanticRepository:
    return SemanticRepository(pg_session)


@pytest_asyncio.fixture
async def hygiene(repo) -> SemanticHygieneService:
    return SemanticHygieneService(semantic_repo=repo)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _commit_fact(repo: SemanticRepository, session: AsyncSession) -> "SemanticFact":  # noqa: F821
    """Stage + increment x2 + commit a semantic fact with evidence_count=3."""
    entity_id = uuid.uuid4()
    fact_text = f"Acceptance test fact {uuid.uuid4()}"
    staging = await repo.stage_fact(
        SemanticFactStagingCreate(
            entity_id=entity_id,
            fact_text=fact_text,
            source_invocation_id=uuid.uuid4(),
        )
    )
    await repo.increment_evidence(staging.staging_id, uuid.uuid4())
    await repo.increment_evidence(staging.staging_id, uuid.uuid4())
    committed = await repo.commit_fact(staging_id=staging.staging_id, embedding=ZERO_VECTOR)
    return committed


async def _backdate_fact(
    session: AsyncSession, fact_id: uuid.UUID, months: int
) -> None:
    """Back-date last_confirmed by the given number of months."""
    backdated = datetime.now(tz=timezone.utc) - timedelta(days=30 * months)
    await session.execute(
        update(SemanticFactORM)
        .where(SemanticFactORM.fact_id == fact_id)
        .values(last_confirmed=backdated)
    )
    await session.flush()


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fact_unconfirmed_7_months_is_marked_decayed(
    repo, hygiene, pg_session
) -> None:
    """AC-001: A fact last confirmed 7 months ago must be marked decayed."""
    fact = await _commit_fact(repo, pg_session)
    await _backdate_fact(pg_session, fact.fact_id, months=7)

    result = await hygiene.run_decay_pass()
    assert result.facts_decayed >= 1

    # Reload the fact row and confirm decayed_at is set.
    row = await pg_session.execute(
        select(SemanticFactORM).where(SemanticFactORM.fact_id == fact.fact_id)
    )
    orm_fact = row.scalar_one()
    assert orm_fact.decayed_at is not None, "decayed_at must be set after decay pass"


@pytest.mark.asyncio
async def test_fact_unconfirmed_5_months_is_not_decayed(
    repo, hygiene, pg_session
) -> None:
    """A fact confirmed 5 months ago (< 6 month threshold) must NOT be decayed."""
    fact = await _commit_fact(repo, pg_session)
    await _backdate_fact(pg_session, fact.fact_id, months=5)

    await hygiene.run_decay_pass()

    row = await pg_session.execute(
        select(SemanticFactORM).where(SemanticFactORM.fact_id == fact.fact_id)
    )
    orm_fact = row.scalar_one()
    assert orm_fact.decayed_at is None, "decayed_at must be NULL for 5-month-old fact"


@pytest.mark.asyncio
async def test_decayed_fact_excluded_from_tool_query_results(
    repo, hygiene, pg_session
) -> None:
    """Decayed fact must be excluded from query_facts(exclude_decayed=True)."""
    fact = await _commit_fact(repo, pg_session)
    await _backdate_fact(pg_session, fact.fact_id, months=7)
    await hygiene.run_decay_pass()

    results = await repo.query_facts(embedding=ZERO_VECTOR, exclude_decayed=True)
    result_ids = [f.fact_id for f in results]
    assert fact.fact_id not in result_ids, (
        "Decayed fact must be excluded when exclude_decayed=True"
    )


@pytest.mark.asyncio
async def test_decayed_fact_accessible_when_exclusion_disabled(
    repo, hygiene, pg_session
) -> None:
    """Decayed fact must be returned when query_facts(exclude_decayed=False)."""
    fact = await _commit_fact(repo, pg_session)
    await _backdate_fact(pg_session, fact.fact_id, months=7)
    await hygiene.run_decay_pass()

    results = await repo.query_facts(embedding=ZERO_VECTOR, exclude_decayed=False)
    result_ids = [f.fact_id for f in results]
    assert fact.fact_id in result_ids, (
        "Decayed fact must be accessible when exclude_decayed=False"
    )


@pytest.mark.asyncio
async def test_decay_does_not_delete_fact(
    repo, hygiene, pg_session
) -> None:
    """After decay, the semantic_fact row must still exist (soft-delete only)."""
    fact = await _commit_fact(repo, pg_session)
    await _backdate_fact(pg_session, fact.fact_id, months=7)
    await hygiene.run_decay_pass()

    row = await pg_session.execute(
        select(SemanticFactORM).where(SemanticFactORM.fact_id == fact.fact_id)
    )
    orm_fact = row.scalar_one_or_none()
    assert orm_fact is not None, "Row must still exist after decay (no deletion)"
    assert orm_fact.fact_text is not None, "fact_text must be preserved"


@pytest.mark.asyncio
async def test_decay_pass_returns_correct_count(
    repo, hygiene, pg_session
) -> None:
    """DecayPassResult.facts_decayed must equal the number of facts older than 6 months."""
    # Insert 3 old facts (>6 months) and 2 recent ones (<6 months).
    old_ids: list[uuid.UUID] = []
    for _ in range(3):
        fact = await _commit_fact(repo, pg_session)
        await _backdate_fact(pg_session, fact.fact_id, months=8)
        old_ids.append(fact.fact_id)

    for _ in range(2):
        # Recent facts — last_confirmed = now (within threshold)
        await _commit_fact(repo, pg_session)

    result = await hygiene.run_decay_pass()
    assert result.facts_decayed == 3, (
        f"Expected 3 facts decayed, got {result.facts_decayed}"
    )

    # Verify the 3 old facts are decayed.
    for fact_id in old_ids:
        row = await pg_session.execute(
            select(SemanticFactORM).where(SemanticFactORM.fact_id == fact_id)
        )
        orm_fact = row.scalar_one()
        assert orm_fact.decayed_at is not None, f"fact {fact_id} must be decayed"
