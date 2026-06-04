"""
Integration tests for TASK-001: Layer 1 episodic DB migration.

These tests verify:
- Migration 0033 applies cleanly and all four tables exist.
- INSERT into workflow_run succeeds.
- UPDATE on workflow_run raises a DB-level exception.
- DELETE on agent_invocation raises a DB-level exception.

Tests run against a real PostgreSQL instance. Requires:
  - DATABASE_URL env var pointing to a test database.
  - alembic configured (alembic.ini in project root).
"""
from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text


@pytest.fixture(scope="module")
def sync_engine():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set; skipping Layer 1 migration integration test")
    # Use synchronous engine for DDL/trigger tests
    sync_url = url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url, echo=False)
    yield engine
    engine.dispose()


def test_tables_exist(sync_engine):
    """All four Layer 1 tables must exist after migration."""
    expected_tables = {
        "workflow_run",
        "agent_invocation",
        "tool_call",
        "recommendation_outcome",
    }
    with sync_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name = ANY(:names)"
            ),
            {"names": list(expected_tables)},
        )
        found = {row[0] for row in result}
    assert expected_tables == found, f"Missing tables: {expected_tables - found}"


def test_insert_workflow_run_succeeds(sync_engine):
    """INSERT into workflow_run must succeed."""
    wf_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_run "
                "(workflow_id, workflow_type, tenant_id) "
                "VALUES (:wid, :wtype, :tid)"
            ),
            {"wid": str(wf_id), "wtype": "mode_b_test", "tid": str(tenant_id)},
        )
        # Clean up — using direct delete at DB level for test isolation
        # (We cannot use normal DELETE via the trigger, so we temporarily disable)
        conn.execute(
            text(
                "ALTER TABLE workflow_run DISABLE TRIGGER trg_workflow_run_append_only"
            )
        )
        conn.execute(
            text("DELETE FROM workflow_run WHERE workflow_id = :wid"),
            {"wid": str(wf_id)},
        )
        conn.execute(
            text(
                "ALTER TABLE workflow_run ENABLE TRIGGER trg_workflow_run_append_only"
            )
        )


def test_update_workflow_run_blocked(sync_engine):
    """UPDATE on workflow_run must raise a DB-level exception (trigger)."""
    wf_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_run "
                "(workflow_id, workflow_type, tenant_id) "
                "VALUES (:wid, :wtype, :tid)"
            ),
            {"wid": str(wf_id), "wtype": "mode_b_test", "tid": str(tenant_id)},
        )

    with pytest.raises(Exception, match="append-only|restrict_violation|Updates are not allowed"):
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE workflow_run SET workflow_type = 'hacked' "
                    "WHERE workflow_id = :wid"
                ),
                {"wid": str(wf_id)},
            )

    # Clean up
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE workflow_run DISABLE TRIGGER trg_workflow_run_append_only"
            )
        )
        conn.execute(
            text("DELETE FROM workflow_run WHERE workflow_id = :wid"),
            {"wid": str(wf_id)},
        )
        conn.execute(
            text(
                "ALTER TABLE workflow_run ENABLE TRIGGER trg_workflow_run_append_only"
            )
        )


def test_delete_agent_invocation_blocked(sync_engine):
    """DELETE on agent_invocation must raise a DB-level exception (trigger)."""
    wf_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    tenant_id = uuid.uuid4()

    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workflow_run "
                "(workflow_id, workflow_type, tenant_id) "
                "VALUES (:wid, :wtype, :tid)"
            ),
            {"wid": str(wf_id), "wtype": "mode_b_test", "tid": str(tenant_id)},
        )
        conn.execute(
            text(
                "INSERT INTO agent_invocation "
                "(invocation_id, workflow_id, agent_role_id) "
                "VALUES (:iid, :wid, :role)"
            ),
            {"iid": str(inv_id), "wid": str(wf_id), "role": "test-agent"},
        )

    with pytest.raises(Exception, match="append-only|restrict_violation|Deletes are not allowed"):
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM agent_invocation WHERE invocation_id = :iid"
                ),
                {"iid": str(inv_id)},
            )

    # Clean up
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE agent_invocation DISABLE TRIGGER trg_agent_invocation_append_only"
            )
        )
        conn.execute(
            text("DELETE FROM agent_invocation WHERE invocation_id = :iid"),
            {"iid": str(inv_id)},
        )
        conn.execute(
            text(
                "ALTER TABLE agent_invocation ENABLE TRIGGER trg_agent_invocation_append_only"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE workflow_run DISABLE TRIGGER trg_workflow_run_append_only"
            )
        )
        conn.execute(
            text("DELETE FROM workflow_run WHERE workflow_id = :wid"),
            {"wid": str(wf_id)},
        )
        conn.execute(
            text(
                "ALTER TABLE workflow_run ENABLE TRIGGER trg_workflow_run_append_only"
            )
        )
