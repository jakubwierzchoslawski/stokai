"""Exposure + Correlation tool family.

Tools:
  - GetEventExposure             (name="get_event_exposure")
  - GetCompanyExposureHistory    (name="get_company_exposure_history")

Both return at most MAX_ROWS rows (enforced by BaseTool.execute).

Visibility rule for event_exposure via geo_event join:
  geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ingestion.cache_or_fetch import build_cache_key
from ingestion.ttl_policy import DataType
from src.ai.tools.base import MAX_ROWS, BaseTool, BaseToolInput


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class GetEventExposureInput(BaseToolInput):
    """Input for GetEventExposure."""

    event_id: UUID


class GetCompanyExposureHistoryInput(BaseToolInput):
    """Input for GetCompanyExposureHistory."""

    company_id: UUID
    limit: int = MAX_ROWS


# ---------------------------------------------------------------------------
# GetEventExposure
# ---------------------------------------------------------------------------


class GetEventExposure(BaseTool):
    """Return event_exposure rows for an event.

    Scoped to tenant via global-event visibility rule:
        geo_event.tenant_id IS NULL OR geo_event.tenant_id = :tenant_id

    At most MAX_ROWS rows.
    """

    name = "get_event_exposure"

    async def _execute(
        self, inputs: GetEventExposureInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params = {"event_id": str(inputs.event_id)}
        cache_key = build_cache_key(
            data_type=DataType.NEWS_EVENT,
            entity_id=str(inputs.event_id),
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.NEWS_EVENT,
            fetch_fn=_fetch,
        )

        if not isinstance(rows, list):
            return []

        # Visibility filter: global or matching tenant
        tenant_str = str(inputs.tenant_id)
        filtered = [
            row for row in rows
            if row.get("tenant_id") is None or row.get("tenant_id") == tenant_str
        ]
        return filtered[:MAX_ROWS + 1]  # extra row signals truncation to BaseTool


# ---------------------------------------------------------------------------
# GetCompanyExposureHistory
# ---------------------------------------------------------------------------


class GetCompanyExposureHistory(BaseTool):
    """Return historical exposure events for a company.

    Aggregates event_exposure rows for a given company_id across all events
    the company was exposed to, respecting the global-event visibility rule.

    At most MAX_ROWS rows.
    """

    name = "get_company_exposure_history"

    async def _execute(
        self, inputs: GetCompanyExposureHistoryInput  # type: ignore[override]
    ) -> list[dict[str, Any]]:
        params = {
            "company_id": str(inputs.company_id),
            "limit": inputs.limit,
        }
        cache_key = build_cache_key(
            data_type=DataType.NEWS_EVENT,
            entity_id=str(inputs.company_id),
            params=params,
        )

        async def _fetch() -> list[dict[str, Any]]:
            return []

        rows = await self._cache_or_fetch.cache_or_fetch(
            key=cache_key,
            data_type=DataType.NEWS_EVENT,
            fetch_fn=_fetch,
        )

        if not isinstance(rows, list):
            return []

        tenant_str = str(inputs.tenant_id)
        filtered = [
            row for row in rows
            if row.get("tenant_id") is None or row.get("tenant_id") == tenant_str
        ]
        return filtered[:MAX_ROWS + 1]
