"""
PipelineExecutor — orchestrates all 12 Mode A Reactive Pipeline steps.

Dependency injection: all collaborators are passed via constructor.
Error handling: StepTimeoutError and CostCeilingExceededError are caught,
logged, and re-raised as PipelineError. The Langfuse trace is always flushed
in the finally block regardless of success or failure.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.embedding.service import EmbeddingService
from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.ai.interfaces.i_llm_client import ILLMClient
from src.alerts.interfaces.i_alert_dispatcher import IAlertDispatcher
from src.alerts.interfaces.i_alert_rule_evaluator import IAlertRuleEvaluator
from src.config.settings import Settings
from src.events.cost_accumulator import CostAccumulator
from src.events.exceptions import (
    CostCeilingExceededError,
    PipelineError,
    SourceDisabledError,
    StepTimeoutError,
)
from src.events.interfaces.i_workflow_queue import IWorkflowQueue
from src.events.models import PipelineContext, PipelineResult, RawEvent
from src.events.steps.classify_event import classify_event
from src.events.steps.compute_exposure_map import compute_exposure_map
from src.events.steps.dispatch_or_log_silent import dispatch_or_log_silent
from src.events.steps.embed_event import embed_event
from src.events.steps.enqueue_deep_dive import enqueue_deep_dive
from src.events.steps.evaluate_alert_rules import evaluate_alert_rules
from src.events.steps.extract_tickers import extract_tickers
from src.events.steps.find_historical_analogies import find_historical_analogies
from src.events.steps.generate_alert_text import generate_alert_text
from src.events.steps.persist_event_record import persist_event_record
from src.events.steps.persist_raw_event import persist_raw_event
from src.events.steps.return_pipeline_result import return_pipeline_result
from src.storage.interfaces.i_alert_repository import IAlertRepository
from src.storage.interfaces.i_event_exposure_repository import IEventExposureRepository
from src.storage.interfaces.i_geo_event_repository import IGeoEventRepository
from src.storage.repositories.event_embedding import EventEmbeddingRepository

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """Orchestrates the 12-step Mode A Reactive Pipeline.

    All collaborators are injected at construction time to satisfy DIP and
    enable full unit-test mockability.
    """

    def __init__(
        self,
        geo_event_repo: IGeoEventRepository,
        event_exposure_repo: IEventExposureRepository,
        event_embedding_repo: EventEmbeddingRepository,
        alert_repo: IAlertRepository,
        llm_client_haiku: ILLMClient,
        llm_client_sonnet: ILLMClient,
        embedding_service: EmbeddingService,
        tracer: ILangfuseTracer,
        alert_rule_evaluator: IAlertRuleEvaluator,
        alert_dispatcher: IAlertDispatcher,
        workflow_queue: IWorkflowQueue,
        db_session: AsyncSession,
        settings: Settings,
        twitter_enabled: bool = False,
    ) -> None:
        self._geo_event_repo = geo_event_repo
        self._event_exposure_repo = event_exposure_repo
        self._event_embedding_repo = event_embedding_repo
        self._alert_repo = alert_repo
        self._llm_client_haiku = llm_client_haiku
        self._llm_client_sonnet = llm_client_sonnet
        self._embedding_service = embedding_service
        self._tracer = tracer
        self._alert_rule_evaluator = alert_rule_evaluator
        self._alert_dispatcher = alert_dispatcher
        self._workflow_queue = workflow_queue
        self._db_session = db_session
        self._settings = settings
        self._twitter_enabled = twitter_enabled

    # ── Public API ────────────────────────────────────────────────────────────

    async def run(self, raw_event: RawEvent) -> PipelineResult:
        """Execute all 12 pipeline steps for *raw_event*.

        Args:
            raw_event: Inbound event from any source adapter.

        Returns:
            PipelineResult with per-step latencies, total cost, and trace ID.

        Raises:
            PipelineError: On any unrecoverable step failure.
        """
        ctx = PipelineContext(
            raw_event=raw_event,
            cost_accumulator=CostAccumulator(),
        )

        # Start Langfuse trace
        trace_id = self._tracer.start_trace(
            "mode_a_pipeline",
            {
                "source_provider": raw_event.source_provider,
                "tenant_id": str(raw_event.tenant_id),
            },
        )
        ctx.langfuse_trace_id = trace_id

        try:
            ctx = await self._execute_steps(ctx)
        except SourceDisabledError as exc:
            logger.info(
                "Source disabled — returning empty result: %s", exc
            )
            # Return an empty result without error trace
            return PipelineResult(
                event_id=ctx.event_id or __import__("uuid").uuid4(),
                alert_dispatched=False,
                silent_logged=False,
                deep_dive_enqueued=False,
                total_cost_usd=0.0,
                step_latencies_ms=ctx.step_latencies_ms,
                langfuse_trace_id=trace_id,
            )
        except (StepTimeoutError, CostCeilingExceededError) as exc:
            logger.error(
                "Pipeline halted: %s — %s", type(exc).__name__, exc
            )
            self._tracer.end_trace(trace_id, {"error": type(exc).__name__})
            raise PipelineError(
                f"Pipeline failed due to {type(exc).__name__}: {exc}"
            ) from exc
        except PipelineError:
            self._tracer.end_trace(trace_id, {"error": "PipelineError"})
            raise
        except Exception as exc:
            logger.exception("Unexpected error in pipeline")
            self._tracer.end_trace(trace_id, {"error": type(exc).__name__})
            raise PipelineError(
                f"Unexpected pipeline error: {type(exc).__name__}"
            ) from exc

        # Step 12: build result and flush trace
        result = await return_pipeline_result(ctx, self._tracer, self._db_session)
        return result

    # ── Private ───────────────────────────────────────────────────────────────

    async def _execute_steps(self, ctx: PipelineContext) -> PipelineContext:
        """Run steps 1–11 in order."""

        # Step 1 — persist raw event
        ctx = await persist_raw_event(
            ctx, self._geo_event_repo, twitter_enabled=self._twitter_enabled
        )

        # Step 2 — classify event
        ctx = await classify_event(ctx, self._llm_client_haiku, self._tracer)

        # Step 3 — extract tickers
        ctx = await extract_tickers(ctx, self._llm_client_haiku, self._tracer)

        # Step 4 — compute exposure map
        ctx = await compute_exposure_map(ctx, self._db_session)

        # Step 5 — persist event record
        ctx = await persist_event_record(
            ctx, self._geo_event_repo, self._event_exposure_repo
        )

        # Step 6 — embed event (PLAN-F-004: EmbeddingService protocol, idempotent)
        ctx = await embed_event(
            ctx, self._embedding_service, self._event_embedding_repo
        )

        # Step 7 — find historical analogies (PLAN-F-004: AnalogSearchResultSet)
        ctx = await find_historical_analogies(
            ctx, self._event_embedding_repo, self._settings
        )

        # Step 8 — generate alert text
        ctx = await generate_alert_text(ctx, self._llm_client_sonnet, self._tracer)

        # Step 9 — evaluate alert rules
        ctx = await evaluate_alert_rules(ctx, self._alert_rule_evaluator)

        # Step 10 — dispatch or log silent
        ctx = await dispatch_or_log_silent(ctx, self._alert_dispatcher, self._alert_repo)

        # Step 11 — enqueue deep dive
        ctx = await enqueue_deep_dive(ctx, self._workflow_queue)

        return ctx
