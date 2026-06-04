"""add source_config and market_source_binding tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-03 00:00:00.000000

Migration for PLAN-F-028: Admin Data Source Management plane.

Creates:
  - source_config table: stores provider configuration with credentials_ref
    (vault-reference only — raw secrets never stored). All rows default to
    enabled=false. Seeded social stub sources are inserted with enabled=false
    (architecture decision D8: Twitter/X off by default).
  - market_source_binding table: maps markets to data-source providers with
    role=primary|fallback. Composite PK prevents duplicate bindings.

Rollback: drops market_source_binding first (FK dependency), then source_config.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None

# ── Social stub seed rows ──────────────────────────────────────────────────────
# Inserted via INSERT...ON CONFLICT DO NOTHING so re-running upgrade is safe.
# All are seeded with enabled=false (architecture decision D8).
_SOCIAL_SEEDS = [
    {
        "source_id": str(uuid.UUID("a1000000-0000-0000-0000-000000000001")),
        "interface_type": "SocialProvider",
        "display_name": "StockTwits",
        "enabled": False,
        "credentials_ref": "env:STOCKTWITS_API_KEY",
        "config": "{}",
        "cost_tier": "free",
        "priority": 0,
    },
    {
        "source_id": str(uuid.UUID("a1000000-0000-0000-0000-000000000002")),
        "interface_type": "SocialProvider",
        "display_name": "Reddit",
        "enabled": False,
        "credentials_ref": "env:REDDIT_CLIENT_ID",
        "config": "{}",
        "cost_tier": "free",
        "priority": 0,
    },
    {
        "source_id": str(uuid.UUID("a1000000-0000-0000-0000-000000000003")),
        "interface_type": "SocialProvider",
        "display_name": "Telegram",
        "enabled": False,
        "credentials_ref": "env:TELEGRAM_BOT_TOKEN",
        "config": "{}",
        "cost_tier": "free",
        "priority": 0,
    },
    {
        "source_id": str(uuid.UUID("a1000000-0000-0000-0000-000000000004")),
        "interface_type": "SocialProvider",
        "display_name": "Truth Social",
        "enabled": False,
        "credentials_ref": "env:TRUTH_SOCIAL_API_KEY",
        "config": "{}",
        "cost_tier": "free",
        "priority": 0,
    },
    {
        "source_id": str(uuid.UUID("a1000000-0000-0000-0000-000000000005")),
        "interface_type": "SocialProvider",
        "display_name": "Twitter/X",
        "enabled": False,  # D8: off by default — explicit admin action required
        "credentials_ref": "env:TWITTER_API_KEY",
        "config": "{}",
        "cost_tier": "medium",
        "priority": 0,
    },
]


def upgrade() -> None:
    # ── source_config ──────────────────────────────────────────────────────────
    op.create_table(
        "source_config",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("interface_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("credentials_ref", sa.Text(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("cost_tier", sa.String(20), nullable=False),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # credentials_ref: only env: or vault: prefixes accepted — raw keys blocked
        sa.CheckConstraint(
            r"credentials_ref ~ '^(env|vault):[A-Z0-9_]+$'",
            name="ck_source_config_credentials_ref",
        ),
    )
    op.create_index("ix_source_config_interface_type", "source_config", ["interface_type"])
    op.create_index("ix_source_config_enabled", "source_config", ["enabled"])

    # ── market_source_binding ──────────────────────────────────────────────────
    op.create_table(
        "market_source_binding",
        sa.Column(
            "market_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("interface_type", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("source_config.source_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "role IN ('primary', 'fallback')",
            name="ck_market_source_binding_role",
        ),
    )
    op.create_index(
        "ix_msb_market_interface",
        "market_source_binding",
        ["market_id", "interface_type"],
    )
    op.create_index("ix_msb_source_id", "market_source_binding", ["source_id"])

    # ── Seed social stub sources (INSERT...ON CONFLICT DO NOTHING) ─────────────
    conn = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()
    for row in _SOCIAL_SEEDS:
        conn.execute(
            sa.text(
                """
                INSERT INTO source_config
                    (source_id, interface_type, display_name, enabled,
                     credentials_ref, config, cost_tier, priority, updated_at)
                VALUES
                    (:source_id, :interface_type, :display_name, :enabled,
                     :credentials_ref, :config::jsonb, :cost_tier, :priority, :updated_at)
                ON CONFLICT (source_id) DO NOTHING
                """
            ),
            {**row, "updated_at": now},
        )


def downgrade() -> None:
    # Drop binding table first (FK dependency on source_config)
    op.drop_index("ix_msb_source_id", table_name="market_source_binding")
    op.drop_index("ix_msb_market_interface", table_name="market_source_binding")
    op.drop_table("market_source_binding")

    op.drop_index("ix_source_config_enabled", table_name="source_config")
    op.drop_index("ix_source_config_interface_type", table_name="source_config")
    op.drop_table("source_config")
