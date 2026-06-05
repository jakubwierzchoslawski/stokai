"""
storage.models.prompt_publication — SQLAlchemy 2.0 ORM model for the prompt_publication table.

PLAN-F-014 TASK-003 (AC-003).

Stores prompt label assignments (production/staging/canary/experimental) with full
audit trail. The UNIQUE (role_id, label) constraint ensures only one active version
per label per role at any time.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = DateTime(timezone=True)  # type: ignore[misc,assignment]


class PromptBase(DeclarativeBase):
    """Declarative base for prompt management ORM models."""


class PromptPublication(PromptBase):
    """ORM model for the prompt_publication table.

    Each row represents the assignment of a label (production/staging/canary/experimental)
    to a specific prompt version (identified by git blob SHA). The UNIQUE constraint on
    (role_id, label) means an upsert is required when moving a label to a new version.

    Columns:
        pub_id: Primary key UUID.
        role_id: Prompt role identifier (e.g. "exposure_analyst").
        version_sha: 40-char git blob SHA or hashlib fallback.
        label: One of production|staging|canary|experimental.
        langfuse_version_id: Optional Langfuse version identifier.
        published_by: UUID of the user or service account that published.
        published_at: Timestamp of the publication event.
    """

    __tablename__ = "prompt_publication"
    __table_args__ = (
        UniqueConstraint("role_id", "label", name="uq_prompt_publication_role_label"),
        CheckConstraint(
            "label IN ('production','staging','canary','experimental')",
            name="ck_prompt_publication_label",
        ),
    )

    pub_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    role_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    langfuse_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False)

    def __repr__(self) -> str:
        return (
            f"PromptPublication(role_id={self.role_id!r}, label={self.label!r}, "
            f"version_sha={self.version_sha[:8]!r}...)"
        )
