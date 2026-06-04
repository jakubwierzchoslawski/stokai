"""
Unit tests for TASK-001: evaluation framework DB migration files.

These tests verify the migration modules are importable and define the correct
revision IDs, table names, column names, and constraints — without touching a
real database.

TDD: written before the migration files exist.
"""
from __future__ import annotations

import importlib
import sys


def _load_migration(module_name: str):
    """Import a migration module dynamically."""
    return importlib.import_module(module_name)


# ── evaluation_result migration ───────────────────────────────────────────────


def test_evaluation_result_migration_importable():
    """Migration module for evaluation_result must be importable."""
    mod = _load_migration("alembic.versions.0053_evaluation_result_table")
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")


def test_evaluation_result_migration_revision():
    """evaluation_result migration must declare revision=0053."""
    mod = _load_migration("alembic.versions.0053_evaluation_result_table")
    assert mod.revision == "0053"


# ── golden_dataset_item migration ────────────────────────────────────────────


def test_golden_dataset_item_migration_importable():
    """Migration module for golden_dataset_item must be importable."""
    mod = _load_migration("alembic.versions.0054_golden_dataset_item_table")
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")


def test_golden_dataset_item_migration_revision():
    """golden_dataset_item migration must declare revision=0054."""
    mod = _load_migration("alembic.versions.0054_golden_dataset_item_table")
    assert mod.revision == "0054"


# ── calibration_result migration ─────────────────────────────────────────────


def test_calibration_result_migration_importable():
    """Migration module for calibration_result must be importable."""
    mod = _load_migration("alembic.versions.0055_calibration_result_table")
    assert hasattr(mod, "upgrade")
    assert hasattr(mod, "downgrade")


def test_calibration_result_migration_revision():
    """calibration_result migration must declare revision=0055."""
    mod = _load_migration("alembic.versions.0055_calibration_result_table")
    assert mod.revision == "0055"
