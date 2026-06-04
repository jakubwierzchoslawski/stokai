"""
Unit tests for evaluate_quality DeterministicNode.

TDD — PLAN-F-009 TASK-007.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from src.ai.workflows.earnings_brief.nodes.evaluate_quality import evaluate_quality
from src.ai.workflows.earnings_brief.state import EarningsBriefState
from src.ai.workflows.errors import EvaluateQualityError
from src.ai.workflows.state import WorkflowStatus


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


class TestEvaluateQuality:
    def test_high_confidence_sets_completed(self):
        """Min confidence 0.75 → COMPLETED, requires_hil=False."""
        state = _make_state(
            confidence_scores={
                "earnings_context_agent": 0.75,
                "historical_context_agent": 0.80,
                "recommendation_synthesizer": 0.85,
            }
        )
        result = evaluate_quality(state)

        assert result.status == WorkflowStatus.COMPLETED
        assert result.requires_hil is False
        assert result.overall_confidence == pytest.approx(0.75)

    def test_mid_confidence_sets_hil_pending(self):
        """Min confidence 0.55 → HIL_PENDING, requires_hil=True."""
        state = _make_state(
            confidence_scores={
                "earnings_context_agent": 0.55,
                "historical_context_agent": 0.80,
            }
        )
        result = evaluate_quality(state)

        assert result.status == WorkflowStatus.HIL_PENDING
        assert result.requires_hil is True
        assert result.hil_reason == "Confidence below auto-send threshold"

    def test_low_confidence_sets_blocked(self):
        """Min confidence 0.3 → BLOCKED."""
        state = _make_state(
            confidence_scores={
                "earnings_context_agent": 0.3,
                "historical_context_agent": 0.8,
            }
        )
        result = evaluate_quality(state)

        assert result.status == WorkflowStatus.BLOCKED
        assert result.requires_hil is False
        assert result.hil_reason == "Confidence too low to deliver"

    def test_uses_minimum_not_average(self):
        """Scores [0.9, 0.9, 0.35] → overall_confidence=0.35."""
        state = _make_state(
            confidence_scores={
                "a": 0.9,
                "b": 0.9,
                "c": 0.35,
            }
        )
        result = evaluate_quality(state)

        assert result.overall_confidence == pytest.approx(0.35)
        assert result.status == WorkflowStatus.BLOCKED

    def test_empty_scores_raises(self):
        """confidence_scores={} → EvaluateQualityError."""
        state = _make_state(confidence_scores={})

        with pytest.raises(EvaluateQualityError):
            evaluate_quality(state)

    def test_boundary_0_7_inclusive_is_completed(self):
        """Score exactly 0.7 → COMPLETED."""
        state = _make_state(confidence_scores={"agent": 0.7})
        result = evaluate_quality(state)

        assert result.status == WorkflowStatus.COMPLETED

    def test_boundary_0_4_inclusive_is_hil_pending(self):
        """Score exactly 0.4 → HIL_PENDING."""
        state = _make_state(confidence_scores={"agent": 0.4})
        result = evaluate_quality(state)

        assert result.status == WorkflowStatus.HIL_PENDING
