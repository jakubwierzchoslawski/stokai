"""Repository Protocol interfaces for the scoring module.

PLAN-F-018 TASK-003: Added GeoAdjustedUpdate dataclass and
bulk_update_geo_adjusted method to ICompanyScoreRepository.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.scoring.schemas.indicator import IndicatorRecord, IndicatorVersionRecord
from src.scoring.schemas.company_score import CompanyScoreRecord
from src.scoring.schemas.scoring_profile import ScoringProfileRecord


@dataclass(frozen=True)
class GeoAdjustedUpdate:
    """Immutable value object representing a targeted geo_adjusted write.

    Carries only the fields needed to write a new geo-adjusted snapshot row.
    The implementation reads score/raw_value/percentile/inputs_hash from the
    most recent existing row and combines them with the new geo_adjusted value.
    """

    company_id: UUID
    indicator_id: UUID
    geo_adjusted: float
    computed_at: datetime  # timestamp for the new snapshot row


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

    async def bulk_update_geo_adjusted(
        self, updates: list[GeoAdjustedUpdate]
    ) -> int:
        """Write geo_adjusted values for multiple (company_id, indicator_id) pairs.

        Inserts a new company_score row for each update (event-driven snapshot, D4),
        carrying the existing score/raw_value/percentile/inputs_hash from the most
        recent row but with the new geo_adjusted value and fresh computed_at.

        Groups updates by indicator_id to execute one SELECT + one INSERT batch
        per indicator — O(indicators) DB round-trips, not O(companies).

        Applies epsilon guard: skips a pair if
        abs(new_geo_adjusted - current_geo_adjusted) <= 0.001 — consistent with
        upsert_if_changed.

        Returns:
            The count of rows actually inserted (after epsilon filtering).
        """
        ...


@runtime_checkable
class IScoringProfileRepository(Protocol):
    async def get_by_id(
        self, profile_id: UUID, tenant_id: UUID
    ) -> ScoringProfileRecord | None: ...
    async def list_by_tenant(self, tenant_id: UUID) -> list[ScoringProfileRecord]: ...
    async def save(self, record: ScoringProfileRecord) -> ScoringProfileRecord: ...
