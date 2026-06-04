"""
storage.models.ingestion_job — SQLAlchemy ORM model for the ingestion_job table.

Mirrors the schema created by migration 0057_add_system_ops_tables.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class IngestionJobStatus(str, enum.Enum):
    idle = "idle"
    running = "running"
    failed = "failed"


class IngestionJob(Base):
    """ORM model for the ``ingestion_job`` table."""

    __tablename__ = "ingestion_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('idle', 'running', 'failed')",
            name="ck_ingestion_job_status",
        ),
        Index("ix_ingestion_job_tenant_status", "tenant_id", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    schedule: Mapped[str] = mapped_column(String, nullable=False)  # cron expression
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=text("'idle'"),
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    last_error_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"IngestionJob(job_id={self.job_id!r}, name={self.name!r}, status={self.status!r})"
