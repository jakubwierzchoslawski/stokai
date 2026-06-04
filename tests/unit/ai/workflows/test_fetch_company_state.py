"""
Unit tests for fetch_company_state DeterministicNode.

TDD: written before implementation to define expected behavior.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowType
from src.ai.workflows.on_demand.nodes.fetch_company_state import (
    CompanyNotFoundError,
    fetch_company_state,
)


def _make_state(**kwargs) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        **kwargs,
    )


class TestFetchCompanyState:
    @pytest.mark.asyncio
    async def test_fetch_company_state_populates_company_state(self):
        """fetch_company_state sets state.company_state from repo."""
        state = _make_state()
        company_data = {"company_id": str(state.company_id), "name": "ACME Corp"}
        mock_repo = AsyncMock()
        mock_repo.get_company_state.return_value = company_data

        result = await fetch_company_state(state, company_repo=mock_repo)
        assert result.company_state == company_data

    @pytest.mark.asyncio
    async def test_fetch_company_state_raises_company_not_found_error(self):
        """When repo returns None, fetch_company_state raises CompanyNotFoundError."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_company_state.return_value = None

        with pytest.raises(CompanyNotFoundError) as exc_info:
            await fetch_company_state(state, company_repo=mock_repo)
        assert str(state.company_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_company_state_passes_tenant_id_to_repo(self):
        """Repo is called with (company_id, tenant_id) to enforce tenant scope."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_company_state.return_value = {"name": "TestCo"}

        await fetch_company_state(state, company_repo=mock_repo)
        mock_repo.get_company_state.assert_called_once_with(
            state.company_id, state.tenant_id
        )

    @pytest.mark.asyncio
    async def test_fetch_company_state_returns_workflowstate(self):
        """Return type is WorkflowState (not None, not dict)."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_company_state.return_value = {"name": "TestCo"}

        result = await fetch_company_state(state, company_repo=mock_repo)
        assert isinstance(result, WorkflowState)

    @pytest.mark.asyncio
    async def test_fetch_company_state_does_not_mutate_original_state(self):
        """fetch_company_state returns a new state; original is unchanged."""
        state = _make_state()
        mock_repo = AsyncMock()
        mock_repo.get_company_state.return_value = {"name": "ACME"}

        result = await fetch_company_state(state, company_repo=mock_repo)
        assert state.company_state is None   # original unchanged
        assert result.company_state is not None  # new state updated
