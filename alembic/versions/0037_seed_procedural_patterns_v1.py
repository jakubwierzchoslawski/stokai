"""Seed Layer 3 v1 procedural patterns — one per agent role, pre-approved

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-03 00:00:00.000000

"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_NOW = datetime.now(tz=timezone.utc).isoformat()


def upgrade() -> None:
    from src.ai.memory.fixtures.procedural_patterns_v1 import PROCEDURAL_PATTERNS_V1

    connection = op.get_bind()
    for pattern_def in PROCEDURAL_PATTERNS_V1:
        role = pattern_def["agent_role"]
        connection.execute(
            sa.text(
                """
                INSERT INTO procedural_pattern (
                    pattern_id, pattern_type, context_tags, pattern_text,
                    authored_by, approved_at, approved_by, version,
                    success_rate, sample_size, confidence,
                    recommended_for_agents, created_at, retracted_at
                )
                VALUES (
                    :pattern_id, :pattern_type, :context_tags, :pattern_text,
                    'human', :approved_at, NULL, 1,
                    NULL, NULL, NULL,
                    :recommended_for_agents, :created_at, NULL
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "pattern_id": str(uuid.uuid4()),
                "pattern_type": pattern_def["pattern_type"],
                # PostgreSQL array literal
                "context_tags": "{" + ",".join(pattern_def["context_tags"]) + "}",
                "pattern_text": pattern_def["pattern_text"],
                "approved_at": _NOW,
                "recommended_for_agents": "{" + role + "}",
                "created_at": _NOW,
            },
        )


def downgrade() -> None:
    from src.ai.memory.fixtures.procedural_patterns_v1 import PROCEDURAL_PATTERNS_V1

    connection = op.get_bind()
    for pattern_def in PROCEDURAL_PATTERNS_V1:
        role = pattern_def["agent_role"]
        connection.execute(
            sa.text(
                "DELETE FROM procedural_pattern WHERE pattern_text = :pattern_text"
            ),
            {"pattern_text": pattern_def["pattern_text"]},
        )
