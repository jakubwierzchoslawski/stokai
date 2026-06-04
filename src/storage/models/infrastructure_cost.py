"""
storage.models.infrastructure_cost — SQLAlchemy ORM model for the infrastructure_cost table.

Mirrors the schema created by migration 0065_create_infrastructure_cost.
Introduced by PLAN-N-005 TASK-001.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class InfraCostCategory(str, enum.Enum):
    """Infrastructure cost category values — stored as VARCHAR(32), not a DB enum.

    Using str enum avoids migration complexity when new categories are added.
    """

    HOSTING = "hosting"           # compute: VM, container service
    DATABASE = "database"         # managed PostgreSQL / TimescaleDB
    REDIS = "redis"               # managed Redis
    OBSERVABILITY = "observability"  # Langfuse infra (ClickHouse + Langfuse DB)
    STORAGE = "storage"           # blob / object storage
    NETWORKING = "networking"     # egress, load balancer
    OTHER = "other"


class InfrastructureCost(Base):
    """ORM model for the ``infrastructure_cost`` table.

    Columns:
      cost_id        UUID PRIMARY KEY DEFAULT gen_random_uuid()
      tenant_id      UUID NULLABLE (single-tenant MVP; NULL = global record)
      billing_month  DATE NOT NULL  (first day of month, e.g. 2026-06-01)
      category       VARCHAR(32) NOT NULL  (InfraCostCategory enum value)
      description    TEXT NOT NULL  (free-text label, e.g. "Azure Container Apps – api")
      cost_usd       NUMERIC(10,4) NOT NULL CHECK (cost_usd >= 0)
      recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
      recorded_by    UUID NOT NULL  (user_id of the admin who entered the record)

    Index: ix_infrastructure_cost_billing_month_tenant_id (billing_month, tenant_id)
    """

    __tablename__ = "infrastructure_cost"
    __table_args__ = (
        sa.CheckConstraint("cost_usd >= 0", name="chk_infra_cost_usd_non_negative"),
        Index("ix_infrastructure_cost_billing_month_tenant_id", "billing_month", "tenant_id"),
    )

    cost_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    billing_month: Mapped[date] = mapped_column(
        Date(),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 4),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"InfrastructureCost(cost_id={self.cost_id!r}, "
            f"billing_month={self.billing_month!r}, "
            f"category={self.category!r}, "
            f"cost_usd={self.cost_usd!r})"
        )
