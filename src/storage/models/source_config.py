"""
storage.models.source_config — SQLAlchemy ORM model for the source_config table.

Stores provider configuration records for the admin data-source management plane
(PLAN-F-028). Credentials are never stored directly — only a vault-reference string
(credentials_ref) that is resolved at runtime by the credentials resolver.

All records are enabled=false by default; an admin must explicitly enable a source.
Twitter/X is seeded disabled by design (architecture decision D8).

The credentials_ref column stores only vault-reference strings matching the
pattern ``^(env|vault):[A-Z0-9_]+$``.  Raw API keys are rejected at the ORM
layer (@validates) and at the database layer (CHECK constraint in migration).
"""
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.storage.models.user import Base

# Regex enforced both at the ORM layer (via @validates) and at the database
# layer (via PostgreSQL CHECK constraint in migration).
CREDENTIALS_REF_PATTERN = re.compile(r"^(env|vault):[A-Z0-9_]+$")


class SourceConfig(Base):
    """ORM model for the ``source_config`` table.

    Stores configuration for external data providers. ``credentials_ref`` is a
    vault-reference string (e.g. ``env:FINNHUB_API_KEY``) resolved at runtime;
    the actual secret never reaches the database or application logs.

    All rows default to enabled=false. Seeded social sources (including Twitter/X)
    are inserted with enabled=false (architecture decision D8).

    Security:
        credentials_ref must match ``^(env|vault):[A-Z0-9_]+$``. Raw API keys
        are rejected by the ORM validator before any DB round-trip.
    """

    __tablename__ = "source_config"
    __table_args__ = (
        Index("ix_source_config_interface_type", "interface_type"),
        Index("ix_source_config_enabled", "enabled"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    interface_type: Mapped[str] = mapped_column(Text(), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    credentials_ref: Mapped[str] = mapped_column(Text(), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    cost_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @validates("credentials_ref")
    def validate_credentials_ref(self, key: str, value: str) -> str:
        """Enforce vault-reference format before any DB round-trip.

        Accepted formats:
            env:MY_VARIABLE   — references an environment variable name
            vault:MY_SECRET   — references a HashiCorp Vault secret path component

        Args:
            key: Column name (always "credentials_ref" — required by SQLAlchemy).
            value: The proposed credentials_ref string.

        Raises:
            ValueError: If the value does not match the required pattern.
        """
        if not value:
            raise ValueError(
                "credentials_ref must not be empty. "
                "Use 'env:MY_VAR' or 'vault:MY_SECRET' format."
            )
        if not CREDENTIALS_REF_PATTERN.match(value):
            raise ValueError(
                f"credentials_ref {value!r} is invalid. "
                "Only 'env:MY_VAR' or 'vault:MY_SECRET' formats are accepted. "
                "Raw API keys must never be stored in source_config."
            )
        return value

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SourceConfig(source_id={self.source_id!r}, "
            f"display_name={self.display_name!r}, "
            f"interface_type={self.interface_type!r}, "
            f"enabled={self.enabled!r})"
        )
