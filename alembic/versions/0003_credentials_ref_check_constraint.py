"""Add CHECK constraint on source_config.credentials_ref

Revision ID: 0003_credentials_ref_check_constraint
Revises: (none — standalone constraint migration)
Create Date: 2026-06-03

Purpose
-------
Add a PostgreSQL CHECK constraint to source_config.credentials_ref that
rejects any value not matching the pattern ^(env|vault):[A-Z0-9_]+$.

This is a defence-in-depth measure: the ORM-level @validates already blocks
raw API keys, but this DB constraint prevents any code path that bypasses
the ORM (bulk inserts, raw SQL, migration data patches) from storing them.

Conditional execution
---------------------
If the source_config table does not yet exist (PLAN-F-028 not yet applied to
this environment), the migration skips gracefully — it will be re-applied once
the table exists.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "0003_credentials_ref_check"
down_revision = None  # standalone; set to the actual preceding revision in your chain
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "ck_source_config_credentials_ref_prefix"
_TABLE_NAME = "source_config"
_CONSTRAINT_EXPR = r"credentials_ref ~ '^(env|vault):[A-Z0-9_]+$'"


def upgrade() -> None:
    """Add CHECK constraint if source_config table exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Skip gracefully if the table does not exist yet (PLAN-F-028 not applied)
    if _TABLE_NAME not in inspector.get_table_names():
        return

    # Skip if constraint already present (idempotent)
    existing_constraints = [
        c["name"] for c in inspector.get_check_constraints(_TABLE_NAME)
    ]
    if _CONSTRAINT_NAME in existing_constraints:
        return

    op.create_check_constraint(
        _CONSTRAINT_NAME,
        _TABLE_NAME,
        _CONSTRAINT_EXPR,
    )


def downgrade() -> None:
    """Drop CHECK constraint if it exists and the table is present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _TABLE_NAME not in inspector.get_table_names():
        return

    existing_constraints = [
        c["name"] for c in inspector.get_check_constraints(_TABLE_NAME)
    ]
    if _CONSTRAINT_NAME not in existing_constraints:
        return

    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="check")
