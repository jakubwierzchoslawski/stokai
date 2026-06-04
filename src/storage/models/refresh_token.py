"""
storage.models.refresh_token — SQLAlchemy ORM model for the refresh_token table.

Mirrors the schema created by migration 0002_create_refresh_token_table.
Server-side token revocation: tokens are hashed (bcrypt) and stored here.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class RefreshToken(Base):
    """ORM model for the `refresh_token` table.

    Enables server-side revocation. The raw token is never stored —
    only a bcrypt hash is persisted.
    """

    __tablename__ = "refresh_token"
    __table_args__ = (
        Index("ix_refresh_token_user_id", "user_id"),
        Index("ix_refresh_token_tenant_id", "tenant_id"),
    )

    token_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"RefreshToken(token_id={self.token_id!r}, user_id={self.user_id!r}, "
            f"revoked_at={self.revoked_at!r})"
        )
