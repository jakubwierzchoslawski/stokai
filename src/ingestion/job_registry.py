"""
ingestion.job_registry — JobRegistry singleton for Celery-backed ingestion jobs.

Provides:
  - JobRegistry: singleton that maps job_id strings to Celery task names.
  - @register_job decorator to register tasks.
  - JobNotFoundError: raised when triggering an unknown job.
  - TriggerResponse: result of a successful trigger call.

PLAN-F-030 TASK-004
"""
from __future__ import annotations

import dataclasses
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from src.storage.models.ingestion_job import IngestionJobStatus
from src.storage.repositories.ingestion_job_repo import IIngestionJobRepository

logger = logging.getLogger(__name__)


def _make_celery_proxy():
    """Return a lazy proxy for the Celery current_app.

    Importing ``celery`` at module level would cause an ImportError in test
    environments where Celery is not installed.  This proxy only resolves the
    real ``current_app`` on first *call* so tests can patch
    ``src.ingestion.job_registry.celery_app`` with a MagicMock.
    """
    class _CeleryProxy:
        def send_task(self, *args, **kwargs):
            from celery import current_app
            return current_app.send_task(*args, **kwargs)

    return _CeleryProxy()


# Module-level name — patchable by ``patch("src.ingestion.job_registry.celery_app")``
celery_app = _make_celery_proxy()


class JobNotFoundError(Exception):
    """Raised when a job_id is not registered in the JobRegistry."""


@dataclasses.dataclass
class TriggerResponse:
    """Result of a successful job trigger."""

    job_id: str
    task_id: str
    status: str = "running"


class JobRegistry:
    """Singleton registry mapping job_id -> Celery task name.

    Usage::

        registry = JobRegistry.instance()
        registry.register("edgar_ingest", "src.ingestion.tasks.edgar_ingest_task")

        # Or via decorator in tasks.py:
        @register_job("edgar_ingest")
        @app.task
        def edgar_ingest_task(): ...
    """

    _instance: JobRegistry | None = None

    def __init__(self) -> None:
        self._jobs: dict[str, str] = {}  # job_id -> celery task name

    @classmethod
    def instance(cls) -> "JobRegistry":
        """Return the process-wide singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — test helper only."""
        cls._instance = None

    def register(self, job_id: str, task_name: str) -> None:
        """Register a job_id → Celery task name mapping."""
        self._jobs[job_id] = task_name
        logger.debug("JobRegistry: registered job %r → %r", job_id, task_name)

    def get_task_name(self, job_id: str) -> str | None:
        """Return the Celery task name for job_id, or None if unknown."""
        return self._jobs.get(job_id)

    async def trigger_job(
        self,
        job_id: str,
        repo: IIngestionJobRepository,
        tenant_id: uuid.UUID,
    ) -> TriggerResponse:
        """Trigger a job by job_id.

        Steps:
          1. Look up the Celery task name — raise JobNotFoundError if missing.
          2. Call repo.get_by_id to confirm the DB row exists.
          3. send_task via Celery.
          4. set_status(RUNNING) in DB.

        Returns:
            TriggerResponse with job_id and Celery task_id.

        Raises:
            JobNotFoundError: If job_id is not registered.
        """
        task_name = self.get_task_name(job_id)
        if task_name is None:
            raise JobNotFoundError(f"Job {job_id!r} is not registered")

        # Confirm the DB row exists for this tenant
        job_uuid = uuid.UUID(job_id) if not isinstance(job_id, uuid.UUID) else job_id
        job = await repo.get_by_id(job_uuid, tenant_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id!r} not found in database")

        # Send Celery task
        result = celery_app.send_task(task_name)
        task_id = result.id

        # Update DB status
        await repo.set_status(job_uuid, IngestionJobStatus.running)

        logger.info(
            "JobRegistry: triggered job %r as task %r (celery_id=%s)",
            job_id,
            task_name,
            task_id,
        )
        return TriggerResponse(job_id=str(job_id), task_id=task_id)

    async def on_failure(
        self,
        job_id: str,
        repo: IIngestionJobRepository,
        tenant_id: uuid.UUID,
    ) -> None:
        """Mark a job as failed and increment error_count.

        Called from Celery task on_failure hooks.
        """
        try:
            job_uuid = uuid.UUID(job_id) if not isinstance(job_id, uuid.UUID) else job_id
            await repo.set_status(
                job_uuid,
                IngestionJobStatus.failed,
                error_count_delta=1,
            )
            logger.warning("JobRegistry: job %r marked FAILED", job_id)
        except Exception as exc:
            logger.error("JobRegistry.on_failure: could not update job %r: %s", job_id, exc)


def register_job(job_id: str) -> Callable:
    """Decorator that registers the decorated Celery task with the JobRegistry.

    Usage::

        @register_job("edgar_ingest")
        @celery_app.task(name="src.ingestion.tasks.edgar_ingest_task")
        def edgar_ingest_task():
            ...
    """

    def decorator(task_func: Callable) -> Callable:
        # Register using the task's name attribute (set by @app.task)
        task_name = getattr(task_func, "name", task_func.__qualname__)
        JobRegistry.instance().register(job_id, task_name)
        return task_func

    return decorator
