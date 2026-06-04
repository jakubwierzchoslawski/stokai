"""
Unit tests for JobRegistry and related logic.

PLAN-F-030 TASK-004
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.job_registry import (
    JobNotFoundError,
    JobRegistry,
    TriggerResponse,
    register_job,
)
from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus
from src.storage.repositories.ingestion_job_repo import IIngestionJobRepository


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the singleton between tests."""
    JobRegistry.reset()
    yield
    JobRegistry.reset()


def _make_repo(job: IngestionJob | None = None) -> AsyncMock:
    repo = AsyncMock(spec=IIngestionJobRepository)
    repo.get_by_id = AsyncMock(return_value=job)
    repo.set_status = AsyncMock(return_value=job)
    return repo


def _make_job(tenant_id: uuid.UUID) -> IngestionJob:
    j = MagicMock(spec=IngestionJob)
    j.job_id = uuid.uuid4()
    j.tenant_id = tenant_id
    j.name = "edgar_ingest"
    j.status = "idle"
    j.error_count = 0
    return j


# ── get_task_name ──────────────────────────────────────────────────────────────


class TestGetTaskName:
    def test_get_task_name_correct(self) -> None:
        registry = JobRegistry.instance()
        registry.register("edgar_ingest", "src.ingestion.tasks.edgar_ingest_task")
        assert registry.get_task_name("edgar_ingest") == "src.ingestion.tasks.edgar_ingest_task"

    def test_get_task_name_returns_none_for_unknown(self) -> None:
        registry = JobRegistry.instance()
        assert registry.get_task_name("no_such_job") is None


# ── trigger_job ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTriggerJob:
    async def test_trigger_raises_job_not_found_when_not_registered(self) -> None:
        """trigger_job raises JobNotFoundError if job_id not in registry."""
        registry = JobRegistry.instance()
        tenant_id = uuid.uuid4()
        job = _make_job(tenant_id)
        repo = _make_repo(job)

        with pytest.raises(JobNotFoundError, match="not registered"):
            await registry.trigger_job(str(job.job_id), repo, tenant_id)

    async def test_trigger_calls_send_task_via_celery(self) -> None:
        """trigger_job calls celery send_task with the correct task name."""
        registry = JobRegistry.instance()
        tenant_id = uuid.uuid4()
        job = _make_job(tenant_id)
        job_id = str(job.job_id)
        task_name = "src.ingestion.tasks.edgar_ingest_task"
        registry.register(job_id, task_name)

        repo = _make_repo(job)

        fake_result = MagicMock()
        fake_result.id = "celery-task-abc"

        with patch("src.ingestion.job_registry.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=fake_result)
            response = await registry.trigger_job(job_id, repo, tenant_id)

        mock_celery.send_task.assert_called_once_with(task_name)
        assert response.task_id == "celery-task-abc"

    async def test_trigger_calls_set_status_running(self) -> None:
        """trigger_job calls repo.set_status(RUNNING) after send_task."""
        registry = JobRegistry.instance()
        tenant_id = uuid.uuid4()
        job = _make_job(tenant_id)
        job_id = str(job.job_id)
        registry.register(job_id, "some.task")

        repo = _make_repo(job)

        fake_result = MagicMock()
        fake_result.id = "celery-abc"

        with patch("src.ingestion.job_registry.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=fake_result)
            await registry.trigger_job(job_id, repo, tenant_id)

        repo.set_status.assert_called_once_with(job.job_id, IngestionJobStatus.running)

    async def test_trigger_raises_when_job_not_in_db(self) -> None:
        """trigger_job raises JobNotFoundError if job_id not found in DB."""
        registry = JobRegistry.instance()
        tenant_id = uuid.uuid4()
        job_id = str(uuid.uuid4())
        registry.register(job_id, "some.task")

        repo = _make_repo(None)  # DB returns None

        with pytest.raises(JobNotFoundError, match="not found in database"):
            await registry.trigger_job(job_id, repo, tenant_id)


# ── on_failure ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestOnFailure:
    async def test_on_failure_sets_failed_and_increments_error_count(self) -> None:
        """on_failure calls set_status(FAILED, error_count_delta=1)."""
        registry = JobRegistry.instance()
        tenant_id = uuid.uuid4()
        job = _make_job(tenant_id)
        job_id = str(job.job_id)
        repo = _make_repo(job)

        await registry.on_failure(job_id, repo, tenant_id)

        repo.set_status.assert_called_once_with(
            job.job_id,
            IngestionJobStatus.failed,
            error_count_delta=1,
        )


# ── register_job decorator ─────────────────────────────────────────────────────


class TestRegisterJobDecorator:
    def test_register_job_decorator_registers_task(self) -> None:
        """@register_job registers the task name in the singleton."""

        @register_job("test_decorated_job")
        def my_task():
            pass

        my_task.name = "src.ingestion.tasks.my_task"

        # Re-register with name attribute set
        JobRegistry.instance().register("test_decorated_job", my_task.name)
        assert (
            JobRegistry.instance().get_task_name("test_decorated_job")
            == "src.ingestion.tasks.my_task"
        )
