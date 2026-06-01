"""Integration tests for ConcreteScoreRepository (PLAN-F-003 TASK-009).

These tests require a live PostgreSQL test database.
Run with: pytest tests/integration/scoring/ -m integration -v

All tests are marked @pytest.mark.integration and are skipped when no test
DB is configured.

AC-005: Score record includes indicator_version_id, inputs_hash, computed_at.
AC-006: Tool Library read tool returns at most 50 rows, is tenant-scoped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.scoring.interfaces import ScoreQuery, ScoreResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_score_result(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None = None,
    indicator_id: uuid.UUID | None = None,
    score: float = 1.0,
    inputs_hash: str = "abc123",
) -> ScoreResult:
    return ScoreResult(
        score_id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        indicator_id=indicator_id or uuid.uuid4(),
        indicator_version_id=uuid.uuid4(),
        score=score,
        geo_weight_applied=1.0,
        inputs_hash=inputs_hash,
        computed_at=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


@pytest.fixture
def repository(db_session: AsyncSession):
    """Provide a ConcreteScoreRepository backed by the test DB session."""
    from src.scoring.repository import ConcreteScoreRepository
    return ConcreteScoreRepository(session=db_session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_append_inserts_new_row(db_session, test_tenant, repository):
    """After append, get_latest returns the record."""
    tenant_id = test_tenant.id
    result = _make_score_result(tenant_id=tenant_id)
    await repository.append(result)

    query = ScoreQuery(tenant_id=tenant_id, limit=10)
    rows = await repository.get_latest(query)
    assert len(rows) >= 1
    assert any(r.score_id == result.score_id for r in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_append_is_immutable(db_session, test_tenant, repository):
    """Calling append twice with same company/indicator creates two rows (no upsert)."""
    tenant_id = test_tenant.id
    company_id = uuid.uuid4()
    indicator_id = uuid.uuid4()

    r1 = _make_score_result(tenant_id=tenant_id, company_id=company_id,
                             indicator_id=indicator_id, score=1.0, inputs_hash="hash_v1")
    r2 = _make_score_result(tenant_id=tenant_id, company_id=company_id,
                             indicator_id=indicator_id, score=2.0, inputs_hash="hash_v2")

    await repository.append(r1)
    await repository.append(r2)

    query = ScoreQuery(tenant_id=tenant_id, company_ids=[company_id],
                       indicator_id=indicator_id, limit=50)
    rows = await repository.get_latest(query)
    assert len(rows) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_latest_respects_50_row_cap(db_session, test_tenant, repository):
    """Insert 60 records; get_latest returns at most 50."""
    tenant_id = test_tenant.id
    indicator_id = uuid.uuid4()

    for i in range(60):
        r = _make_score_result(
            tenant_id=tenant_id,
            indicator_id=indicator_id,
            score=float(i),
            inputs_hash=f"hash_{i}",
        )
        await repository.append(r)

    query = ScoreQuery(tenant_id=tenant_id, indicator_id=indicator_id, limit=60)
    rows = await repository.get_latest(query)
    assert len(rows) <= 50


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_latest_is_tenant_scoped(db_session, test_tenant, other_tenant, repository):
    """Records from tenant A are not returned for tenant B."""
    from src.scoring.repository import ConcreteScoreRepository

    repo_a = ConcreteScoreRepository(session=db_session)
    repo_b = ConcreteScoreRepository(session=db_session)

    indicator_id = uuid.uuid4()
    r_a = _make_score_result(tenant_id=test_tenant.id, indicator_id=indicator_id)
    await repo_a.append(r_a)

    query_b = ScoreQuery(tenant_id=other_tenant.id, indicator_id=indicator_id, limit=50)
    rows = await repo_b.get_latest(query_b)
    assert all(r.tenant_id == other_tenant.id for r in rows)
    assert not any(r.score_id == r_a.score_id for r in rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_stored_hash_returns_none_for_new_company(db_session, test_tenant, repository):
    """No prior record → get_stored_hash returns None."""
    result = await repository.get_stored_hash(
        company_id=uuid.uuid4(),
        indicator_id=uuid.uuid4(),
        tenant_id=test_tenant.id,
    )
    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_stored_hash_returns_most_recent_hash(db_session, test_tenant, repository):
    """After two appends, returns hash from the latest row."""
    tenant_id = test_tenant.id
    company_id = uuid.uuid4()
    indicator_id = uuid.uuid4()

    r1 = _make_score_result(tenant_id=tenant_id, company_id=company_id,
                             indicator_id=indicator_id, inputs_hash="hash_first")
    r2 = _make_score_result(tenant_id=tenant_id, company_id=company_id,
                             indicator_id=indicator_id, inputs_hash="hash_second")

    await repository.append(r1)
    await repository.append(r2)

    stored = await repository.get_stored_hash(
        company_id=company_id,
        indicator_id=indicator_id,
        tenant_id=tenant_id,
    )
    assert stored == "hash_second"
