"""
Unit tests for QARepository (PLAN-F-027 TASK-001).

Uses mock AsyncSession to avoid PostgreSQL dependency.
Tests cover: create_session, get_session (tenant guard), append_message (FK),
get_messages (ordered), and invalid role DB constraint.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.storage.repositories.qa_repository import (
    QAMessage,
    QARepository,
    QASession,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_session_orm(tenant_id, user_id, session_id):
    """Mock ORM object returned after insert / query."""
    orm = MagicMock()
    orm.session_id = session_id
    orm.user_id = user_id
    orm.tenant_id = tenant_id
    orm.workflow_run_id = None
    orm.created_at = datetime.now(tz=timezone.utc)
    orm.updated_at = datetime.now(tz=timezone.utc)
    return orm


@pytest.fixture
def mock_message_orm(tenant_id, session_id):
    """Mock ORM object for a qa_message row."""
    orm = MagicMock()
    orm.message_id = uuid.uuid4()
    orm.session_id = session_id
    orm.tenant_id = tenant_id
    orm.role = "user"
    orm.content = "What is my AAPL exposure?"
    orm.sources = None
    orm.confidence = None
    orm.cost_usd = None
    orm.cost_limited = False
    orm.created_at = datetime.now(tz=timezone.utc)
    return orm


# ── TASK-001 Tests ─────────────────────────────────────────────────────────────


class TestQARepositoryCreateSession:
    """create_session persists all fields and returns domain schema."""

    @pytest.mark.asyncio
    async def test_create_session_persists_all_fields(
        self, tenant_id, user_id, session_id, mock_session_orm
    ):
        """create_session inserts a row with all fields and returns QASession."""
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        # Simulate ORM refresh populating the orm object
        async def fake_refresh(orm):
            orm.session_id = session_id
            orm.user_id = user_id
            orm.tenant_id = tenant_id
            orm.workflow_run_id = None
            orm.created_at = mock_session_orm.created_at
            orm.updated_at = mock_session_orm.updated_at

        db.refresh.side_effect = fake_refresh

        repo = QARepository(db)
        qa_session = QASession(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        result = await repo.create_session(qa_session)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert result.user_id == user_id
        assert result.tenant_id == tenant_id
        assert result.session_id == session_id

    @pytest.mark.asyncio
    async def test_create_session_with_workflow_run_id(
        self, tenant_id, user_id, session_id
    ):
        """create_session persists optional workflow_run_id."""
        run_id = uuid.uuid4()
        db = AsyncMock()
        db.flush = AsyncMock()

        async def fake_refresh(orm):
            orm.session_id = session_id
            orm.user_id = user_id
            orm.tenant_id = tenant_id
            orm.workflow_run_id = run_id
            orm.created_at = datetime.now(tz=timezone.utc)
            orm.updated_at = datetime.now(tz=timezone.utc)

        db.refresh.side_effect = fake_refresh

        repo = QARepository(db)
        qa_session = QASession(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            workflow_run_id=run_id,
        )
        result = await repo.create_session(qa_session)
        assert result.workflow_run_id == run_id


class TestQARepositoryGetSession:
    """get_session enforces tenant_id and user_id (IDOR prevention)."""

    @pytest.mark.asyncio
    async def test_get_session_returns_session_for_correct_tenant(
        self, tenant_id, user_id, session_id, mock_session_orm
    ):
        """get_session returns session when tenant_id and user_id match."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_orm
        db.execute = AsyncMock(return_value=mock_result)

        repo = QARepository(db)
        result = await repo.get_session(session_id, user_id, tenant_id)

        assert result is not None
        assert result.session_id == session_id
        assert result.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_get_session_wrong_tenant_returns_none(
        self, tenant_id, user_id, session_id
    ):
        """get_session returns None when tenant_id does not match (IDOR guard)."""
        wrong_tenant = uuid.uuid4()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # DB returns no row
        db.execute = AsyncMock(return_value=mock_result)

        repo = QARepository(db)
        result = await repo.get_session(session_id, user_id, wrong_tenant)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_wrong_user_returns_none(
        self, tenant_id, user_id, session_id
    ):
        """get_session returns None when user_id does not match."""
        wrong_user = uuid.uuid4()
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = QARepository(db)
        result = await repo.get_session(session_id, wrong_user, tenant_id)

        assert result is None


class TestQARepositoryAppendMessage:
    """append_message links to session via FK and returns persisted message."""

    @pytest.mark.asyncio
    async def test_append_message_links_to_session(
        self, tenant_id, session_id, mock_message_orm
    ):
        """append_message inserts with correct session_id FK."""
        db = AsyncMock()
        db.flush = AsyncMock()

        async def fake_refresh(orm):
            orm.message_id = mock_message_orm.message_id
            orm.session_id = session_id
            orm.tenant_id = tenant_id
            orm.role = "user"
            orm.content = "What is my AAPL exposure?"
            orm.sources = None
            orm.confidence = None
            orm.cost_usd = None
            orm.cost_limited = False
            orm.created_at = mock_message_orm.created_at

        db.refresh.side_effect = fake_refresh

        repo = QARepository(db)
        msg = QAMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="user",
            content="What is my AAPL exposure?",
        )
        result = await repo.append_message(msg)

        db.add.assert_called_once()
        db.flush.assert_called_once()
        assert result.session_id == session_id
        assert result.role == "user"
        assert result.content == "What is my AAPL exposure?"

    @pytest.mark.asyncio
    async def test_append_assistant_message_with_sources_and_confidence(
        self, tenant_id, session_id
    ):
        """append_message persists sources, confidence, cost_usd for assistant."""
        db = AsyncMock()
        db.flush = AsyncMock()
        msg_id = uuid.uuid4()
        sources = [{"type": "event", "id": "evt-1", "description": "AAPL Q1 2026"}]

        async def fake_refresh(orm):
            orm.message_id = msg_id
            orm.session_id = session_id
            orm.tenant_id = tenant_id
            orm.role = "assistant"
            orm.content = "Your AAPL exposure is 15%."
            orm.sources = sources
            orm.confidence = 0.87
            orm.cost_usd = 0.05
            orm.cost_limited = False
            orm.created_at = datetime.now(tz=timezone.utc)

        db.refresh.side_effect = fake_refresh

        repo = QARepository(db)
        msg = QAMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="assistant",
            content="Your AAPL exposure is 15%.",
            sources=sources,
            confidence=0.87,
            cost_usd=0.05,
        )
        result = await repo.append_message(msg)

        assert result.role == "assistant"
        assert result.confidence == 0.87
        assert result.sources == sources
        assert result.cost_usd == 0.05


class TestQARepositoryGetMessages:
    """get_messages returns messages ordered by created_at ASC."""

    @pytest.mark.asyncio
    async def test_get_messages_ordered_by_created_at(
        self, tenant_id, session_id
    ):
        """get_messages returns rows ordered created_at ascending."""
        t1 = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 4, 10, 1, tzinfo=timezone.utc)

        def make_orm_msg(role, content, created_at):
            orm = MagicMock()
            orm.message_id = uuid.uuid4()
            orm.session_id = session_id
            orm.tenant_id = tenant_id
            orm.role = role
            orm.content = content
            orm.sources = None
            orm.confidence = None
            orm.cost_usd = None
            orm.cost_limited = False
            orm.created_at = created_at
            return orm

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            make_orm_msg("user", "Q1", t1),
            make_orm_msg("assistant", "A1", t2),
        ]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        repo = QARepository(db)
        results = await repo.get_messages(session_id, tenant_id)

        assert len(results) == 2
        assert results[0].role == "user"
        assert results[1].role == "assistant"
        assert results[0].created_at <= results[1].created_at

    @pytest.mark.asyncio
    async def test_get_messages_empty_session(self, tenant_id, session_id):
        """get_messages returns empty list for session with no messages."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        repo = QARepository(db)
        results = await repo.get_messages(session_id, tenant_id)

        assert results == []


class TestQARepositoryInvalidRole:
    """Invalid role raises DB-level constraint (simulated via ValueError)."""

    def test_qa_message_domain_schema_accepts_valid_roles(self, tenant_id, session_id):
        """QAMessage domain schema can be created with role='user' or 'assistant'."""
        user_msg = QAMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="user",
            content="Hello",
        )
        asst_msg = QAMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="assistant",
            content="Hi",
        )
        assert user_msg.role == "user"
        assert asst_msg.role == "assistant"

    @pytest.mark.asyncio
    async def test_append_message_invalid_role_propagates_db_error(
        self, tenant_id, session_id
    ):
        """append_message with invalid role → DB raises IntegrityError (simulated)."""
        from sqlalchemy.exc import IntegrityError

        db = AsyncMock()
        db.flush = AsyncMock(
            side_effect=IntegrityError(
                "CHECK constraint failed: ck_qa_message_role", params={}, orig=None
            )
        )

        repo = QARepository(db)
        msg = QAMessage(
            session_id=session_id,
            tenant_id=tenant_id,
            role="invalid_role",  # violates CHECK constraint
            content="Bad message",
        )
        with pytest.raises(IntegrityError):
            await repo.append_message(msg)
