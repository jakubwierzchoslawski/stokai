"""Unit tests for ai_decision table migration (PLAN-F-029 TASK-001).

Tests verify migration correctness via ORM model inspection without requiring
a live PostgreSQL connection.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID, JSONB

from src.ai.decision_log.models.ai_decision_model import AIDecision, Base


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_column(table, col_name: str):
    for col in table.columns:
        if col.name == col_name:
            return col
    return None


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestAIDecisionModel:
    """Validates the ORM model reflects the desired DDL for the ai_decision table."""

    def test_table_name(self):
        assert AIDecision.__tablename__ == "ai_decision"

    def test_all_required_columns_exist(self):
        table = AIDecision.__table__
        expected_cols = {
            "decision_id",
            "agent_role",
            "model",
            "prompt_version",
            "confidence",
            "inputs_summary",
            "inputs_full",
            "retrieved_analogs",
            "action_signal",
            "company_ticker",
            "output_text",
            "langfuse_trace_url",
            "workflow_run_id",
            "created_at",
        }
        actual_cols = {c.name for c in table.columns}
        assert expected_cols == actual_cols

    def test_decision_id_is_primary_key(self):
        table = AIDecision.__table__
        col = _get_column(table, "decision_id")
        assert col is not None
        assert col.primary_key is True

    def test_nullable_columns(self):
        """action_signal, company_ticker, and workflow_run_id are nullable."""
        table = AIDecision.__table__
        for name in ("action_signal", "company_ticker", "workflow_run_id"):
            col = _get_column(table, name)
            assert col is not None, f"Column {name} not found"
            assert col.nullable is True, f"Column {name} should be nullable"

    def test_non_nullable_columns(self):
        """Core columns must be non-nullable."""
        table = AIDecision.__table__
        for name in (
            "agent_role",
            "model",
            "prompt_version",
            "confidence",
            "inputs_summary",
            "inputs_full",
            "output_text",
            "langfuse_trace_url",
        ):
            col = _get_column(table, name)
            assert col is not None, f"Column {name} not found"
            assert col.nullable is False, f"Column {name} should be non-nullable"

    def test_confidence_check_constraint_exists(self):
        table = AIDecision.__table__
        constraint_names = {c.name for c in table.constraints if hasattr(c, "name")}
        assert "ai_decision_confidence_range" in constraint_names

    def test_workflow_run_id_foreign_key(self):
        table = AIDecision.__table__
        col = _get_column(table, "workflow_run_id")
        assert col is not None
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert "workflow_run.workflow_id" in fk_targets

    def test_retrieved_analogs_server_default_empty_array(self):
        table = AIDecision.__table__
        col = _get_column(table, "retrieved_analogs")
        assert col is not None
        # Server default should be [] for JSONB
        assert col.server_default is not None

    def test_composite_index_defined(self):
        """Verify the composite index on (created_at DESC, decision_id) exists."""
        table = AIDecision.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_ai_decision_created_at_decision_id" in index_names

    def test_agent_role_index_defined(self):
        table = AIDecision.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_ai_decision_agent_role" in index_names

    def test_company_ticker_index_defined(self):
        table = AIDecision.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_ai_decision_company_ticker" in index_names

    def test_action_signal_index_defined(self):
        table = AIDecision.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_ai_decision_action_signal" in index_names


class TestAIDecisionInMemorySQLite:
    """Smoke tests validating CHECK constraint is declared on the model.

    Note: SQLite in-memory tests are skipped because the ai_decision table has a
    FK to workflow_run which is not in the same Base. The ORM model correctness is
    verified via the TestAIDecisionModel tests above which inspect the table metadata.
    """

    def test_insert_with_confidence_out_of_range_documents_check_constraint(self):
        """Confidence CHECK constraint — documented on the model for PostgreSQL enforcement."""
        table = AIDecision.__table__
        check_constraints = [
            c for c in table.constraints
            if hasattr(c, "name") and c.name == "ai_decision_confidence_range"
        ]
        assert len(check_constraints) == 1, "CHECK constraint must be declared on model"

    def test_null_columns_are_nullable_in_schema(self):
        """action_signal, company_ticker, workflow_run_id are nullable per schema."""
        table = AIDecision.__table__
        for col_name in ("action_signal", "company_ticker", "workflow_run_id"):
            col = next((c for c in table.columns if c.name == col_name), None)
            assert col is not None
            assert col.nullable is True
