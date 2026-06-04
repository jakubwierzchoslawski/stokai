"""Unit tests for TTLValidator and MissingTTLError — all data-type branches.

Covers AC-002: writing to Redis without TTL for time-based types raises
MissingTTLError; immutable and event-driven types are exempt.
"""

from __future__ import annotations

import pytest

from ingestion.ttl_policy import DEFAULT_TTL_REGISTRY, DataType, TTLPolicy
from ingestion.ttl_validator import MissingTTLError, TTLValidator


@pytest.fixture
def validator() -> TTLValidator:
    return TTLValidator()


# ---------------------------------------------------------------------------
# time_based — raises when TTL absent
# ---------------------------------------------------------------------------


def test_price_bar_without_ttl_raises_missing_ttl_error(validator: TTLValidator) -> None:
    """PRICE_BAR is time_based; missing TTL must raise MissingTTLError."""
    with pytest.raises(MissingTTLError):
        validator.validate(DataType.PRICE_BAR, ttl_seconds=None)


def test_price_bar_with_ttl_does_not_raise(validator: TTLValidator) -> None:
    """PRICE_BAR with an explicit TTL must NOT raise."""
    validator.validate(DataType.PRICE_BAR, ttl_seconds=900)  # no exception


def test_fundamentals_without_ttl_raises(validator: TTLValidator) -> None:
    """FUNDAMENTALS is time_based; missing TTL must raise MissingTTLError."""
    with pytest.raises(MissingTTLError):
        validator.validate(DataType.FUNDAMENTALS, ttl_seconds=None)


def test_news_event_without_ttl_raises(validator: TTLValidator) -> None:
    """NEWS_EVENT is time_based; missing TTL must raise MissingTTLError."""
    with pytest.raises(MissingTTLError):
        validator.validate(DataType.NEWS_EVENT, ttl_seconds=None)


def test_macro_without_ttl_raises(validator: TTLValidator) -> None:
    """MACRO is time_based; missing TTL must raise MissingTTLError."""
    with pytest.raises(MissingTTLError):
        validator.validate(DataType.MACRO, ttl_seconds=None)


# ---------------------------------------------------------------------------
# immutable — exempt (no TTL required)
# ---------------------------------------------------------------------------


def test_historical_price_bar_with_none_ttl_does_not_raise(validator: TTLValidator) -> None:
    """PRICE_BAR_HISTORICAL is immutable; None TTL is valid."""
    validator.validate(DataType.PRICE_BAR_HISTORICAL, ttl_seconds=None)  # no exception


def test_event_embedding_with_none_ttl_does_not_raise(validator: TTLValidator) -> None:
    """EVENT_EMBEDDING is immutable; None TTL is valid."""
    validator.validate(DataType.EVENT_EMBEDDING, ttl_seconds=None)  # no exception


# ---------------------------------------------------------------------------
# event_driven — exempt (invalidated explicitly, not by TTL)
# ---------------------------------------------------------------------------


def test_company_score_with_none_ttl_does_not_raise(validator: TTLValidator) -> None:
    """COMPANY_SCORE is event_driven; None TTL is valid."""
    validator.validate(DataType.COMPANY_SCORE, ttl_seconds=None)  # no exception


# ---------------------------------------------------------------------------
# MissingTTLError carries attributes
# ---------------------------------------------------------------------------


def test_missing_ttl_error_carries_data_type_and_policy(validator: TTLValidator) -> None:
    """MissingTTLError must expose data_type and policy attributes."""
    with pytest.raises(MissingTTLError) as exc_info:
        validator.validate(DataType.PRICE_BAR, ttl_seconds=None)

    err = exc_info.value
    assert err.data_type == DataType.PRICE_BAR
    assert isinstance(err.policy, TTLPolicy)
    assert err.policy.invalidation == "time_based"


# ---------------------------------------------------------------------------
# Unknown data type — conservative (require TTL)
# ---------------------------------------------------------------------------


def test_unknown_data_type_raises_conservatively() -> None:
    """An unregistered DataType with no TTL must raise MissingTTLError."""
    # Build a registry that is missing PRICE_BAR so it becomes "unknown"
    sparse_registry: dict[DataType, TTLPolicy] = {
        k: v for k, v in DEFAULT_TTL_REGISTRY.items() if k != DataType.PRICE_BAR
    }
    validator = TTLValidator(registry=sparse_registry)

    with pytest.raises(MissingTTLError) as exc_info:
        validator.validate(DataType.PRICE_BAR, ttl_seconds=None)

    err = exc_info.value
    assert err.data_type == DataType.PRICE_BAR
    # Unknown type should still be reported as time_based in synthetic policy
    assert err.policy.invalidation == "time_based"
