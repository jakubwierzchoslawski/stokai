"""
Unit tests for Layer 3 and Layer 4 migration content.

These tests verify the migration file structure rather than running Alembic
directly (integration tests cover live migration application).
"""
from __future__ import annotations

import importlib


def _load_migration(module_name: str):
    return importlib.import_module(f"alembic.versions.{module_name}")


def test_layer3_migration_has_correct_revision():
    mod = _load_migration("0035_layer3_procedural_tables")
    assert mod.revision == "0035"
    assert mod.down_revision == "0034"


def test_layer4_migration_has_correct_revision():
    mod = _load_migration("0036_layer4_feedback_improvement_tables")
    assert mod.revision == "0036"
    assert mod.down_revision == "0035"


def test_layer3_migration_defines_upgrade():
    mod = _load_migration("0035_layer3_procedural_tables")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_layer4_migration_defines_upgrade():
    mod = _load_migration("0036_layer4_feedback_improvement_tables")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
