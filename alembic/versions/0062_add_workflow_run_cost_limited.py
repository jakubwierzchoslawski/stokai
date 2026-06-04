"""Add cost_limited column to workflow_run table.

Revision: 0062
Revises: 0061
Create Date: 2026-06-04

PLAN-N-004 TASK-001

Changes:
  1. Adds cost_limited BOOLEAN NOT NULL DEFAULT FALSE to workflow_run.
     Set to TRUE by the cost_exceeded_node when a workflow is terminated
     mid-execution due to WorkflowBudgetExceededError.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_run",
        sa.Column(
            "cost_limited",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )


def downgrade() -> None:
    op.drop_column("workflow_run", "cost_limited")
