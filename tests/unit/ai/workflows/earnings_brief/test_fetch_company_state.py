"""
Unit tests for fetch_company_state DeterministicNode.

TDD — PLAN-F-009 TASK-004.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.workflows.earnings_brief.nodes.context import NodeContext
from src.ai.workflows.earnings_brief.nodes.fetch_company_state import (
    CompanyNotFoundError,
    fetch_company_state,
)
from src.ai.workflows.earnings_brief.state import EarningsBriefState


def _make_state(**kwargs) -> EarningsBriefState:
    defaults = dict(
        workflow_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        earnings_date=date.today(),
        started_at=datetime.now(tz=timezone.utc),
    )
    defaults.update(kwargs)
    return EarningsBriefState(**defaults)


class TestFetchCompanyState:
    @pytest.mark.asyncio
    async def test_populates_state(self):
        """Mock repository returns company fixture; asserts state.company_state set."""
        state = _make_state()
        company_mock = MagicMock()
        company_mock.model_dump.return_value = {"company_id": str(state.company_id)}

        repo = AsyncMock()
        repo.get = AsyncMock(return_value=company_mock)
        ctx = NodeContext(company_repo=repo)

        result = await fetch_company_state(state, ctx)

        assert result.company_state is not None
        assert "company" in result.company_state

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        """Repository returns None; CompanyNotFoundError raised."""
        state = _make_state()
        repo = AsyncMock()
        repo.get = AsyncMock(return_value=None)
        ctx = NodeContext(company_repo=repo)

        with pytest.raises(CompanyNotFoundError):
            await fetch_company_state(state, ctx)

    @pytest.mark.asyncio
    async def test_scoped_to_tenant(self):
        """Asserts repository called with tenant_id."""
        state = _make_state()
        company_mock = MagicMock()
        company_mock.model_dump.return_value = {"company_id": str(state.company_id)}

        repo = AsyncMock()
        repo.get = AsyncMock(return_value=company_mock)
        ctx = NodeContext(company_repo=repo)

        await fetch_company_state(state, ctx)

        repo.get.assert_called_once_with(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
        )

    @pytest.mark.asyncio
    async def test_stub_when_no_repo(self):
        """Without a company_repo, returns stub company_state."""
        state = _make_state()
        ctx = NodeContext()

        result = await fetch_company_state(state, ctx)

        assert result.company_state is not None
        # The stub nests under "company" key
        company_data = result.company_state.get("company", {})
        assert company_data.get("stub") is True
