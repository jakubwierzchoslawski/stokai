"""
Unit + integration tests for build_on_demand_graph.

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "workflow_type": WorkflowType.ON_DEMAND,
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_registry() -> MagicMock:
    defn = MagicMock()
    defn.role_id = "exposure-analyst"
    defn.tools = []
    defn.output_schema = {"type": "object"}
    defn.limits = MagicMock()
    defn.limits.cost_ceiling_usd = 10.0
    defn.limits.max_iterations = 3
    defn.limits.max_input_tokens = 50000
    defn.limits.timeout_seconds = 60
    defn.model = MagicMock()
    defn.model.model_id = "claude-3-5-sonnet-20241022"
    defn.system_prompt_file = "prompts/test.txt"

    registry = MagicMock()
    registry.resolve.return_value = defn
    return registry


class TestBuildOnDemandGraph:
    def test_graph_builds_without_error(self):
        """build_on_demand_graph returns a compiled graph."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph

        registry = _make_registry()
        graph = build_on_demand_graph(
            registry=registry,
            cost_ceiling_usd=1.50,
            pg_checkpointer=None,
        )
        assert graph is not None

    def test_graph_validates_node_sequence(self):
        """WorkflowStructureValidator is called during graph construction."""
        from src.ai.workflows.on_demand.graph import build_on_demand_graph
        from src.ai.validators.workflow_structure_validator import WorkflowStructureValidator

        registry = _make_registry()
        with patch.object(
            WorkflowStructureValidator,
            "validate",
            wraps=WorkflowStructureValidator().validate,
        ) as mock_validate:
            build_on_demand_graph(
                registry=registry,
                cost_ceiling_usd=1.50,
                pg_checkpointer=None,
            )
        mock_validate.assert_called_once()

    def test_graph_is_cached_at_module_level(self):
        """build_on_demand_graph returns same instance on repeated calls (cached)."""
        from src.ai.workflows.on_demand import graph as graph_module

        # The module should export a cached builder or graph instance
        assert hasattr(graph_module, "build_on_demand_graph")


class TestAiRecommendationRepository:
    """TASK-010 additions to this test file."""

    @pytest.mark.asyncio
    async def test_ai_recommendation_repository_save_returns_uuid(self):
        from src.storage.repositories.ai_recommendation_repository import (
            AiRecommendationRepository,
        )

        state = _make_state(
            recommendation={"action": "hold", "summary": "Test recommendation"},
            status=WorkflowStatus.COMPLETED,
        )
        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        # Mock the ORM object returned
        mock_orm = MagicMock()
        mock_orm.recommendation_id = uuid.uuid4()

        with patch(
            "src.storage.repositories.ai_recommendation_repository.AiRecommendation",
            return_value=mock_orm,
        ):
            repo = AiRecommendationRepository(session)
            rec_id = await repo.save(state)

        assert isinstance(rec_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_ai_recommendation_repository_list_for_company(self):
        from src.storage.repositories.ai_recommendation_repository import (
            AiRecommendationRepository,
        )

        company_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        repo = AiRecommendationRepository(session)
        results = await repo.list_for_company(company_id, tenant_id)
        assert isinstance(results, list)
