"""
Unit tests for TrackedCompany model and ICompanyRepository.get_tracked_companies.

Tests:
  - test_get_tracked_companies_returns_only_tracked   AC-001
  - test_get_tracked_companies_tenant_scoped          AC-001
  - test_tracked_company_market_cap_weight_normalized AC-001

All DB interactions are mocked via AsyncMock so no real database is required.

PLAN-F-003 TASK-001.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.event_pipeline.exposure_mapping import TrackedCompany
from src.storage.repositories.company_exposure_repository import (
    CompanyExposureRepository,
    ICompanyRepository,
)


def _make_row(
    company_id: uuid.UUID | None = None,
    sector_internal: str = "energy",
    sector_gics: str = "Energy",
    geo_revenue: dict | None = None,
    market_cap_weight: float = 0.5,
) -> dict:
    return {
        "company_id": company_id or uuid.uuid4(),
        "sector_internal": sector_internal,
        "sector_gics": sector_gics,
        "geo_revenue": geo_revenue or {"EMEA": 0.6, "APAC": 0.4},
        "market_cap_weight": market_cap_weight,
    }


@pytest.mark.asyncio
class TestGetTrackedCompanies:
    """get_tracked_companies returns only is_tracked=True rows, scoped to tenant."""

    async def test_get_tracked_companies_returns_only_tracked(self) -> None:
        """Repository returns tracked companies (DB query filters is_tracked=TRUE)."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        row_a = _make_row(market_cap_weight=0.6)
        row_b = _make_row(sector_internal="materials", market_cap_weight=0.4)

        result_mock = MagicMock()
        result_mock.mappings.return_value = [row_a, row_b]
        session.execute = AsyncMock(return_value=result_mock)

        repo = CompanyExposureRepository(session)
        companies = await repo.get_tracked_companies(tenant_id)

        assert len(companies) == 2
        assert all(isinstance(c, TrackedCompany) for c in companies)
        session.execute.assert_called_once()

    async def test_get_tracked_companies_tenant_scoped(self) -> None:
        """The SQL query is parameterised with the provided tenant_id."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.mappings.return_value = [_make_row()]
        session.execute = AsyncMock(return_value=result_mock)

        repo = CompanyExposureRepository(session)
        await repo.get_tracked_companies(tenant_id)

        call_args = session.execute.call_args
        params = call_args[0][1]  # second positional arg is the bind params dict
        assert "tenant_id" in params
        assert params["tenant_id"] == tenant_id

    async def test_tracked_company_market_cap_weight_normalized(self) -> None:
        """market_cap_weight values returned by the repo reflect normalised DB values."""
        session = AsyncMock()
        tenant_id = uuid.uuid4()

        # Simulate DB returning already-normalised weights (0.6 + 0.4 = 1.0)
        row_a = _make_row(market_cap_weight=0.6)
        row_b = _make_row(market_cap_weight=0.4)

        result_mock = MagicMock()
        result_mock.mappings.return_value = [row_a, row_b]
        session.execute = AsyncMock(return_value=result_mock)

        repo = CompanyExposureRepository(session)
        companies = await repo.get_tracked_companies(tenant_id)

        total_weight = sum(c.market_cap_weight for c in companies)
        # Weights from the mock DB already sum to 1.0; the repo must preserve them.
        assert abs(total_weight - 1.0) < 1e-9

    async def test_get_tracked_companies_empty_when_none_tracked(self) -> None:
        """Returns empty list when the DB has no tracked companies for the tenant."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.mappings.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = CompanyExposureRepository(session)
        companies = await repo.get_tracked_companies(uuid.uuid4())

        assert companies == []

    async def test_icompany_repository_protocol_satisfied(self) -> None:
        """CompanyExposureRepository satisfies the ICompanyRepository protocol."""
        session = AsyncMock()
        repo = CompanyExposureRepository(session)
        assert isinstance(repo, ICompanyRepository)
