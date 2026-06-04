"""
Create qa_session and qa_message tables for PLAN-F-027 Q&A Chat Interface.

Revision: 0060
Revises: 0056 (prompt_publication / earnings)
Create Date: 2026-06-04

PLAN-F-027 TASK-001

Changes:
  1. Creates qa_session table (user+tenant scoped Q&A sessions).
  2. Creates qa_message table (append-only conversation messages).
  3. Creates indexes on tenant+user and session+created_at.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMPTZ

# revision identifiers, used by Alembic.
revision = "0060"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create qa_session table ────────────────────────────────────────────
    op.create_table(
        "qa_session",
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_qa_session_tenant_user",
        "qa_session",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "idx_qa_session_tenant",
        "qa_session",
        ["tenant_id", "session_id"],
    )

    # ── 2. Create qa_message table ────────────────────────────────────────────
    op.create_table(
        "qa_message",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("qa_session.session_id"),
            nullable=False,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", JSONB, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column(
            "cost_limited",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            TIMESTAMPTZ,
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_qa_message_role"),
    )

    op.create_index(
        "idx_qa_message_session",
        "qa_message",
        ["session_id", "created_at"],
    )
    op.create_index(
        "idx_qa_message_tenant",
        "qa_message",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_qa_message_tenant", table_name="qa_message")
    op.drop_index("idx_qa_message_session", table_name="qa_message")
    op.drop_table("qa_message")

    op.drop_index("idx_qa_session_tenant", table_name="qa_session")
    op.drop_index("idx_qa_session_tenant_user", table_name="qa_session")
    op.drop_table("qa_session")
