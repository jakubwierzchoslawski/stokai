"""Alembic migration: scoring engine tables.

Creates:
  - indicator (formula storage, versioning)
  - indicator_version (historical DSL snapshots)
  - company_score (TimescaleDB hypertable, D4 snapshot pattern)
  - scoring_profile (built-in and custom scoring profiles)
  - dsl_parameter (parameter catalog)

Revision ID: 017_scoring_engine
Revises: 016 (assumed prior migration)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "017_scoring_engine"
down_revision = None  # Update to previous migration revision ID
branch_labels = ("legacy",)
depends_on = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # Assert TimescaleDB extension is enabled before creating hypertable
    # -----------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
            ) THEN
                RAISE EXCEPTION 'TimescaleDB extension must be enabled before running this migration';
            END IF;
        END $$;
        """
    )

    # -----------------------------------------------------------------------
    # indicator table
    # -----------------------------------------------------------------------
    op.create_table(
        "indicator",
        sa.Column("indicator_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("formula_dsl", sa.Text, nullable=False),
        sa.Column("normalization_mode", sa.String(50), nullable=False, server_default="percentile"),
        sa.Column("normalization_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("direction", sa.String(20), nullable=False, server_default="higher_better"),
        sa.Column("geo_weight", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_indicator_tenant_id", "indicator", ["tenant_id"])
    op.create_index(
        "ix_indicator_tenant_indicator",
        "indicator",
        ["tenant_id", "indicator_id"],
    )
    op.create_unique_constraint(
        "uq_indicator_id_version",
        "indicator",
        ["indicator_id", "version"],
    )

    # -----------------------------------------------------------------------
    # indicator_version table (historical DSL snapshots)
    # -----------------------------------------------------------------------
    op.create_table(
        "indicator_version",
        sa.Column("version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "indicator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("indicator.indicator_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("formula_dsl", sa.Text, nullable=False),
        sa.Column("diff_tokens", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_indicator_version_indicator_id", "indicator_version", ["indicator_id"])
    op.create_index(
        "ix_indicator_version_indicator_version",
        "indicator_version",
        ["indicator_id", "version"],
    )

    # -----------------------------------------------------------------------
    # company_score — TimescaleDB hypertable (D4 snapshot pattern)
    # -----------------------------------------------------------------------
    op.create_table(
        "company_score",
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("indicator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_value", sa.Float, nullable=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("percentile", sa.Float, nullable=True),
        sa.Column("geo_adjusted", sa.Float, nullable=True),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("company_id", "indicator_id", "computed_at"),
    )
    op.create_index("ix_company_score_company_id", "company_score", ["company_id"])
    op.create_index("ix_company_score_indicator_id", "company_score", ["indicator_id"])
    op.create_index(
        "ix_company_score_company_indicator",
        "company_score",
        ["company_id", "indicator_id", "computed_at"],
    )

    # Convert to TimescaleDB hypertable (partitioned on computed_at)
    op.execute(
        "SELECT create_hypertable('company_score', 'computed_at', if_not_exists => TRUE)"
    )

    # 2-year data retention policy
    op.execute(
        "SELECT add_retention_policy('company_score', INTERVAL '2 years', if_not_exists => TRUE)"
    )

    # -----------------------------------------------------------------------
    # scoring_profile table
    # -----------------------------------------------------------------------
    op.create_table(
        "scoring_profile",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "indicators",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment='[{indicator_id, weight}]',
        ),
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_scoring_profile_tenant_id", "scoring_profile", ["tenant_id"])

    # -----------------------------------------------------------------------
    # dsl_parameter table (parameter catalog)
    # -----------------------------------------------------------------------
    op.create_table(
        "dsl_parameter",
        sa.Column("parameter_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_field", sa.String(200), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_dsl_parameter_tenant_id", "dsl_parameter", ["tenant_id"])
    op.create_unique_constraint(
        "uq_dsl_parameter_tenant_name",
        "dsl_parameter",
        ["tenant_id", "name"],
    )


def downgrade() -> None:
    op.drop_table("dsl_parameter")
    op.drop_table("scoring_profile")

    # Remove TimescaleDB policies before dropping table
    op.execute(
        "SELECT remove_retention_policy('company_score', if_exists => TRUE)"
    )
    op.drop_table("company_score")
    op.drop_table("indicator_version")
    op.drop_table("indicator")
