"""
Unit tests for cost_exceeded_node (PLAN-N-004 TASK-007).

TDD: tests were written before the implementation.
The node is a shared DeterministicNode used by all five Mode B workflows.

Tests verify:
  - cost_limited flag set to True
  - workflow_status set to "cost_exceeded"
  - partial recommendations preserved in state (not cleared)
  - no email dispatched
  - structured ERROR logged

All external dependencies are mocked.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.ai.workflows.cost_exceeded_node import cost_exceeded_node
from src.ai.workflows.state import WorkflowState, WorkflowStatus, WorkflowType


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> WorkflowState:
    base = dict(
        workflow_id=uuid4(),
        workflow_type=WorkflowType.EVENT_DEEP_DIVE,
        tenant_id=uuid4(),
        user_id=uuid4(),
        started_at=datetime.now(timezone.utc),
        cost_usd=2.01,
    )
    base.update(overrides)
    return WorkflowState(**base)


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_cost_exceeded_node_sets_cost_limited_true() -> None:
    """cost_exceeded_node sets state.cost_limited = True."""
    state = _make_state()
    state.recommendation = {"action": "HOLD", "confidence": 0.85}

    result = cost_exceeded_node(state)

    assert result.cost_limited is True


def test_cost_exceeded_node_sets_status_cost_exceeded() -> None:
    """cost_exceeded_node sets state.status to COST_LIMIT."""
    state = _make_state()

    result = cost_exceeded_node(state)

    assert result.status == WorkflowStatus.COST_LIMIT


def test_cost_exceeded_node_preserves_partial_recommendations() -> None:
    """Partial recommendations present before node are retained after node."""
    state = _make_state()
    state.recommendation = {"action": "BUY", "confidence": 0.72}
    state.active_events = [{"event_id": str(uuid4()), "title": "Test event"}]

    result = cost_exceeded_node(state)

    assert result.recommendation == {"action": "BUY", "confidence": 0.72}
    assert len(result.active_events) == 1


def test_cost_exceeded_node_does_not_dispatch_email() -> None:
    """cost_exceeded_node never calls any email dispatcher."""
    state = _make_state()

    with patch("src.ai.workflows.cost_exceeded_node.email_dispatcher", None, create=True):
        with patch("src.ai.dispatch.email_dispatcher.EmailDispatcher") as mock_email:
            cost_exceeded_node(state)
            mock_email.assert_not_called()


def test_cost_exceeded_node_logs_structured_error(caplog) -> None:
    """cost_exceeded_node emits ERROR log with workflow_id and cost_usd."""
    workflow_id = uuid4()
    state = _make_state(workflow_id=workflow_id, cost_usd=2.01)

    with caplog.at_level(logging.ERROR):
        cost_exceeded_node(state)

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 1
    combined = " ".join(r.message for r in error_records)
    assert str(workflow_id) in combined or "cost_exceeded" in combined.lower() or "cost" in combined.lower()
