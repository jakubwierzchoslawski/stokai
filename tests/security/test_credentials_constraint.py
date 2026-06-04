"""
tests.security.test_credentials_constraint — credentials_ref constraint tests.

Covers AC-003: source_config.credentials_ref accepts only vault-reference
strings; raw API keys are rejected at both ORM and DB layers.
"""
import uuid

import pytest

from src.storage.models.source_config import CREDENTIALS_REF_PATTERN, SourceConfig


# ── Helper ─────────────────────────────────────────────────────────────────────

def _make_source_config(**kwargs) -> SourceConfig:
    """Build a SourceConfig with sensible defaults; override with kwargs."""
    defaults = {
        "tenant_id": uuid.uuid4(),
        "source_name": "test_source",
        "credentials_ref": "env:TEST_API_KEY",
    }
    defaults.update(kwargs)
    return SourceConfig(**defaults)


# ── ORM validator tests ────────────────────────────────────────────────────────

def test_credentials_ref_orm_validator_accepts_env_prefix() -> None:
    """ORM validator must accept env:UPPERCASE_KEY format."""
    cfg = _make_source_config(credentials_ref="env:FINNHUB_API_KEY")
    assert cfg.credentials_ref == "env:FINNHUB_API_KEY"


def test_credentials_ref_orm_validator_accepts_vault_prefix() -> None:
    """ORM validator must accept vault:UPPERCASE_KEY format."""
    cfg = _make_source_config(credentials_ref="vault:MY_SECRET_123")
    assert cfg.credentials_ref == "vault:MY_SECRET_123"


def test_credentials_ref_orm_validator_rejects_raw_key() -> None:
    """ORM validator must raise ValueError for raw API key strings."""
    with pytest.raises(ValueError, match="invalid"):
        _make_source_config(credentials_ref="sk-abc123xyz")


def test_credentials_ref_orm_validator_rejects_empty_string() -> None:
    """ORM validator must raise ValueError for empty string."""
    with pytest.raises(ValueError):
        _make_source_config(credentials_ref="")


def test_credentials_ref_orm_validator_rejects_env_lowercase() -> None:
    """ORM validator must reject lowercase keys (e.g. 'env:my_key')."""
    with pytest.raises(ValueError, match="invalid"):
        _make_source_config(credentials_ref="env:my_key")


# ── DB constraint simulation test ─────────────────────────────────────────────

def test_credentials_ref_db_constraint_rejects_raw_key() -> None:
    """The regex pattern used for the DB CHECK constraint must reject raw API keys.

    This test validates the constraint expression used in the Alembic migration
    without requiring a live database connection. The pattern is applied via
    Python re to confirm it would reject the same values the PG regex rejects.
    """
    # Values that must pass
    valid_values = [
        "env:FINNHUB_API_KEY",
        "env:FMP_API_KEY",
        "vault:MY_SECRET",
        "vault:PROD_DB_PASSWORD_123",
    ]
    for v in valid_values:
        assert CREDENTIALS_REF_PATTERN.match(v), f"Expected {v!r} to be valid"

    # Values that must fail
    invalid_values = [
        "sk-abcdef1234567890",          # raw Stripe-style key
        "AIzaSyAbc123",                 # raw Google key
        "env:my_lowercase",             # lowercase — rejected
        "vault:",                       # missing key portion
        "ENV:MY_VAR",                   # uppercase prefix — only 'env'/'vault' allowed
        "secret:MY_VAR",               # unknown prefix
        "",                             # empty string
        "env:MY KEY",                  # space — invalid character
    ]
    for v in invalid_values:
        assert not CREDENTIALS_REF_PATTERN.match(v), f"Expected {v!r} to be invalid"
