"""
Integration tests for the Layer 1 episodic memory flow (TASK-018).

These tests require a real PostgreSQL instance. Run with:
  pytest tests/integration/memory/test_episodic_flow.py -m integration

The test DB URL is taken from the DATABASE_URL environment variable (or .env).

NOTE: The append-only trigger tests (UPDATE/DELETE blocked) are tested here because
they require a real PostgreSQL environment — SQLite does not support them.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.ai.memory.interfaces.i_memory_service import WorkflowContext
from src.ai.memory.models.base import MemoryBase
from src.ai.memory.models.episodic_models import (
    WorkflowRun as WorkflowRunORM,
)
from src.ai.memory.repositories.episodic_repository import EpisodicRepository
from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocationCreate,
    ToolCallCreate,
    WorkflowRunCreate,
)

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def pg_engine():
    """PostgreSQL engine for integration tests."""
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
    """Auto-rollback session for test isolation."""
    async with pg_engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
        await conn.rollback()


@pytest_asyncio.fixture
async def repo(pg_session):
    return EpisodicRepository(pg_session)


@pytest_asyncio.fixture
async def tenant_id():
    return uuid.uuid4()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_episodic_flow_record_and_retrieve(repo, tenant_id):
    """
    AC-001: workflow_run → agent_invocation → tool_call → all rows exist.
    """
    # record_workflow_start
    run_create = WorkflowRunCreate(
        workflow_type="mode_b_analysis", tenant_id=tenant_id
    )
    workflow_run = await repo.append_workflow_run(run_create)
    assert workflow_run.workflow_id is not None

    # record_agent_invocation
    inv_create = AgentInvocationCreate(
        workflow_id=workflow_run.workflow_id,
        agent_role_id="relevance-analyst",
        model_used="claude-haiku-4-5",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.005,
    )
    inv = await repo.append_agent_invocation(inv_create)
    assert inv.workflow_id == workflow_run.workflow_id

    # record_tool_call
    call_create = ToolCallCreate(
        invocation_id=inv.invocation_id,
        tool_name="fetch_price_data",
        arguments={"ticker": "AAPL"},
        duration_ms=80,
    )
    tool_call = await repo.append_tool_call(call_create)
    assert tool_call.invocation_id == inv.invocation_id

    # list_recent_runs
    recent = await repo.list_recent_runs(tenant_id=tenant_id, limit=10)
    assert any(r.workflow_id == workflow_run.workflow_id for r in recent)


@pytest.mark.asyncio
async def test_db_trigger_blocks_delete_on_workflow_run(repo, pg_session, tenant_id):
    """
    AC-001: DB-level trigger must raise on DELETE of workflow_run.
    """
    from sqlalchemy import delete

    run_create = WorkflowRunCreate(
        workflow_type="mode_a_pipeline", tenant_id=tenant_id
    )
    workflow_run = await repo.append_workflow_run(run_create)

    with pytest.raises(DBAPIError):
        await pg_session.execute(
            delete(WorkflowRunORM).where(
                WorkflowRunORM.workflow_id == workflow_run.workflow_id
            )
        )
        await pg_session.flush()


@pytest.mark.asyncio
async def test_db_trigger_blocks_update_on_workflow_run(repo, pg_session, tenant_id):
    """
    AC-001: DB-level trigger must raise on UPDATE of workflow_run immutable columns.
    """
    from sqlalchemy import update

    run_create = WorkflowRunCreate(
        workflow_type="mode_b_analysis", tenant_id=tenant_id
    )
    workflow_run = await repo.append_workflow_run(run_create)

    with pytest.raises(DBAPIError):
        await pg_session.execute(
            update(WorkflowRunORM)
            .where(WorkflowRunORM.workflow_id == workflow_run.workflow_id)
            .values(workflow_type="tampered")
        )
        await pg_session.flush()
