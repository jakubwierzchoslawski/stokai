"""
Celery task wrapper for the Mode A Reactive Pipeline.

Receives a serialised RawEvent dict, deserialises it, instantiates a
PipelineExecutor with production dependencies, and executes the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import os

from celery import shared_task

from src.events.models import RawEvent

logger = logging.getLogger(__name__)


@shared_task(
    name="src.events.celery_tasks.run_pipeline_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def run_pipeline_task(self, raw_event_dict: dict) -> dict:
    """Celery task that runs the Mode A Reactive Pipeline.

    Args:
        raw_event_dict: Serialised RawEvent as a plain dict (JSON-serialisable).

    Returns:
        Serialised PipelineResult as a dict.
    """
    try:
        raw_event = RawEvent(**raw_event_dict)
        executor = _build_executor()
        result = asyncio.run(executor.run(raw_event))
        return result.model_dump(mode="json")
    except Exception as exc:
        logger.error(
            "Pipeline task failed for event %s: %s",
            raw_event_dict.get("source_provider"),
            type(exc).__name__,
        )
        raise self.retry(exc=exc)


def _build_executor():
    """Build a PipelineExecutor with production dependencies."""
    from src.ai.anthropic_client import AnthropicLLMClient
    from src.ai.langfuse_tracer import LangfuseTracer
    from src.ai.openai_embedding_client import OpenAIEmbeddingClient
    from src.alerts.alert_dispatcher import AlertDispatcher
    from src.alerts.alert_rule_evaluator import AlertRuleEvaluator
    from src.config.settings import get_settings
    from src.events.pipeline_executor import PipelineExecutor
    from src.storage.implementations.alert_repository import AlertRepository
    from src.storage.implementations.event_embedding_repository import (
        EventEmbeddingRepository,
    )
    from src.storage.implementations.event_exposure_repository import (
        EventExposureRepository,
    )
    from src.storage.implementations.geo_event_repository import GeoEventRepository

    settings = get_settings()

    # For Celery sync tasks we need a synchronous DB session via a new async engine
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(settings.DATABASE_URL)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # We run the async session inside asyncio.run() in the task, so create a
    # module-level session factory and bind it per-call.
    session = async_session_factory()

    # Placeholder user email resolver (production would query user table)
    def resolve_email(user_id) -> str:
        return "alerts@stokai.com"

    twitter_enabled = os.environ.get("TWITTER_ENABLED", "false").lower() == "true"

    return PipelineExecutor(
        geo_event_repo=GeoEventRepository(session),
        event_exposure_repo=EventExposureRepository(session),
        event_embedding_repo=EventEmbeddingRepository(session),
        alert_repo=AlertRepository(session),
        llm_client_haiku=AnthropicLLMClient(
            api_key=settings.ANTHROPIC_API_KEY,
            default_model="claude-haiku-4-5",
        ),
        llm_client_sonnet=AnthropicLLMClient(
            api_key=settings.ANTHROPIC_API_KEY,
            default_model="claude-sonnet-4-6",
        ),
        embedding_client=OpenAIEmbeddingClient(api_key=settings.OPENAI_API_KEY),
        tracer=LangfuseTracer(
            secret_key=settings.LANGFUSE_SECRET_KEY,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            host=settings.LANGFUSE_HOST,
        ),
        alert_rule_evaluator=AlertRuleEvaluator(session),
        alert_dispatcher=AlertDispatcher(
            sendgrid_api_key=settings.SENDGRID_API_KEY,
            from_email="alerts@stokai.com",
            user_email_resolver=resolve_email,
        ),
        workflow_queue=_CeleryWorkflowQueue(),
        db_session=session,
        twitter_enabled=twitter_enabled,
    )


class _CeleryWorkflowQueue:
    """Celery-backed IWorkflowQueue implementation."""

    def enqueue(self, workflow_type: str, inputs: dict, priority: str, scheduled_for) -> None:
        from src.config.celery_app import celery_app

        eta = scheduled_for
        celery_app.send_task(
            f"src.events.workflows.{workflow_type}",
            kwargs=inputs,
            eta=eta,
            priority=0 if priority == "high" else 5,
        )
