"""TTLPolicy dataclass, DataType enum, and default TTL registry.

Authoritative type contracts for the entire caching subsystem.
All per-data-type TTL values are imported from src/ingestion/ttl_contract.py
so that there is exactly one place to change a TTL value.
Environment variable overrides are applied at import time via
src/config/ttl_defaults.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ingestion.ttl_contract import (
    COMPANY_SCORE_TTL_S,
    EVENT_EMBEDDING_TTL_S,
    FUNDAMENTALS_TTL_S,
    HISTORICAL_PRICE_BAR_TTL_S,
    MACRO_TTL_S,
    NEWS_EVENT_TTL_S,
    PRICE_BAR_DELAYED_TTL_S,
)


class DataType(StrEnum):
    """Enumeration of all cacheable data types in the system."""

    PRICE_BAR = "price_bar"
    PRICE_BAR_HISTORICAL = "price_bar_historical"  # past close — immutable
    FUNDAMENTALS = "fundamentals"
    NEWS_EVENT = "news_event"
    MACRO = "macro"
    EVENT_EMBEDDING = "event_embedding"  # immutable
    COMPANY_SCORE = "company_score"  # event-driven invalidation only


@dataclass(frozen=True)
class TTLPolicy:
    """TTL configuration for a single data type.

    Attributes:
        data_type: The data type this policy applies to.
        redis_ttl_seconds: TTL in seconds for the Redis hot-cache layer.
            None = no expiry (infinite lifetime).
        pg_ttl_seconds: TTL in seconds for the PostgreSQL persistent-cache layer.
            None = no expiry (infinite lifetime).
        invalidation: Invalidation strategy.
            "time_based"   — key expires automatically after TTL.
            "event_driven" — key is valid until explicitly invalidated.
            "immutable"    — key is never invalidated (fetched once per system lifetime).
    """

    data_type: DataType
    redis_ttl_seconds: int | None
    pg_ttl_seconds: int | None
    invalidation: str  # "time_based" | "event_driven" | "immutable"


# Default registry — values sourced from ingestion.ttl_contract (single source of truth).
# Override individual TTLs at runtime via src/config/ttl_defaults.py
# (which reads PRICE_BAR_TTL_SECONDS etc. from env vars).
DEFAULT_TTL_REGISTRY: dict[DataType, TTLPolicy] = {
    DataType.PRICE_BAR: TTLPolicy(
        DataType.PRICE_BAR,
        redis_ttl_seconds=PRICE_BAR_DELAYED_TTL_S,
        pg_ttl_seconds=PRICE_BAR_DELAYED_TTL_S,
        invalidation="time_based",
    ),
    DataType.PRICE_BAR_HISTORICAL: TTLPolicy(
        DataType.PRICE_BAR_HISTORICAL,
        redis_ttl_seconds=HISTORICAL_PRICE_BAR_TTL_S,
        pg_ttl_seconds=HISTORICAL_PRICE_BAR_TTL_S,
        invalidation="immutable",
    ),
    DataType.FUNDAMENTALS: TTLPolicy(
        DataType.FUNDAMENTALS,
        redis_ttl_seconds=FUNDAMENTALS_TTL_S,
        pg_ttl_seconds=FUNDAMENTALS_TTL_S,
        invalidation="time_based",
    ),
    DataType.NEWS_EVENT: TTLPolicy(
        DataType.NEWS_EVENT,
        redis_ttl_seconds=NEWS_EVENT_TTL_S,
        pg_ttl_seconds=NEWS_EVENT_TTL_S,
        invalidation="time_based",
    ),
    DataType.MACRO: TTLPolicy(
        DataType.MACRO,
        redis_ttl_seconds=MACRO_TTL_S,
        pg_ttl_seconds=MACRO_TTL_S,
        invalidation="time_based",
    ),
    DataType.EVENT_EMBEDDING: TTLPolicy(
        DataType.EVENT_EMBEDDING,
        redis_ttl_seconds=EVENT_EMBEDDING_TTL_S,
        pg_ttl_seconds=EVENT_EMBEDDING_TTL_S,
        invalidation="immutable",
    ),
    DataType.COMPANY_SCORE: TTLPolicy(
        DataType.COMPANY_SCORE,
        redis_ttl_seconds=COMPANY_SCORE_TTL_S,
        pg_ttl_seconds=COMPANY_SCORE_TTL_S,
        invalidation="event_driven",
    ),
}
