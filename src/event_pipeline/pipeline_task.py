"""Celery task entry point for the Mode A reactive pipeline.

Architecture enforcement:
  P-06 12-Factor — task configuration from settings only.
  AC-001 — orchestrates the 13-step executor in the correct order.
  Idempotency — re-queued completed/duplicate events are no-ops.

Single Responsibility: task entry point only; all business logic delegated to
  ``PipelineExecutor`` and individual step classes.

Note: This module is imported by the Celery worker.  Heavy imports (steps,
  settings) are kept at module level so they are loaded once per worker process.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Idempotency guard helpers (injected / replaced in tests)
# ---------------------------------------------------------------------------

async def get_raw_event_status(raw_event_id: uuid.UUID, tenant_id: uuid.UUID) -> str | None:
    """Return the current pipeline_status of the raw event, or None if not found.

    This is a thin wrapper so tests can patch it cleanly.
    In production this would call the RawEventRepository.
    """
    # Deferred import to avoid circular imports at module load time
    from src.event_pipeline.repositories.raw_event_repository import RawEventRepository
    repo = RawEventRepository()
    return await repo.get_status(raw_event_id)


def build_executor(raw_event_id: uuid.UUID, tenant_id: uuid.UUID, langfuse_client: Any) -> Any:
    """Construct a fully-wired PipelineExecutor with all 13 steps injected.

    This factory function is defined at module level so tests can patch it to
    assert that the executor is (or is not) constructed.
    """
    from src.event_pipeline.pipeline_executor import PipelineExecutor
    from src.event_pipeline.repositories.raw_event_repository import RawEventRepository

    # Steps are imported lazily here so module load does not pull in all deps
    from src.event_pipeline.steps.s01_ingest import IngestStep
    from src.event_pipeline.steps.s02_deduplicate import DeduplicateStep
    from src.event_pipeline.steps.s03_parse import ParseStep
    from src.event_pipeline.steps.s04_classify import ClassifyStep
    from src.event_pipeline.steps.s05_embed import EmbedStep
    from src.event_pipeline.steps.s06_portfolio_scan import PortfolioScanStep
    from src.event_pipeline.steps.s07_exposure_score import ExposureScoreStep
    from src.event_pipeline.steps.s08_analogy_search import AnalogySearchStep
    from src.event_pipeline.steps.s09_confidence_calc import ConfidenceCalcStep
    from src.event_pipeline.steps.s10_routing import RoutingStep
    from src.event_pipeline.steps.s11_record import RecordStep
    from src.event_pipeline.steps.s12_dispatch import DispatchStep
    from src.event_pipeline.steps.s13_trace import TraceStep

    repo = RawEventRepository()

    steps = [
        IngestStep(repo=repo),
        DeduplicateStep(repo=repo),
        ParseStep(),
        ClassifyStep(repo=repo, langfuse_client=langfuse_client),
        EmbedStep(repo=repo),
        PortfolioScanStep(repo=repo),
        ExposureScoreStep(repo=repo),
        AnalogySearchStep(repo=repo),
        ConfidenceCalcStep(repo=repo, langfuse_client=langfuse_client),
        RoutingStep(),
        RecordStep(repo=repo),
        DispatchStep(),
        TraceStep(repo=repo, langfuse_client=langfuse_client),
    ]

    return PipelineExecutor(
        steps=steps,
        langfuse_client=langfuse_client,
        raw_event_repo=repo,
    )


# ---------------------------------------------------------------------------
# Public async task function (wrapped by Celery in celery_app.py)
# ---------------------------------------------------------------------------

async def run_pipeline_task(raw_event_id_str: str, tenant_id_str: str) -> None:
    """Idempotent pipeline entry point.

    Parameters
    ----------
    raw_event_id_str:
        UUID string for the raw event to process.
    tenant_id_str:
        UUID string for the owning tenant.

    Behaviour
    ---------
    - If ``pipeline_status`` is already ``completed`` or ``duplicate``:
      returns immediately (idempotency guarantee for Celery at-least-once).
    - Otherwise: constructs the executor, builds the initial state, and runs
      the 13-step pipeline.
    """
    raw_event_id = uuid.UUID(raw_event_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    # Idempotency guard
    current_status = await get_raw_event_status(raw_event_id, tenant_id)
    if current_status in ("completed", "duplicate"):
        logger.info(
            "Pipeline task skipped (idempotency): raw_event_id=%s status=%s",
            raw_event_id_str,
            current_status,
        )
        return

    # Langfuse trace opened here; closed in Step 13
    langfuse_client = _open_langfuse_trace(raw_event_id, tenant_id)

    executor = build_executor(raw_event_id, tenant_id, langfuse_client)

    # Build initial state from the raw event record
    initial_state = await _build_initial_state(raw_event_id, tenant_id)

    await executor.run(initial_state)


async def _build_initial_state(
    raw_event_id: uuid.UUID, tenant_id: uuid.UUID
) -> "PipelineState":  # noqa: F821
    """Load raw event from DB and build initial PipelineState."""
    from src.event_pipeline.pipeline_state import PipelineState, RawEventPayload, RawEventSource
    from src.event_pipeline.repositories.raw_event_repository import RawEventRepository
    import datetime as dt

    repo = RawEventRepository()
    raw = await repo.get_by_id(raw_event_id)

    payload = RawEventPayload(
        source=RawEventSource(raw.source) if raw else RawEventSource.GDELT,
        raw_payload=raw.raw_payload if raw else {},
        detected_at=raw.detected_at if raw else dt.datetime.now(dt.timezone.utc),
        tenant_id=tenant_id,
    )
    return PipelineState(
        raw_event_id=raw_event_id,
        tenant_id=tenant_id,
        payload=payload,
    )


def _open_langfuse_trace(raw_event_id: uuid.UUID, tenant_id: uuid.UUID) -> Any:
    """Open a Langfuse trace for this pipeline run.

    Returns a no-op placeholder when Langfuse is not configured.
    """
    try:
        from src.observability.langfuse_client import get_langfuse_client
        client = get_langfuse_client()
        return client.trace(
            name="mode_a_pipeline",
            id=str(raw_event_id),
            metadata={"tenant_id": str(tenant_id)},
        )
    except Exception:  # noqa: BLE001
        logger.warning("Langfuse unavailable — pipeline will run without tracing")
        return _NoopTrace()


class _NoopTrace:
    """Placeholder trace object when Langfuse is unavailable."""

    def span(self, *args: Any, **kwargs: Any) -> "_NoopTrace":
        return self

    def finish(self, *args: Any, **kwargs: Any) -> None:
        pass
