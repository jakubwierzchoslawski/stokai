"""portfolio and watchlist tables

Revision ID: 0052_portfolio_watchlist
Revises:
Create Date: 2026-06-04 00:00:00.000000

Tables created:
  - portfolio
  - position
  - watchlist_item
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0052"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── portfolio ──────────────────────────────────────────────────────────────
    op.create_table(
        "portfolio",
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_portfolio_tenant_user",
        "portfolio",
        ["tenant_id", "user_id"],
    )

    # ── company (universe table) ──────────────────────────────────────────────
    op.create_table(
        "company",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_tracked", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("sector_gics", sa.Text(), nullable=True),
    )
    op.create_index("ix_company_ticker", "company", ["ticker"], unique=True)

    # ── position ───────────────────────────────────────────────────────────────
    op.create_table(
        "position",
        sa.Column(
            "position_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolio.portfolio_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company.company_id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("shares", sa.Float, nullable=False),
        sa.Column("cost_basis", sa.Float, nullable=True),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "source",
            sa.String(20),
            sa.CheckConstraint(
                "source IN ('manual', 'csv', 'broker')",
                name="ck_position_source",
            ),
            nullable=False,
        ),
        sa.UniqueConstraint("portfolio_id", "company_id", name="uq_position_portfolio_company"),
    )
    op.create_index(
        "ix_position_portfolio_id",
        "position",
        ["portfolio_id"],
    )

    # ── watchlist_item ─────────────────────────────────────────────────────────
    op.create_table(
        "watchlist_item",
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company.company_id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "company_id", name="uq_watchlist_tenant_user_company"
        ),
    )
    op.create_index(
        "ix_watchlist_tenant_user",
        "watchlist_item",
        ["tenant_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_table("watchlist_item")
    op.drop_table("position")
    op.drop_table("portfolio")
