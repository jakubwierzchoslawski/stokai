"""
storage.models.cost_record — SQLAlchemy ORM model for the cost_record table.

Mirrors the schema created by migration 0057_add_system_ops_tables.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class CostRecord(Base):
    """ORM model for the ``cost_record`` table."""

    __tablename__ = "cost_record"
    __table_args__ = (
        Index("ix_cost_record_tenant_date", "tenant_id", "date"),
    )

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    date: Mapped[date] = mapped_column(Date(), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    workflow_type: Mapped[str | None] = mapped_column(String, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"CostRecord(record_id={self.record_id!r}, "
            f"tenant_id={self.tenant_id!r}, date={self.date!r}, "
            f"cost_usd={self.cost_usd!r})"
        )
