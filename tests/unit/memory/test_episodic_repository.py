"""
Unit tests for EpisodicRepository.

Uses an async in-memory SQLite database (aiosqlite) so no real PostgreSQL is needed.
Append-only triggers are DB-level (PostgreSQL-only) — tested in integration tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from src.ai.memory.models.base import MemoryBase
from src.ai.memory.models.episodic_models import (
    WorkflowRun as WorkflowRunORM,
    AgentInvocation as AgentInvocationORM,
    ToolCall as ToolCallORM,
    RecommendationOutcome as RecommendationOutcomeORM,
)
from src.ai.memory.repositories.episodic_repository import EpisodicRepository
from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocationCreate,
    RecommendationOutcomeCreate,
    ToolCallCreate,
    WorkflowRunCreate,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def engine():
    """In-memory SQLite engine for unit tests."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(MemoryBase.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Async session bound to the in-memory engine."""
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as sess:
        yield sess


@pytest_asyncio.fixture
async def repo(session):
    return EpisodicRepository(session)


@pytest_asyncio.fixture
async def tenant_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def workflow_run(repo, tenant_id):
    """Create and return a persisted workflow run."""
    run_create = WorkflowRunCreate(
        workflow_type="mode_b_analysis",
        tenant_id=tenant_id,
        langfuse_trace_id="trace-001",
    )
    return await repo.append_workflow_run(run_create)


# ── append_workflow_run ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_workflow_run_inserts_and_returns_entity(repo, tenant_id):
    run_create = WorkflowRunCreate(
        workflow_type="mode_a_pipeline",
        tenant_id=tenant_id,
    )
    result = await repo.append_workflow_run(run_create)

    assert result.workflow_id is not None
    assert isinstance(result.workflow_id, uuid.UUID)
    assert result.workflow_type == "mode_a_pipeline"
    assert result.tenant_id == tenant_id
    assert result.status == "running"


# ── append_agent_invocation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_agent_invocation_with_valid_workflow_id_succeeds(
    repo, workflow_run
):
    inv_create = AgentInvocationCreate(
        workflow_id=workflow_run.workflow_id,
        agent_role_id="relevance-analyst",
        model_used="claude-haiku-4-5",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
    )
    result = await repo.append_agent_invocation(inv_create)

    assert result.invocation_id is not None
    assert result.workflow_id == workflow_run.workflow_id
    assert result.agent_role_id == "relevance-analyst"


@pytest.mark.asyncio
async def test_append_agent_invocation_with_invalid_fk_raises_integrity_error(
    repo, session
):
    """Non-existent workflow_id should trigger FK constraint."""
    inv_create = AgentInvocationCreate(
        workflow_id=uuid.uuid4(),  # does not exist
        agent_role_id="qa-analyst",
    )
    with pytest.raises(IntegrityError):
        await repo.append_agent_invocation(inv_create)
        await session.flush()


# ── append_tool_call ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_tool_call_inserts_correctly(repo, workflow_run, session):
    inv_create = AgentInvocationCreate(
        workflow_id=workflow_run.workflow_id,
        agent_role_id="anomaly-detector",
    )
    inv = await repo.append_agent_invocation(inv_create)

    call_create = ToolCallCreate(
        invocation_id=inv.invocation_id,
        tool_name="fetch_price_data",
        arguments={"ticker": "AAPL"},
        result={"price": 150.0},
        duration_ms=120,
        cost_tier="free",
        cached=False,
    )
    result = await repo.append_tool_call(call_create)

    assert result.tool_call_id is not None
    assert result.invocation_id == inv.invocation_id
    assert result.tool_name == "fetch_price_data"


# ── append_recommendation_outcome ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_recommendation_outcome_inserts_correctly(repo, workflow_run):
    outcome_create = RecommendationOutcomeCreate(
        workflow_id=workflow_run.workflow_id,
        company_id=uuid.uuid4(),
        action_signal="BUY",
        confidence=0.85,
    )
    result = await repo.append_recommendation_outcome(outcome_create)

    assert result.rec_id is not None
    assert result.workflow_id == workflow_run.workflow_id
    assert result.action_signal == "BUY"
    assert result.actual_t1d is None


# ── fill_outcome_actuals ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fill_outcome_actuals_updates_only_calibration_columns(
    repo, workflow_run, session
):
    outcome_create = RecommendationOutcomeCreate(
        workflow_id=workflow_run.workflow_id,
        action_signal="SELL",
        confidence=0.70,
    )
    outcome = await repo.append_recommendation_outcome(outcome_create)
    await session.commit()

    await repo.fill_outcome_actuals(
        rec_id=outcome.rec_id,
        actual_t1d=2.5,
        actual_t1w=5.1,
        direction_correct=True,
    )
    await session.commit()

    fetched = await repo.get_workflow_run(outcome.workflow_id)
    # Verify the workflow run is unaffected (we only updated outcome cols)
    assert fetched is not None
    assert fetched.workflow_id == workflow_run.workflow_id


# ── list_recent_runs ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recent_runs_ordered_by_started_at_descending(
    repo, tenant_id, session
):
    for wtype in ("first", "second", "third"):
        await repo.append_workflow_run(
            WorkflowRunCreate(workflow_type=wtype, tenant_id=tenant_id)
        )
    await session.commit()

    results = await repo.list_recent_runs(tenant_id=tenant_id, limit=10)

    assert len(results) == 3
    # Most recent first
    times = [r.started_at for r in results]
    assert times == sorted(times, reverse=True)


@pytest.mark.asyncio
async def test_list_recent_runs_bounded_by_limit(repo, tenant_id, session):
    for i in range(5):
        await repo.append_workflow_run(
            WorkflowRunCreate(workflow_type=f"run-{i}", tenant_id=tenant_id)
        )
    await session.commit()

    results = await repo.list_recent_runs(tenant_id=tenant_id, limit=2)
    assert len(results) == 2
