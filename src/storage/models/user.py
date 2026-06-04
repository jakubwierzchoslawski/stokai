"""
storage.models.user — SQLAlchemy ORM model for the user table.

Mirrors the schema created by migration 0001_create_user_table.
"""
import enum
import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import DateTime, Enum, Index, String, Text, Time, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class UserRole(str, enum.Enum):
    """User role enumeration — mapped to PostgreSQL user_role enum type."""

    admin = "admin"
    operator = "operator"
    end_user = "end_user"


class User(Base):
    """ORM model for the `user` table.

    Every row belongs to exactly one tenant (tenant_id is non-nullable).
    Passwords are stored as bcrypt hashes only — never plaintext.
    """

    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_user_email_tenant"),
        Index("ix_user_tenant_id", "tenant_id"),
        Index("ix_user_email", "email"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_type=False),
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    scoring_profile_default: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    dispatch_time: Mapped[time] = mapped_column(
        Time(),
        nullable=False,
        server_default=text("'06:00'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"User(user_id={self.user_id!r}, email={self.email!r}, role={self.role!r})"
