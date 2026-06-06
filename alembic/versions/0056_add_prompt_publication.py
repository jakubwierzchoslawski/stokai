"""Add prompt_publication table for label-based prompt versioning

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import DateTime

try:
    from sqlalchemy.dialects.postgresql import TIMESTAMPTZ
except ImportError:
    TIMESTAMPTZ = lambda: DateTime(timezone=True)  # type: ignore[misc,assignment]

revision = "0056_prompt_publication"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_publication",
        sa.Column(
            "pub_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("role_id", sa.Text(), nullable=False),
        sa.Column("version_sha", sa.String(40), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("langfuse_version_id", sa.Text(), nullable=True),
        sa.Column("published_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "published_at",
            TIMESTAMPTZ(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "role_id", "label", name="uq_prompt_publication_role_label"
        ),
        sa.CheckConstraint(
            "label IN ('production','staging','canary','experimental')",
            name="ck_prompt_publication_label",
        ),
    )
    op.create_index(
        "ix_prompt_publication_role_id",
        "prompt_publication",
        ["role_id"],
    )
    op.create_index(
        "ix_prompt_publication_published_at",
        "prompt_publication",
        ["published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_publication_published_at", table_name="prompt_publication")
    op.drop_index("ix_prompt_publication_role_id", table_name="prompt_publication")
    op.drop_table("prompt_publication")
