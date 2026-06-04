"""
storage.models.feature_flag — SQLAlchemy ORM model for the feature_flag table.

Mirrors the schema created by migration 0057_add_system_ops_tables.

Primary key: (flag_id, environment) composite — one row per flag per environment.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class FeatureFlag(Base):
    """ORM model for the ``feature_flag`` table."""

    __tablename__ = "feature_flag"
    __table_args__ = (
        PrimaryKeyConstraint("flag_id", "environment", name="pk_feature_flag"),
    )

    flag_id: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.user_id", name="fk_feature_flag_updated_by"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"FeatureFlag(flag_id={self.flag_id!r}, "
            f"environment={self.environment!r}, enabled={self.enabled!r})"
        )
