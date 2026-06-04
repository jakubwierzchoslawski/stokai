"""Unit tests for TTLPolicy dataclass and DEFAULT_TTL_REGISTRY.

Verifies that all per-data-type TTL values match REQ-F-032 exactly.
"""

from __future__ import annotations

import pytest

from ingestion.ttl_policy import DataType, DEFAULT_TTL_REGISTRY


def test_price_bar_ttl_is_900_seconds():
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR]
    assert policy.redis_ttl_seconds == 900
    assert policy.pg_ttl_seconds == 900


def test_historical_price_bar_ttl_is_none():
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR_HISTORICAL]
    assert policy.redis_ttl_seconds is None
    assert policy.pg_ttl_seconds is None


def test_event_embedding_ttl_is_none():
    policy = DEFAULT_TTL_REGISTRY[DataType.EVENT_EMBEDDING]
    assert policy.redis_ttl_seconds is None
    assert policy.pg_ttl_seconds is None


def test_company_score_invalidation_type_is_event_driven():
    policy = DEFAULT_TTL_REGISTRY[DataType.COMPANY_SCORE]
    assert policy.invalidation == "event_driven"


def test_company_score_ttl_is_none():
    policy = DEFAULT_TTL_REGISTRY[DataType.COMPANY_SCORE]
    assert policy.redis_ttl_seconds is None
    assert policy.pg_ttl_seconds is None


def test_fundamentals_ttl_is_86400():
    policy = DEFAULT_TTL_REGISTRY[DataType.FUNDAMENTALS]
    assert policy.redis_ttl_seconds == 86400
    assert policy.pg_ttl_seconds == 86400


def test_news_event_ttl_is_3600():
    policy = DEFAULT_TTL_REGISTRY[DataType.NEWS_EVENT]
    assert policy.redis_ttl_seconds == 3600
    assert policy.pg_ttl_seconds == 3600


def test_macro_ttl_is_86400():
    policy = DEFAULT_TTL_REGISTRY[DataType.MACRO]
    assert policy.redis_ttl_seconds == 86400
    assert policy.pg_ttl_seconds == 86400


def test_price_bar_historical_invalidation_is_immutable():
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR_HISTORICAL]
    assert policy.invalidation == "immutable"


def test_event_embedding_invalidation_is_immutable():
    policy = DEFAULT_TTL_REGISTRY[DataType.EVENT_EMBEDDING]
    assert policy.invalidation == "immutable"


def test_price_bar_invalidation_is_time_based():
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR]
    assert policy.invalidation == "time_based"


def test_all_data_types_present_in_registry():
    for dt in DataType:
        assert dt in DEFAULT_TTL_REGISTRY, f"{dt} missing from DEFAULT_TTL_REGISTRY"


def test_ttl_policy_is_frozen():
    """TTLPolicy must be immutable (frozen dataclass)."""
    policy = DEFAULT_TTL_REGISTRY[DataType.PRICE_BAR]
    with pytest.raises((AttributeError, TypeError)):
        policy.redis_ttl_seconds = 999  # type: ignore[misc]
