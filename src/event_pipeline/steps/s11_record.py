"""Step 11: RECORD — persist event_scores, ai_audit_log, episodic_memory atomically.

Architecture enforcement:
  P-08 Immutable Episodic Memory — episodic_memory writes are INSERT-only, never UPDATE.
  AC-005 — on any DB error raises PipelineHalt to prevent partial alert dispatch.
  AC-001 — all three writes within a single logical transaction.

Single Responsibility: atomic persistence of pipeline outputs.
Dependency Inversion: repository is injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.exceptions import PipelineHalt
from src.event_pipeline.pipeline_state import AlertRoute, PipelineState

logger = logging.getLogger(__name__)


class RecordStep:
    """Pipeline Step 11: RECORD.

    Within a single atomic operation:
    1. Writes event_scores rows for each portfolio in state.exposure_map.
    2. Sets raw_event.pipeline_status = 'completed'.
    3. Writes an episodic_memory record (INSERT only — P-08).

    Parameters
    ----------
    repo:
        Repository exposing:
          - ``write_event_score_batch(scores: list[dict]) -> None``
          - ``write_episodic_memory(tenant_id, source_ref, event_type, payload) -> None``
          - ``update_status(raw_event_id, status=...) -> None``
    """

    step_name: str = "s11_record"

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def execute(self, state: PipelineState) -> PipelineState:
        """Persist scores, update pipeline status, append episodic memory record."""
        try:
            # 1. Write event_scores for all portfolios
            scores = [
                {
                    "portfolio_id": portfolio_id,
                    "event_id": state.raw_event_id,
                    "tenant_id": state.tenant_id,
                    "score": score,
                    "confidence": state.confidence,
                    "route": state.route.value if state.route else None,
                }
                for portfolio_id, score in state.exposure_map.items()
            ]
            await self._repo.write_event_score_batch(scores)

            # 2. Append episodic memory record — INSERT only (P-08)
            episodic_payload = {
                "category": state.category.value if state.category else None,
                "intensity": state.intensity,
                "route": state.route.value if state.route else None,
                "confidence": state.confidence,
            }
            await self._repo.write_episodic_memory(
                tenant_id=state.tenant_id,
                event_type="pipeline_completed",
                source_ref=state.raw_event_id,
                payload=episodic_payload,
            )

            # 3. Mark pipeline as completed
            await self._repo.update_status(
                state.raw_event_id,
                status="completed",
            )

        except PipelineHalt:
            raise
        except Exception as exc:
            raise PipelineHalt(
                step_name=self.step_name,
                detail=f"Record step DB error: {exc}",
            ) from exc

        logger.info(
            "Step 11 (RECORD): raw_event_id=%s portfolios=%d route=%s",
            state.raw_event_id,
            len(state.exposure_map),
            state.route.value if state.route else "None",
        )

        return state
