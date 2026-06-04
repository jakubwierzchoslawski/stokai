"""Alembic migration: geo-modifier performance index.

Adds a partial index on company_score to accelerate geo-modifier read pattern:
  SELECT ... WHERE company_id = ANY(:ids) AND indicator_id = :id
  ORDER BY computed_at DESC

The index covers rows where geo_adjusted IS NOT NULL, which is the exact
filter used by bulk_update_geo_adjusted in the geo-modifier worker.

No new tables are introduced. company_score.geo_adjusted already exists
from 017_scoring_engine.

Revision ID: 018_geo_modifier
Revises: 017_scoring_engine
Branch labels: None
Depends on: None

PLAN-F-018 TASK-008
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision = "018_geo_modifier"
down_revision = "017_scoring_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add partial index to accelerate geo-modifier score lookups."""
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_score_geo_lookup
        ON company_score (indicator_id, company_id, computed_at DESC)
        WHERE geo_adjusted IS NOT NULL;
        """
    )


def downgrade() -> None:
    """Drop the geo-modifier lookup index."""
    op.execute(
        """
        DROP INDEX CONCURRENTLY IF EXISTS idx_company_score_geo_lookup;
        """
    )
