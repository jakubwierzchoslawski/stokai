"""Step 8: ANALOGY SEARCH — pgvector ANN top-K historical analogue retrieval.

Architecture enforcement:
  P-02 Cache-First — ANN search may be cached per embedding fingerprint.
  AC-001 — analogues populated for confidence synthesis (Step 9).

Single Responsibility: pgvector similarity query execution.
Dependency Inversion: repository is injected.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 10


class AnalogySearchStep:
    """Pipeline Step 8: ANALOGY SEARCH.

    Executes a pgvector ANN query to retrieve the top-K most similar
    historical events based on the current event's embedding.

    Parameters
    ----------
    repo:
        Repository exposing:
          ``find_analogues(tenant_id, embedding, top_k, exclude_event_id) -> list[uuid.UUID]``
    top_k:
        Number of analogues to retrieve (default: 10).
    """

    step_name: str = "s08_analogy_search"

    def __init__(self, repo: Any, top_k: int = _DEFAULT_TOP_K) -> None:
        self._repo = repo
        self._top_k = top_k

    async def execute(self, state: PipelineState) -> PipelineState:
        """Retrieve top-K historical analogues by pgvector ANN."""
        if state.embedding is None:
            logger.warning(
                "Step 8 (ANALOGY SEARCH): no embedding on state — skipping"
            )
            return state.model_copy(update={"analogues": []})

        analogues = await self._repo.find_analogues(
            tenant_id=state.tenant_id,
            embedding=state.embedding,
            top_k=self._top_k,
            exclude_event_id=state.raw_event_id,
        )

        logger.info(
            "Step 8 (ANALOGY SEARCH): raw_event_id=%s analogues_found=%d",
            state.raw_event_id,
            len(analogues),
        )

        return state.model_copy(update={"analogues": analogues})
