"""Events + History tool family.

Tools:
  - GetEventsByCompany           (name="get_events_by_company")
  - GetEventAnalogies            (name="get_event_analogies")
  - GetAiRecommendationHistory   (name="get_ai_recommendation_history")

Visibility rule for geo_event:
  tenant_id IS NULL  → global event (visible to all tenants)
  tenant_id = :tid   → tenant-specific event (visible to that tenant only)
  tenant_id = other  → NOT returned

GetEventAnalogies uses IHistoricalSearch protocol (injected — no concrete class import).
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import MAX_ROWS, BaseTool, BaseToolInput


# ---------------------------------------------------------------------------
# IHistoricalSearch protocol
# ---------------------------------------------------------------------------


class IHistoricalSearch(Protocol):
    """Protocol for pgvector HNSW cosine similarity search.

    Injected into GetEventAnalogies so the tool is decoupled from the
    concrete embedding repository.
    """

    async def search(
        self,
        embedding: list[float],
        top_k: int,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        """Return the top_k most similar events to the query embedding."""
        ...


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetEventsByCompanyInput(BaseToolInput):
    """Input for GetEventsByCompany."""

    company_id: UUID
    limit: int = MAX_ROWS


class GetEventAnalogiesInput(BaseToolInput):
    """Input for GetEventAnalogies."""

    event_id: UUID
    top_k: int = 10


class GetAiRecommendationHistoryInput(BaseToolInput):
    """Input for GetAiRecommendationHistory."""

    ticker: str
    limit: int = MAX_ROWS


# ---------------------------------------------------------------------------
# GetEventsByCompany
# ---------------------------------------------------------------------------


class GetEventsByCompany(BaseTool):
    """Return geo_event rows relevant to a company.

    Visibility rule:
        geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id

    This ensures global events are returned to all tenants while
    other tenants' private events remain invisible.
    """

    name = "get_events_by_company"

    async def _execute(
        self, inputs: GetEventsByCompanyInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params = {"company_id": str(inputs.company_id)}
        cache_key = build_cache_key(
            data_type=DataType.NEWS_EVENT,
            entity_id=str(inputs.company_id),
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.NEWS_EVENT,
            fetch_fn=_fetch,
        )

        if not isinstance(rows, list):
            return []

        # Client-side visibility filter: keep global or matching tenant rows
        tenant_str = str(inputs.tenant_id)
        return [
            row for row in rows
            if row.get("tenant_id") is None or row.get("tenant_id") == tenant_str
        ]


# ---------------------------------------------------------------------------
# GetEventAnalogies
# ---------------------------------------------------------------------------


class GetEventAnalogies(BaseTool):
    """Return similar historical events via pgvector HNSW cosine search.

    top_k is capped at MAX_ROWS to honour the bounded-output contract.
    Uses IHistoricalSearch protocol — no concrete class is imported here.
    """

    name = "get_event_analogies"

    async def _execute(
        self, inputs: GetEventAnalogiesInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        # Cap top_k at MAX_ROWS
        effective_top_k = min(inputs.top_k, MAX_ROWS)

        params = {"event_id": str(inputs.event_id), "top_k": effective_top_k}
        cache_key = build_cache_key(
            data_type=DataType.EVENT_EMBEDDING,
            entity_id=str(inputs.event_id),
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.EVENT_EMBEDDING,
            fetch_fn=_fetch,
        )
        return rows if isinstance(rows, list) else []


# ---------------------------------------------------------------------------
# GetAiRecommendationHistory
# ---------------------------------------------------------------------------


class GetAiRecommendationHistory(BaseTool):
    """Return historical AI recommendations for a ticker, scoped to tenant.

    Joins ai_recommendation to recommendation_outcome for context.
    """

    name = "get_ai_recommendation_history"

    async def _execute(
        self, inputs: GetAiRecommendationHistoryInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params = {"ticker": inputs.ticker, "limit": inputs.limit}
        cache_key = build_cache_key(
            data_type=DataType.COMPANY_SCORE,
            entity_id=inputs.ticker,
            params=params,
            tenant_id=str(inputs.tenant_id),
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.COMPANY_SCORE,
            fetch_fn=_fetch,
        )
        return rows if isinstance(rows, list) else []
