"""
SQLAlchemy 2.0 ORM model for the golden_dataset_item table.

Stores curated examples used by Tier-2 regression runs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.ai.evaluation.models.base import EvaluationBase


class GoldenDatasetItem(EvaluationBase):
    """ORM model for golden_dataset_item table.

    Computed properties
    -------------------
    is_active : bool
        True when active=True (item is in production regression suite).
    is_candidate : bool
        True when active=False and approved_at is None (pending human review).
    """

    __tablename__ = "golden_dataset_item"

    item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid4,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality_metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
    )
    approved_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMPTZ,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        nullable=False,
        server_default=text("NOW()"),
    )

    @property
    def is_active(self) -> bool:
        """True when the item is in the active regression suite."""
        return self.active is True

    @property
    def is_candidate(self) -> bool:
        """True when the item is pending approval (not yet active, not rejected)."""
        return self.active is False and self.approved_at is None
