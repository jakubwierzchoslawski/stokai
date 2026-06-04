"""
storage.repositories.qa_repository — QARepository implementing IQARepository.

PLAN-F-027 TASK-001

Provides create/get for QASession and append/list for QAMessage.
All queries are scoped by tenant_id to prevent IDOR leakage.
Messages are returned ordered by created_at ASC (conversation order).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models.qa_session import QAMessage as QAMessageORM
from src.storage.models.qa_session import QASession as QASessionORM


# ── Domain schemas ─────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field
from typing import Any


class QASession(BaseModel):
    """Domain schema for a Q&A session."""

    session_id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    tenant_id: UUID
    workflow_run_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QAMessage(BaseModel):
    """Domain schema for a Q&A conversation message."""

    message_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    tenant_id: UUID
    role: str  # 'user' | 'assistant'
    content: str
    sources: list[Any] | None = None
    confidence: float | None = None
    cost_usd: float | None = None
    cost_limited: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Repository protocol ────────────────────────────────────────────────────────


@runtime_checkable
class IQARepository(Protocol):
    """Repository contract for Q&A session persistence.

    All methods are tenant-scoped — every query includes tenant_id to prevent
    IDOR data leakage across tenants.
    """

    async def create_session(self, session: QASession) -> QASession:
        """Insert a new qa_session row and return it with generated IDs."""
        ...

    async def get_session(
        self, session_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> QASession | None:
        """Return QASession scoped to user_id+tenant_id, or None.

        Wrong tenant or wrong user → None (IDOR prevention).
        """
        ...

    async def append_message(self, message: QAMessage) -> QAMessage:
        """Insert a qa_message row and return it with generated IDs."""
        ...

    async def get_messages(
        self, session_id: UUID, tenant_id: UUID
    ) -> list[QAMessage]:
        """Return all messages for a session, ordered by created_at ASC."""
        ...


# ── SQLAlchemy implementation ──────────────────────────────────────────────────


class QARepository:
    """SQLAlchemy 2.0 async repository for qa_session and qa_message tables.

    Constructor-injected AsyncSession — no session creation inside methods (DIP).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(self, session: QASession) -> QASession:
        """INSERT a new qa_session row and return the persisted domain schema."""
        now = datetime.now(tz=timezone.utc)
        orm = QASessionORM(
            session_id=session.session_id,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            workflow_run_id=session.workflow_run_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return QASession.model_validate(orm)

    async def get_session(
        self, session_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> QASession | None:
        """Return QASession scoped to user_id+tenant_id, or None."""
        stmt = select(QASessionORM).where(
            QASessionORM.session_id == session_id,
            QASessionORM.user_id == user_id,
            QASessionORM.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return QASession.model_validate(orm)

    async def append_message(self, message: QAMessage) -> QAMessage:
        """INSERT a qa_message row and return the persisted domain schema."""
        orm = QAMessageORM(
            message_id=message.message_id,
            session_id=message.session_id,
            tenant_id=message.tenant_id,
            role=message.role,
            content=message.content,
            sources=message.sources,
            confidence=message.confidence,
            cost_usd=message.cost_usd,
            cost_limited=message.cost_limited,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._session.add(orm)
        await self._session.flush()
        await self._session.refresh(orm)
        return QAMessage.model_validate(orm)

    async def get_messages(
        self, session_id: UUID, tenant_id: UUID
    ) -> list[QAMessage]:
        """Return all messages for a session, ordered by created_at ASC."""
        stmt = (
            select(QAMessageORM)
            .where(
                QAMessageORM.session_id == session_id,
                QAMessageORM.tenant_id == tenant_id,
            )
            .order_by(QAMessageORM.created_at.asc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [QAMessage.model_validate(r) for r in rows]
