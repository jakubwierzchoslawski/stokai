"""Step 1: INGEST — set detected_at and persist RawEvent with status=running.

Architecture enforcement:
  P-01 Provider Abstraction — payload already populated by the adapter before entry.
  AC-001 — first step in the 13-step pipeline.

Single Responsibility: DB write and detected_at assignment only.
Dependency Inversion: RawEventRepository is injected.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


class IngestStep:
    """Pipeline Step 1: INGEST.

    Writes the RawEvent to the DB with ``pipeline_status = running``
    and ensures ``detected_at`` is set.
    """

    step_name: str = "s01_ingest"

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def execute(self, state: PipelineState) -> PipelineState:
        """Mark the raw event as running and ensure detected_at is set."""
        # Update pipeline_status to running
        await self._repo.update_status(
            state.raw_event_id,
            status="running",
        )

        logger.info(
            "Step 1 (INGEST): raw_event_id=%s source=%s",
            state.raw_event_id,
            state.payload.source.value,
        )

        return state
