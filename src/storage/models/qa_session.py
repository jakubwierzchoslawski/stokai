"""
storage.models.qa_session — SQLAlchemy 2.0 ORM models for Q&A session tables.

PLAN-F-027 TASK-001

Tables:
  qa_session  — one row per Q&A session (user + tenant scoped)
  qa_message  — append-only conversation messages (user/assistant roles)

Multi-tenancy: every lookup MUST include tenant_id in the WHERE clause.
IDOR prevention is enforced at the repository layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class QABase(DeclarativeBase):
    """Declarative base for Q&A ORM models."""


class QASession(QABase):
    """
    ORM model for the qa_session table.

    Each row represents a Q&A conversation session tied to a user and tenant.
    The optional workflow_run_id FK links to the episodic memory layer.

    Multi-tenancy: all queries MUST scope on tenant_id.
    """

    __tablename__ = "qa_session"
    __table_args__ = (
        Index("idx_qa_session_tenant_user", "tenant_id", "user_id"),
        Index("idx_qa_session_tenant", "tenant_id", "session_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )

    def __repr__(self) -> str:
        return (
            f"QASession(session_id={self.session_id!r}, "
            f"user_id={self.user_id!r}, tenant_id={self.tenant_id!r})"
        )


class QAMessage(QABase):
    """
    ORM model for the qa_message table.

    Append-only: no DELETE triggers enforced at DB level.
    role must be 'user' or 'assistant' (CHECK constraint).
    sources is JSONB — list of QASource-shaped objects.
    """

    __tablename__ = "qa_message"
    __table_args__ = (
        Index("idx_qa_message_session", "session_id", "created_at"),
        Index("idx_qa_message_tenant", "tenant_id"),
    )

    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("qa_session.session_id"),
        nullable=False,
    )
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_limited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=text("NOW()")
    )

    def __repr__(self) -> str:
        return (
            f"QAMessage(message_id={self.message_id!r}, "
            f"session_id={self.session_id!r}, role={self.role!r})"
        )
