"""
Unit tests for Layer 1 and Layer 2 migration content verification.

These verify migration file structure/revision metadata without running Alembic.
DB-level tests (actual CREATE TABLE) are in integration tests.
"""
from __future__ import annotations

import importlib


def _load_migration(module_name: str):
    return importlib.import_module(f"alembic.versions.{module_name}")


# ── Layer 1 ───────────────────────────────────────────────────────────────────


def test_layer1_migration_has_correct_revision():
    mod = _load_migration("0033_layer1_episodic_tables")
    assert mod.revision == "0033"
    assert mod.down_revision == "0032"


def test_layer1_migration_defines_upgrade_and_downgrade():
    mod = _load_migration("0033_layer1_episodic_tables")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


# ── Layer 2 ───────────────────────────────────────────────────────────────────


def test_layer2_migration_has_correct_revision():
    mod = _load_migration("0034_layer2_semantic_tables")
    assert mod.revision == "0034"
    assert mod.down_revision == "0033"


def test_layer2_migration_defines_upgrade_and_downgrade():
    mod = _load_migration("0034_layer2_semantic_tables")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
