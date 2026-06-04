"""src.ai.prompts.tasks.publish_prompts_task — Celery task for publishing prompts.

PLAN-F-014 TASK-007 (AC-002).

Triggered explicitly on deploy (via ``celery call``) after a merge to main.
This task publishes all prompt files to Langfuse with the 'staging' label,
making the new prompt SHA accessible to agents in the staging environment
without any code changes.

The task is idempotent: publishing the same SHA twice does not create duplicate
Langfuse prompt versions (Langfuse SDK upsert behaviour).

Usage:
    celery call src.ai.prompts.tasks.publish_prompts_task.publish_all_prompts_to_langfuse
"""
from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[5]
PROMPTS_ROOT = _PROJECT_ROOT / "prompts"


@shared_task(
    name="src.ai.prompts.tasks.publish_all_prompts_to_langfuse",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def publish_all_prompts_to_langfuse(self) -> dict:
    """Celery task: publish all prompt files to Langfuse with 'staging' label.

    Called by CI after a merge to main. Idempotent — safe to run multiple times
    for the same commit. Does not fail if Langfuse is unreachable (warnings logged).

    Returns:
        Dict with 'published' count and list of 'role_ids'.
    """
    import asyncio

    from src.ai.prompts.services.prompt_loader_service import PromptLoaderService

    try:
        langfuse_client = _get_langfuse_client()
    except Exception:
        logger.warning("Langfuse client unavailable — prompts will be loaded but not published")
        langfuse_client = None

    service = PromptLoaderService(
        prompts_root=PROMPTS_ROOT,
        langfuse_client=langfuse_client,
        published_by="ci",
    )

    publications = asyncio.get_event_loop().run_until_complete(service.publish_all())

    role_ids = [p.role_id for p in publications]
    logger.info(
        "publish_all_prompts_to_langfuse: published %d prompts: %s",
        len(publications),
        role_ids,
    )
    return {
        "published": len(publications),
        "role_ids": role_ids,
    }


def _get_langfuse_client():
    """Construct a Langfuse client from environment variables, or return None."""
    import os
    from langfuse import Langfuse  # type: ignore

    host = os.environ.get("LANGFUSE_HOST", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")

    if not host or not secret_key:
        return None

    return Langfuse(
        host=host,
        secret_key=secret_key,
        public_key=public_key,
    )
