"""Add system ops tables: ingestion_job, cost_record, feature_flag.

Revision: 0057
Revises: 0056
Create Date: 2026-06-04

PLAN-F-030 TASK-001

Changes:
  1. Creates ingestion_job table with status CHECK constraint.
  2. Creates cost_record table with tenant+date index.
  3. Creates feature_flag table with composite PK (flag_id, environment).
  4. Seeds default feature flags for all environments.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

_ENVIRONMENTS = ["local", "test", "staging", "production"]

# Flags enabled by default
_ENABLED_FLAGS = [
    "realtime_mode",
    "morning_brief",
    "watchlist_scan",
    "earnings_risk_brief",
    "event_deep_dive",
]

# Flags disabled by default (D8: social sources)
_DISABLED_FLAGS = [
    "social_twitter",
    "social_stocktwits",
    "social_reddit",
]


def upgrade() -> None:
    # ── 1. ingestion_job ──────────────────────────────────────────────────────
    op.create_table(
        "ingestion_job",
        sa.Column(
            "job_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("schedule", sa.Text(), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            sa.CheckConstraint(
                "status IN ('idle', 'running', 'failed')",
                name="ck_ingestion_job_status",
            ),
            nullable=False,
            server_default=sa.text("'idle'"),
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error_trace", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_ingestion_job_tenant_status",
        "ingestion_job",
        ["tenant_id", "status"],
    )

    # ── 2. cost_record ────────────────────────────────────────────────────────
    op.create_table(
        "cost_record",
        sa.Column(
            "record_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("workflow_type", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_cost_record_tenant_date",
        "cost_record",
        ["tenant_id", "date"],
    )

    # ── 3. feature_flag ───────────────────────────────────────────────────────
    op.create_table(
        "feature_flag",
        sa.Column("flag_id", sa.Text(), nullable=False),
        sa.Column("environment", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("user.user_id", name="fk_feature_flag_updated_by"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("flag_id", "environment", name="pk_feature_flag"),
    )

    # ── 4. Seed feature flags ─────────────────────────────────────────────────
    feature_flag_table = sa.table(
        "feature_flag",
        sa.column("flag_id", sa.Text()),
        sa.column("environment", sa.Text()),
        sa.column("enabled", sa.Boolean()),
    )

    rows = []
    for env in _ENVIRONMENTS:
        for flag in _ENABLED_FLAGS:
            rows.append({"flag_id": flag, "environment": env, "enabled": True})
        for flag in _DISABLED_FLAGS:
            rows.append({"flag_id": flag, "environment": env, "enabled": False})

    op.bulk_insert(feature_flag_table, rows)


def downgrade() -> None:
    op.drop_table("feature_flag")
    op.drop_index("ix_cost_record_tenant_date", table_name="cost_record")
    op.drop_table("cost_record")
    op.drop_index("ix_ingestion_job_tenant_status", table_name="ingestion_job")
    op.drop_table("ingestion_job")
