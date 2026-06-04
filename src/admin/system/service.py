"""
admin.system.service — SystemOpsService orchestrates all system-ops operations.

Wires together repositories, JobRegistry, BudgetGuard, CacheService, and
FeatureFlagService into a single service used by the FastAPI router.

PLAN-F-030 TASK-008
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.admin.system.cache_service import CacheService, InvalidDataTypeError
from src.admin.system.feature_flag_service import FeatureFlagService
from src.ai.budget_guard import BudgetGuard, BudgetHardStopError, BudgetStatus
from src.ingestion.job_registry import JobNotFoundError, JobRegistry, TriggerResponse
from src.storage.models.ingestion_job import IngestionJob, IngestionJobStatus
from src.storage.repositories.cost_record_repo import ICostRecordRepository
from src.storage.repositories.feature_flag_repo import IFeatureFlagRepository
from src.storage.repositories.ingestion_job_repo import IIngestionJobRepository


class SystemOpsService:
    """Façade for all system-ops panel operations.

    Args:
        job_repo: IIngestionJobRepository
        cost_repo: ICostRecordRepository
        flag_repo: IFeatureFlagRepository
        company_repo: CompanyRepository
        job_registry: JobRegistry singleton
        budget_guard: BudgetGuard
        cache_service: CacheService
        flag_service: FeatureFlagService
        tenant_id: The current admin's tenant_id
        environment: The current deployment environment
    """

    def __init__(
        self,
        job_repo: IIngestionJobRepository,
        cost_repo: ICostRecordRepository,
        flag_repo: IFeatureFlagRepository,
        company_repo,
        job_registry: JobRegistry,
        budget_guard: BudgetGuard,
        cache_service: CacheService,
        flag_service: FeatureFlagService,
        tenant_id: uuid.UUID,
        environment: str,
    ) -> None:
        self._job_repo = job_repo
        self._cost_repo = cost_repo
        self._flag_repo = flag_repo
        self._company_repo = company_repo
        self._job_registry = job_registry
        self._budget_guard = budget_guard
        self._cache_service = cache_service
        self._flag_service = flag_service
        self._tenant_id = tenant_id
        self._environment = environment

    # ── Ingestion Jobs ─────────────────────────────────────────────────────────

    async def list_jobs(self) -> list[IngestionJob]:
        return await self._job_repo.list_all(self._tenant_id)

    async def trigger_job(self, job_id: uuid.UUID) -> TriggerResponse:
        return await self._job_registry.trigger_job(
            str(job_id), self._job_repo, self._tenant_id
        )

    # ── Cost Monitor ───────────────────────────────────────────────────────────

    async def get_cost_data(self) -> dict:
        now = datetime.now(timezone.utc)
        status = await self._budget_guard.get_budget_status(self._tenant_id)

        by_source = await self._cost_repo.breakdown_by_source(
            self._tenant_id, now.year, now.month
        )
        by_model = await self._cost_repo.breakdown_by_model(
            self._tenant_id, now.year, now.month
        )
        by_workflow = await self._cost_repo.breakdown_by_workflow(
            self._tenant_id, now.year, now.month
        )

        end = now.date()
        start = end - timedelta(days=29)
        daily = await self._cost_repo.daily_totals(self._tenant_id, start, end)

        return {
            "spend_usd": status.spend_usd,
            "threshold_usd": status.threshold_usd,
            "pct_used": status.pct_used,
            "warning_active": status.warning_active,
            "hard_stop_active": status.hard_stop_active,
            "by_source": by_source,
            "by_model": by_model,
            "by_workflow": by_workflow,
            "daily_totals": daily,
        }

    async def update_threshold(self, threshold_usd: float) -> dict:
        await self._budget_guard.set_threshold(self._tenant_id, threshold_usd)
        return {"threshold_usd": threshold_usd}

    # ── Company Universe ───────────────────────────────────────────────────────

    async def list_companies(self, page: int = 1, page_size: int = 50) -> dict:
        return await self._company_repo.list_tracked(
            self._tenant_id, page, page_size
        )

    async def set_tracked(self, company_id: uuid.UUID, is_tracked: bool) -> dict | None:
        return await self._company_repo.set_tracked(
            company_id, is_tracked, self._tenant_id
        )

    async def search_companies(self, query: str, limit: int = 20) -> list[dict]:
        return await self._company_repo.search_by_name_or_ticker(
            self._tenant_id, query, limit
        )

    # ── Cache Inspection ───────────────────────────────────────────────────────

    async def get_cache_stats(self) -> dict:
        stats = await self._cache_service.get_cache_stats()
        return {
            "price_bars_count": stats.price_bars_count,
            "embeddings_count": stats.embeddings_count,
            "event_data_count": stats.event_data_count,
            "total_redis_memory_bytes": stats.total_redis_memory_bytes,
        }

    async def force_refresh_cache(
        self, data_type: str, company_id: Optional[uuid.UUID] = None
    ) -> dict:
        keys_deleted = await self._cache_service.force_refresh_cache(
            data_type, company_id
        )
        return {"data_type": data_type, "keys_deleted": keys_deleted}

    # ── Feature Flags ──────────────────────────────────────────────────────────

    async def list_flags(self) -> list[dict]:
        flags = await self._flag_repo.list_all(self._environment)
        return [
            {
                "flag_id": f.flag_id,
                "environment": f.environment,
                "enabled": f.enabled,
                "updated_at": f.updated_at.isoformat() if f.updated_at else None,
                "updated_by": str(f.updated_by) if f.updated_by else None,
            }
            for f in flags
        ]

    async def set_flag(
        self, flag_id: str, enabled: bool, updated_by: uuid.UUID
    ) -> dict:
        await self._flag_service.set_enabled(
            flag_id=flag_id,
            enabled=enabled,
            updated_by=updated_by,
            environment=self._environment,
        )
        flag = await self._flag_repo.get(flag_id, self._environment)
        if flag is None:
            return {"flag_id": flag_id, "environment": self._environment, "enabled": enabled}
        return {
            "flag_id": flag.flag_id,
            "environment": flag.environment,
            "enabled": flag.enabled,
            "updated_at": flag.updated_at.isoformat() if flag.updated_at else None,
            "updated_by": str(flag.updated_by) if flag.updated_by else None,
        }
