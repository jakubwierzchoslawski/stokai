"""
0001_create_user_table

Creates user_role enum type and the user table.

Revision ID: 0001
Revises: None
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(72), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "operator", "end_user", name="user_role"),
            nullable=False,
        ),
        sa.Column(
            "settings",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("scoring_profile_default", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "dispatch_time",
            sa.Time(),
            nullable=False,
            server_default=sa.text("'06:00'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", "tenant_id", name="uq_user_email_tenant"),
    )

    op.create_index("ix_user_tenant_id", "user", ["tenant_id"])
    op.create_index("ix_user_email", "user", ["email"])


def downgrade() -> None:
    op.drop_index("ix_user_email", table_name="user")
    op.drop_index("ix_user_tenant_id", table_name="user")
    op.drop_table("user")

    user_role_enum = sa.Enum(
        "admin", "operator", "end_user",
        name="user_role",
    )
    user_role_enum.drop(op.get_bind(), checkfirst=True)
