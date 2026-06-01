"""Step 5: EMBED — generate 1536-dim embedding and upsert to geopolitical_events.

Architecture enforcement:
  P-02 Cache-First — embedding cached in Redis keyed on fingerprint (TTL infinity).
  P-03 Inputs-Hash Invalidation — embedding reused for identical events.
  AC-001 — embedding upserted into geopolitical_events for analogy search (Step 8).

Single Responsibility: embedding generation, Redis caching, and DB upsert.
Dependency Inversion: embedding provider and repository are injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_EMBED_CACHE_PREFIX = "event:embedding:"


class EmbedStep:
    """Pipeline Step 5: EMBED.

    Generates a 1536-dimensional vector embedding for the event description
    and upserts it into the ``geopolitical_events`` table.

    Parameters
    ----------
    embedding_provider:
        Async client exposing ``embed(text: str) -> list[float]``.
    repo:
        Repository exposing ``upsert_event_record(**kwargs)`` as an awaitable.
    redis_client:
        Optional Redis client for caching embeddings (TTL infinity, P-02).
    """

    step_name: str = "s05_embed"

    def __init__(
        self,
        embedding_provider: Any,
        repo: Any,
        redis_client: Any = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._repo = repo
        self._redis = redis_client

    async def execute(self, state: PipelineState) -> PipelineState:
        """Generate embedding and upsert to geopolitical_events."""
        description = state.event_description or ""

        # Cache-first: check Redis for existing embedding (P-02)
        embedding = await self._get_cached_embedding(state.fingerprint)

        if embedding is None:
            embedding = await self._embedding_provider.embed(description)
            await self._cache_embedding(state.fingerprint, embedding)

        # Upsert into geopolitical_events
        await self._repo.upsert_event_record(
            raw_event_id=state.raw_event_id,
            tenant_id=state.tenant_id,
            source=state.payload.source.value,
            detected_at=state.payload.detected_at,
            category=state.category.value if state.category else None,
            intensity=state.intensity,
            geo_lat=state.geo_lat,
            geo_lon=state.geo_lon,
            embedding=embedding,
            raw_payload=state.payload.raw_payload,
        )

        logger.info(
            "Step 5 (EMBED): raw_event_id=%s embedding_dim=%d",
            state.raw_event_id,
            len(embedding),
        )

        return state.model_copy(update={"embedding": embedding})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_cached_embedding(self, fingerprint: str | None) -> list[float] | None:
        """Return cached embedding from Redis or None on miss."""
        if self._redis is None or fingerprint is None:
            return None
        try:
            import json
            raw = await self._redis.get(f"{_EMBED_CACHE_PREFIX}{fingerprint}")
            if raw is not None:
                return json.loads(raw)
        except Exception:  # noqa: BLE001
            pass
        return None

    async def _cache_embedding(
        self, fingerprint: str | None, embedding: list[float]
    ) -> None:
        """Store embedding in Redis with no TTL (TTL infinity per P-02)."""
        if self._redis is None or fingerprint is None:
            return
        try:
            import json
            await self._redis.set(
                f"{_EMBED_CACHE_PREFIX}{fingerprint}",
                json.dumps(embedding),
            )
        except Exception:  # noqa: BLE001
            pass
