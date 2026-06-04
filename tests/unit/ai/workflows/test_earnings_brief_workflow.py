"""
Unit tests for EarningsBriefWorkflow, EarningsBriefState, and ScenarioTree.

TDD — tests written for PLAN-F-009 TASK-003.

Tests cover:
- ScenarioTree validator: probabilities must sum to 1.0 ± 0.01
- EarningsBriefWorkflow routes to requires_hil=True when confidence < 0.70
- EarningsBriefWorkflow auto_store when confidence >= 0.70
- Cost ceiling stops workflow (WorkflowCostLimitError)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.ai.workflows.earnings_brief.state import (
    EarningsBriefState,
    EarningsScenario,
    ScenarioTree,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_scenario(probability: float) -> EarningsScenario:
    return EarningsScenario(
        probability=probability,
        rationale="Test rationale",
        macro_drivers=["macro1"],
        sector_drivers=["sector1"],
    )


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


def _make_registry(confidence: float = 0.80) -> MagicMock:
    registry = MagicMock()
    defn = MagicMock()
    defn.role_id = "earnings-analyst"
    registry.resolve.return_value = defn
    return registry


_GOOD_LLM_RESULT = {
    "output": {
        "bull": {
            "probability": 0.30,
            "rationale": "Strong results",
            "macro_drivers": ["low rates"],
            "sector_drivers": ["growth"],
        },
        "base": {
            "probability": 0.45,
            "rationale": "In-line results",
            "macro_drivers": ["stable macro"],
            "sector_drivers": ["average"],
        },
        "bear": {
            "probability": 0.25,
            "rationale": "Margin risk",
            "macro_drivers": ["costs"],
            "sector_drivers": ["competition"],
        },
        "analogies": [],
        "macro_summary": "Stable macro",
        "sector_summary": "Sector on track",
    },
    "confidence": 0.80,
    "cost_usd": 0.01,
    "input_tokens": 100,
    "output_tokens": 50,
}

_RECOMMENDATION_RESULT = {
    "output": {"action": "WATCH", "rationale": "Monitor", "confidence": 0.80},
    "confidence": 0.80,
    "cost_usd": 0.01,
    "input_tokens": 50,
    "output_tokens": 25,
}

_NARRATIVE_RESULT = {
    "output": {"title": "Earnings Brief", "sections": [], "text": "Test."},
    "confidence": 0.80,
    "cost_usd": 0.01,
    "input_tokens": 50,
    "output_tokens": 25,
}


# ── ScenarioTree validator tests ──────────────────────────────────────────────


class TestScenarioTreeProbabilities:
    """ScenarioTree.probabilities_sum_to_one validator."""

    def test_valid_probabilities_accepted(self):
        """Probabilities summing to exactly 1.0 are accepted."""
        tree = ScenarioTree(
            bull=_make_scenario(0.30),
            base=_make_scenario(0.45),
            bear=_make_scenario(0.25),
            macro_summary="Stable",
            sector_summary="Normal",
        )
        assert abs(tree.bull.probability + tree.base.probability + tree.bear.probability - 1.0) < 0.01

    def test_probabilities_within_tolerance_accepted(self):
        """Probabilities summing to 0.999 (within 0.01 tolerance) are accepted."""
        tree = ScenarioTree(
            bull=_make_scenario(0.30),
            base=_make_scenario(0.45),
            bear=_make_scenario(0.249),  # sum = 0.999 — within ±0.01
            macro_summary="Stable",
            sector_summary="Normal",
        )
        assert tree is not None

    def test_invalid_probabilities_raise_validation_error(self):
        """Probabilities summing far from 1.0 raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioTree(
                bull=_make_scenario(0.30),
                base=_make_scenario(0.30),  # sum = 0.80 — too far from 1.0
                bear=_make_scenario(0.20),
                macro_summary="Stable",
                sector_summary="Normal",
            )

    def test_probabilities_summing_to_1_15_raise_validation_error(self):
        """Probabilities > 1.0 by more than 0.01 raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioTree(
                bull=_make_scenario(0.40),
                base=_make_scenario(0.50),
                bear=_make_scenario(0.40),  # sum = 1.30 — too high
                macro_summary="Over",
                sector_summary="Over",
            )


# ── EarningsBriefWorkflow routing tests ───────────────────────────────────────


class TestEarningsBriefWorkflowRouting:
    """EarningsBriefWorkflow — confidence routing."""

    def _patch_all_llm_nodes(self, scenario_conf=0.85, rec_conf=0.85, narr_conf=0.85):
        """Return context manager patching all three LLM calls."""
        import unittest.mock as mock

        return mock.patch.multiple(
            "src.ai.workflows.earnings_brief.workflow",
            _invoke_scenario_analyst=AsyncMock(
                return_value={**_GOOD_LLM_RESULT, "confidence": scenario_conf}
            ),
            _invoke_recommendation_agent=AsyncMock(
                return_value={**_RECOMMENDATION_RESULT, "confidence": rec_conf}
            ),
            _invoke_narrative_writer=AsyncMock(
                return_value={**_NARRATIVE_RESULT, "confidence": narr_conf}
            ),
        )

    @pytest.mark.asyncio
    async def test_routes_to_auto_store_on_high_confidence(self):
        """requires_hil=False when all agents return confidence >= 0.70."""
        from src.ai.workflows.earnings_brief.workflow import EarningsBriefWorkflow

        registry = _make_registry()
        workflow = EarningsBriefWorkflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        with self._patch_all_llm_nodes(scenario_conf=0.85, rec_conf=0.85, narr_conf=0.85):
            result = await workflow.ainvoke(state)

        assert result.overall_confidence is not None
        assert result.overall_confidence >= 0.70
        assert result.requires_hil is False

    @pytest.mark.asyncio
    async def test_routes_to_hil_when_confidence_below_0_70(self):
        """requires_hil=True when any agent confidence is 0.40-0.69."""
        from src.ai.workflows.earnings_brief.workflow import EarningsBriefWorkflow

        registry = _make_registry()
        workflow = EarningsBriefWorkflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        # scenario_analyst returns 0.55 — pulls min below 0.70 but above 0.40
        with self._patch_all_llm_nodes(scenario_conf=0.55, rec_conf=0.80, narr_conf=0.80):
            result = await workflow.ainvoke(state)

        assert result.overall_confidence is not None
        assert result.overall_confidence < 0.70
        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_cost_ceiling_stops_workflow(self):
        """WorkflowCostLimitError is raised when cost ceiling is reached."""
        from src.ai.workflows.earnings_brief.workflow import EarningsBriefWorkflow
        from src.ai.workflows.errors import WorkflowCostLimitError

        registry = _make_registry()
        # Set ceiling to $0.001 — any real cost will breach it
        workflow = EarningsBriefWorkflow(registry=registry, cost_ceiling_usd=0.001)
        state = _make_state()

        expensive_result = {**_GOOD_LLM_RESULT, "cost_usd": 0.10}

        with patch(
            "src.ai.workflows.earnings_brief.workflow._invoke_scenario_analyst",
            new_callable=AsyncMock,
            return_value=expensive_result,
        ):
            with pytest.raises(WorkflowCostLimitError):
                await workflow.ainvoke(state)

    @pytest.mark.asyncio
    async def test_ainvoke_returns_earnings_brief_state(self):
        """ainvoke returns an EarningsBriefState instance."""
        from src.ai.workflows.earnings_brief.workflow import EarningsBriefWorkflow

        registry = _make_registry()
        workflow = EarningsBriefWorkflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        with self._patch_all_llm_nodes():
            result = await workflow.ainvoke(state)

        assert isinstance(result, EarningsBriefState)
        assert result.scenario_tree is not None
        assert result.recommendation is not None
        assert result.report is not None


class TestBuildEarningsBriefWorkflow:
    """build_earnings_brief_workflow factory."""

    def test_factory_returns_workflow(self):
        """build_earnings_brief_workflow returns an EarningsBriefWorkflow."""
        from src.ai.workflows.earnings_brief.workflow import (
            build_earnings_brief_workflow,
            EarningsBriefWorkflow,
        )

        registry = _make_registry()
        workflow = build_earnings_brief_workflow(registry=registry, cost_ceiling_usd=5.0)

        assert isinstance(workflow, EarningsBriefWorkflow)
