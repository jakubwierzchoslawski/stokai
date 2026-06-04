"""Repository Protocol interfaces for the scoring module."""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.schemas.scoring_profile import ScoringProfileRecord


@runtime_checkable
class IIndicatorRepository(Protocol):
    async def get_by_id(self, indicator_id: UUID, tenant_id: UUID) -> IndicatorRecord | None: ...
    async def list_by_tenant(self, tenant_id: UUID) -> list[IndicatorRecord]: ...
    async def save(self, record: IndicatorRecord) -> IndicatorRecord: ...
    async def get_version(self, indicator_id: UUID, version: int) -> IndicatorVersionRecord | None: ...
    async def list_versions(self, indicator_id: UUID) -> list[IndicatorVersionRecord]: ...


@runtime_checkable
class ICompanyScoreRepository(Protocol):
    async def get_current(
        self, company_id: UUID, indicator_id: UUID
    ) -> CompanyScoreRecord | None: ...
    async def upsert_if_changed(self, record: CompanyScoreRecord) -> bool: ...
    async def get_history(
        self, company_id: UUID, indicator_id: UUID, limit: int = 90
    ) -> list[CompanyScoreRecord]: ...


@runtime_checkable
class IScoringProfileRepository(Protocol):
    async def get_by_id(
        self, profile_id: UUID, tenant_id: UUID
    ) -> ScoringProfileRecord | None: ...
    async def list_by_tenant(self, tenant_id: UUID) -> list[ScoringProfileRecord]: ...
    async def save(self, record: ScoringProfileRecord) -> ScoringProfileRecord: ...
