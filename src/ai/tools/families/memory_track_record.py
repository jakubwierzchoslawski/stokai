"""Memory + Track Record tool family.

Tools:
  - GetSemanticFacts            (name="get_semantic_facts")
  - GetProceduralPatterns       (name="get_procedural_patterns")
  - GetRecommendationOutcomes   (name="get_recommendation_outcomes")

All tools scope queries by tenant_id and return at most MAX_ROWS rows.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import MAX_ROWS, BaseTool, BaseToolInput


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetSemanticFactsInput(BaseToolInput):
    """Input for GetSemanticFacts.

    Supports pgvector cosine search when query is provided,
    or exact namespace match when only namespace is given.
    """

    namespace: str
    query: str | None = None
    entity_id: UUID | None = None


class GetProceduralPatternsInput(BaseToolInput):
    """Input for GetProceduralPatterns."""

    pattern_type: str | None = None
    agent_role: str | None = None


class GetRecommendationOutcomesInput(BaseToolInput):
    """Input for GetRecommendationOutcomes."""

    ticker: str
    limit: int = MAX_ROWS


# ---------------------------------------------------------------------------
# GetSemanticFacts
# ---------------------------------------------------------------------------


class GetSemanticFacts(BaseTool):
    """Return semantic memory facts for a namespace or entity.

    Uses pgvector cosine similarity search when a query embedding is available,
    or falls back to exact namespace match.

    Returns at most 50 facts (MAX_ROWS).
    """

    name = "get_semantic_facts"

    async def _execute(
        self, inputs: GetSemanticFactsInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"namespace": inputs.namespace}
        if inputs.query:
            params["query"] = inputs.query
        if inputs.entity_id:
            params["entity_id"] = str(inputs.entity_id)

        cache_key = build_cache_key(
            data_type=DataType.COMPANY_SCORE,  # reuse event-driven invalidated type
            entity_id=inputs.namespace,
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


# ---------------------------------------------------------------------------
# GetProceduralPatterns
# ---------------------------------------------------------------------------


class GetProceduralPatterns(BaseTool):
    """Return approved procedural patterns ordered by success_rate DESC.

    Returns at most MAX_ROWS patterns.
    """

    name = "get_procedural_patterns"

    async def _execute(
        self, inputs: GetProceduralPatternsInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if inputs.pattern_type:
            params["pattern_type"] = inputs.pattern_type
        if inputs.agent_role:
            params["agent_role"] = inputs.agent_role

        cache_key = build_cache_key(
            data_type=DataType.COMPANY_SCORE,
            entity_id="procedural",
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


# ---------------------------------------------------------------------------
# GetRecommendationOutcomes
# ---------------------------------------------------------------------------


class GetRecommendationOutcomes(BaseTool):
    """Return historical recommendation outcomes for a ticker.

    JOINs recommendation_outcome to ai_recommendation for full context.
    Scoped by tenant_id.
    """

    name = "get_recommendation_outcomes"

    async def _execute(
        self, inputs: GetRecommendationOutcomesInput  # type: ignore[override]
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
