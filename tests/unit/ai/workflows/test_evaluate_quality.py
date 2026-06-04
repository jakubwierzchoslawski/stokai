"""
Unit tests for evaluate_quality DeterministicNode.

TDD: written before implementation.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.errors import EvaluateQualityError
from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType
from src.ai.workflows.on_demand.nodes.evaluate_quality import evaluate_quality


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


class TestEvaluateQuality:
    def test_evaluate_quality_high_confidence_sets_completed(self):
        """overall_confidence >= 0.7 → status=COMPLETED."""
        state = _make_state(
            confidence_scores={"exposure-analyst": 0.8, "narrative-writer": 0.9}
        )
        result = evaluate_quality(state)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.requires_hil is False

    def test_evaluate_quality_boundary_at_0_7_sets_completed(self):
        """overall_confidence exactly 0.7 → status=COMPLETED (boundary test)."""
        state = _make_state(
            confidence_scores={"exposure-analyst": 0.7, "narrative-writer": 0.9}
        )
        result = evaluate_quality(state)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.overall_confidence == pytest.approx(0.7)

    def test_evaluate_quality_mid_confidence_sets_hil_pending(self):
        """overall_confidence 0.4–0.69 → status=HIL_PENDING."""
        state = _make_state(
            confidence_scores={"exposure-analyst": 0.5, "narrative-writer": 0.8}
        )
        result = evaluate_quality(state)
        assert result.status == WorkflowStatus.HIL_PENDING
        assert result.requires_hil is True
        assert result.hil_reason is not None

    def test_evaluate_quality_boundary_at_0_4_sets_hil_pending(self):
        """overall_confidence exactly 0.4 → status=HIL_PENDING (boundary test)."""
        state = _make_state(
            confidence_scores={"exposure-analyst": 0.4, "narrative-writer": 0.9}
        )
        result = evaluate_quality(state)
        assert result.status == WorkflowStatus.HIL_PENDING
        assert result.overall_confidence == pytest.approx(0.4)

    def test_evaluate_quality_low_confidence_sets_blocked(self):
        """overall_confidence < 0.4 → status=BLOCKED."""
        state = _make_state(
            confidence_scores={"exposure-analyst": 0.3, "narrative-writer": 0.8}
        )
        result = evaluate_quality(state)
        assert result.status == WorkflowStatus.BLOCKED
        assert result.hil_reason is not None

    def test_evaluate_quality_sets_overall_confidence_to_minimum(self):
        """overall_confidence = min(confidence_scores.values())."""
        state = _make_state(
            confidence_scores={
                "exposure-analyst": 0.85,
                "historical-context": 0.72,
                "anomaly-detector": 0.90,
            }
        )
        result = evaluate_quality(state)
        assert result.overall_confidence == pytest.approx(0.72)

    def test_evaluate_quality_raises_on_empty_confidence_scores(self):
        """EvaluateQualityError raised when confidence_scores is empty."""
        state = _make_state(confidence_scores={})
        with pytest.raises(EvaluateQualityError) as exc_info:
            evaluate_quality(state)
        assert "confidence" in str(exc_info.value).lower()
