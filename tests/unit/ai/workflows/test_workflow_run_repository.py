"""
Unit tests for WorkflowRunRepository.

TDD: tests written to verify create/get/update_status/save_final_state behavior
including tenant isolation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType
from src.storage.models.workflow_run import WorkflowBase, WorkflowRun
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(WorkflowBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


def _make_state(
    tenant_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=tenant_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
    )


class TestWorkflowRunRepositoryCreateAndGet:
    @pytest.mark.asyncio
    async def test_workflow_run_repository_create_and_get(self, db_session):
        """Create a run and retrieve it by workflow_id + tenant_id."""
        state = _make_state()
        repo = WorkflowRunRepository(db_session)

        created = await repo.create(state)
        assert created.workflow_id == state.workflow_id
        assert created.status == "RUNNING"

        fetched = await repo.get(state.workflow_id, state.tenant_id)
        assert fetched is not None
        assert fetched.workflow_id == state.workflow_id
        assert fetched.tenant_id == state.tenant_id

    @pytest.mark.asyncio
    async def test_workflow_run_repository_get_wrong_tenant_returns_none(self, db_session):
        """get() with a different tenant_id must return None (IDOR prevention)."""
        state = _make_state()
        repo = WorkflowRunRepository(db_session)

        await repo.create(state)
        other_tenant = uuid.uuid4()
        result = await repo.get(state.workflow_id, other_tenant)
        assert result is None

    @pytest.mark.asyncio
    async def test_workflow_run_repository_get_unknown_id_returns_none(self, db_session):
        repo = WorkflowRunRepository(db_session)
        result = await repo.get(uuid.uuid4(), uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_workflow_run_repository_update_status(self, db_session):
        """update_status changes the status column."""
        state = _make_state()
        repo = WorkflowRunRepository(db_session)
        await repo.create(state)

        await repo.update_status(state.workflow_id, WorkflowStatus.COMPLETED)
        fetched = await repo.get(state.workflow_id, state.tenant_id)
        assert fetched is not None
        assert fetched.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_workflow_run_repository_save_final_state(self, db_session):
        """save_final_state persists the full WorkflowState as JSONB."""
        state = _make_state()
        repo = WorkflowRunRepository(db_session)
        await repo.create(state)

        final_state = state.model_copy(
            update={"status": WorkflowStatus.COMPLETED, "cost_usd": 0.42}
        )
        await repo.save_final_state(state.workflow_id, final_state)

        fetched = await repo.get(state.workflow_id, state.tenant_id)
        assert fetched is not None
        assert fetched.status == "COMPLETED"
        assert fetched.cost_usd == pytest.approx(0.42)
        assert fetched.final_state is not None


class TestWorkflowRunRepositorySaveTimeoutMock:
    """Mock-based tests for save_timeout() — PLAN-N-002 TASK-003.

    Uses mocked sessions because the SQLite in-memory DB does not support
    PostgreSQL-specific types (JSONB, TIMESTAMPTZ, UUID).
    """

    def _make_mock_session(self, rowcount: int = 1):
        from unittest.mock import AsyncMock, MagicMock

        mock_result = MagicMock()
        mock_result.rowcount = rowcount

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_save_timeout_sets_status_to_timeout(self):
        state = _make_state()
        session = self._make_mock_session(rowcount=1)
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        await repo.save_timeout(
            workflow_id=state.workflow_id,
            partial_state=state,
            timeout_at=timeout_at,
        )

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        compiled_params = stmt.compile().params
        assert compiled_params.get("status") == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_save_timeout_sets_partial_result_true(self):
        state = _make_state()
        session = self._make_mock_session(rowcount=1)
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        await repo.save_timeout(
            workflow_id=state.workflow_id,
            partial_state=state,
            timeout_at=timeout_at,
        )

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        compiled_params = stmt.compile().params
        assert compiled_params.get("partial_result") is True

    @pytest.mark.asyncio
    async def test_save_timeout_sets_timeout_at(self):
        state = _make_state()
        session = self._make_mock_session(rowcount=1)
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        await repo.save_timeout(
            workflow_id=state.workflow_id,
            partial_state=state,
            timeout_at=timeout_at,
        )

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        compiled_params = stmt.compile().params
        assert compiled_params.get("timeout_at") == timeout_at

    @pytest.mark.asyncio
    async def test_save_timeout_persists_final_state(self):
        state = _make_state()
        partial = state.model_copy(update={"cost_usd": 1.23, "tokens_consumed": {"input": 500}})
        session = self._make_mock_session(rowcount=1)
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        await repo.save_timeout(
            workflow_id=state.workflow_id,
            partial_state=partial,
            timeout_at=timeout_at,
        )

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        compiled_params = stmt.compile().params
        final_state = compiled_params.get("final_state")
        assert final_state is not None
        assert final_state["cost_usd"] == pytest.approx(1.23)
        assert final_state["tokens_consumed"]["input"] == 500

    @pytest.mark.asyncio
    async def test_save_timeout_scoped_to_tenant(self):
        """save_timeout UPDATE WHERE clause includes tenant_id."""
        state = _make_state()
        session = self._make_mock_session(rowcount=1)
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        await repo.save_timeout(
            workflow_id=state.workflow_id,
            partial_state=state,
            timeout_at=timeout_at,
        )

        call_args = session.execute.call_args
        stmt = call_args[0][0]
        where_str = str(stmt.whereclause.compile())
        assert "tenant_id" in where_str

    @pytest.mark.asyncio
    async def test_save_timeout_on_missing_workflow_run_raises(self):
        """Calling save_timeout with a non-existent workflow_id raises WorkflowRunNotFoundError."""
        from src.ai.workflows.errors import WorkflowRunNotFoundError

        state = _make_state()
        session = self._make_mock_session(rowcount=0)  # zero rows = not found
        repo = WorkflowRunRepository(session)
        timeout_at = datetime.now(tz=timezone.utc)

        with pytest.raises(WorkflowRunNotFoundError):
            await repo.save_timeout(
                workflow_id=state.workflow_id,
                partial_state=state,
                timeout_at=timeout_at,
            )
