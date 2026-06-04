"""
Unit tests for EarningsBriefState, ScenarioTree, and EarningsScenario models.

TDD — PLAN-F-009 TASK-002.

Tests cover:
- ScenarioTree probability sum validation
- EarningsBriefState defaults
- JSON serialization
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.ai.workflows.earnings_brief.state import (
    EarningsBriefState,
    EarningsScenario,
    ScenarioTree,
)
from src.ai.workflows.state import WorkflowStatus


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_scenario(probability: float) -> EarningsScenario:
    return EarningsScenario(
        probability=probability,
        rationale="Test rationale",
        macro_drivers=["macro1"],
        sector_drivers=["sector1"],
    )


def _make_valid_tree(
    bull_p: float = 0.25,
    base_p: float = 0.50,
    bear_p: float = 0.25,
) -> ScenarioTree:
    return ScenarioTree(
        bull=_make_scenario(bull_p),
        base=_make_scenario(base_p),
        bear=_make_scenario(bear_p),
        macro_summary="Macro summary",
        sector_summary="Sector summary",
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


# ── ScenarioTree tests ────────────────────────────────────────────────────────


class TestScenarioTree:
    def test_probabilities_sum_to_one(self):
        """Valid tree with probs 0.25/0.50/0.25 passes validation."""
        tree = _make_valid_tree(0.25, 0.50, 0.25)
        assert tree.bull.probability == 0.25
        assert tree.base.probability == 0.50
        assert tree.bear.probability == 0.25

    def test_probabilities_invalid_sum_raises(self):
        """Probs 0.4/0.4/0.4 raises ValueError (sum = 1.2)."""
        with pytest.raises((ValidationError, ValueError)):
            _make_valid_tree(0.4, 0.4, 0.4)

    def test_probabilities_exactly_1_0_passes(self):
        """Probs 0.30/0.40/0.30 (sum=1.0) passes."""
        tree = _make_valid_tree(0.30, 0.40, 0.30)
        assert tree.bull.probability == 0.30

    def test_probabilities_within_tolerance_passes(self):
        """Sum of 0.999 (within 0.01) passes."""
        tree = _make_valid_tree(0.333, 0.333, 0.333)
        # 0.333+0.333+0.333 = 0.999, within ±0.01
        assert tree is not None

    def test_probabilities_outside_tolerance_raises(self):
        """Sum of 0.98 (outside 0.01 tolerance) raises."""
        with pytest.raises((ValidationError, ValueError)):
            _make_valid_tree(0.30, 0.40, 0.28)  # sum = 0.98

    def test_scenario_tree_has_analogies_default(self):
        """analogies defaults to empty list."""
        tree = _make_valid_tree()
        assert tree.analogies == []

    def test_scenario_tree_macro_and_sector_summaries(self):
        """macro_summary and sector_summary are stored correctly."""
        tree = ScenarioTree(
            bull=_make_scenario(0.30),
            base=_make_scenario(0.50),
            bear=_make_scenario(0.20),
            macro_summary="Fed holds rates",
            sector_summary="Tech earnings mixed",
        )
        assert tree.macro_summary == "Fed holds rates"
        assert tree.sector_summary == "Tech earnings mixed"


# ── EarningsBriefState tests ──────────────────────────────────────────────────


class TestEarningsBriefState:
    def test_status_defaults_to_running(self):
        """status defaults to WorkflowStatus.RUNNING."""
        state = _make_state()
        assert state.status == WorkflowStatus.RUNNING

    def test_cost_usd_defaults_to_zero(self):
        """cost_usd defaults to 0.0."""
        state = _make_state()
        assert state.cost_usd == 0.0

    def test_requires_hil_defaults_to_false(self):
        """requires_hil defaults to False."""
        state = _make_state()
        assert state.requires_hil is False

    def test_confidence_scores_defaults_to_empty_dict(self):
        """confidence_scores defaults to empty dict."""
        state = _make_state()
        assert state.confidence_scores == {}

    def test_serialises_to_json(self):
        """state.model_dump_json() must not raise."""
        state = _make_state()
        json_str = state.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["workflow_type"] == "earnings_brief"

    def test_serialises_with_scenario_tree(self):
        """State with scenario_tree serializes correctly."""
        state = _make_state(scenario_tree=_make_valid_tree())
        json_str = state.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["scenario_tree"]["bull"]["probability"] == 0.25

    def test_workflow_type_is_earnings_brief(self):
        """workflow_type defaults to 'earnings_brief'."""
        state = _make_state()
        assert state.workflow_type == "earnings_brief"

    def test_hil_reason_defaults_to_none(self):
        """hil_reason defaults to None."""
        state = _make_state()
        assert state.hil_reason is None

    def test_error_detail_defaults_to_none(self):
        """error_detail defaults to None."""
        state = _make_state()
        assert state.error_detail is None

    def test_tokens_consumed_defaults_to_empty(self):
        """tokens_consumed defaults to empty dict."""
        state = _make_state()
        assert state.tokens_consumed == {}
