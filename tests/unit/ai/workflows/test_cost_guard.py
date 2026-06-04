"""
Unit tests for CostCeilingGuard, WorkflowCostLimitError, and WorkflowTimeoutError.

TDD: written before implementation to define exact behavior.
"""
import json
import uuid
from datetime import datetime, timezone

import pytest

from src.ai.workflows.cost_guard import CostCeilingGuard
from src.ai.workflows.errors import WorkflowCostLimitError, WorkflowTimeoutError
from src.ai.workflows.state import WorkflowState, WorkflowType


def _make_state(cost_usd: float = 0.0) -> WorkflowState:
    return WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        cost_usd=cost_usd,
    )


class TestCostCeilingGuard:
    def test_cost_guard_passes_when_under_ceiling(self):
        """cost_usd=1.49 with ceiling 1.50 must not raise."""
        guard = CostCeilingGuard(ceiling_usd=1.50)
        state = _make_state(cost_usd=1.49)
        guard.check(state)  # no exception expected

    def test_cost_guard_raises_at_ceiling(self):
        """cost_usd exactly at ceiling must raise WorkflowCostLimitError."""
        guard = CostCeilingGuard(ceiling_usd=1.50)
        state = _make_state(cost_usd=1.50)
        with pytest.raises(WorkflowCostLimitError) as exc_info:
            guard.check(state)
        assert exc_info.value.accumulated == 1.50
        assert exc_info.value.ceiling == 1.50

    def test_cost_guard_raises_over_ceiling(self):
        """cost_usd=1.51 must raise WorkflowCostLimitError."""
        guard = CostCeilingGuard(ceiling_usd=1.50)
        state = _make_state(cost_usd=1.51)
        with pytest.raises(WorkflowCostLimitError):
            guard.check(state)

    def test_cost_guard_rejects_non_positive_ceiling(self):
        """ceiling_usd=0.0 must raise ValueError (misconfiguration guard)."""
        with pytest.raises(ValueError):
            CostCeilingGuard(ceiling_usd=0.0)

    def test_cost_guard_rejects_negative_ceiling(self):
        """Negative ceiling_usd must also raise ValueError."""
        with pytest.raises(ValueError):
            CostCeilingGuard(ceiling_usd=-1.0)

    def test_cost_guard_stores_ceiling(self):
        guard = CostCeilingGuard(ceiling_usd=1.50)
        assert guard.ceiling_usd == 1.50


class TestWorkflowCostLimitError:
    def test_cost_limit_error_attributes(self):
        """accumulated, ceiling, workflow_id must be accessible as attributes."""
        wf_id = uuid.uuid4()
        err = WorkflowCostLimitError(accumulated=1.55, ceiling=1.50, workflow_id=wf_id)
        assert err.accumulated == 1.55
        assert err.ceiling == 1.50
        assert err.workflow_id == wf_id

    def test_cost_limit_error_to_dict_is_json_serializable(self):
        """to_dict() result must be serializable with json.dumps without error."""
        wf_id = uuid.uuid4()
        err = WorkflowCostLimitError(accumulated=1.55, ceiling=1.50, workflow_id=wf_id)
        d = err.to_dict()
        raw = json.dumps(d)  # must not raise
        parsed = json.loads(raw)
        assert parsed["error"] == "WorkflowCostLimitError"
        assert parsed["workflow_id"] == str(wf_id)
        assert parsed["accumulated_usd"] == 1.55
        assert parsed["ceiling_usd"] == 1.50

    def test_cost_limit_error_is_exception(self):
        wf_id = uuid.uuid4()
        err = WorkflowCostLimitError(accumulated=2.0, ceiling=1.50, workflow_id=wf_id)
        assert isinstance(err, Exception)


class TestWorkflowTimeoutError:
    def test_timeout_error_to_dict_is_json_serializable(self):
        wf_id = uuid.uuid4()
        err = WorkflowTimeoutError(workflow_id=wf_id, elapsed_seconds=310.5)
        raw = json.dumps(err.to_dict())
        parsed = json.loads(raw)
        assert parsed["error"] == "WorkflowTimeoutError"
        assert parsed["workflow_id"] == str(wf_id)
        assert parsed["elapsed_seconds"] == 310.5

    def test_timeout_error_attributes(self):
        wf_id = uuid.uuid4()
        err = WorkflowTimeoutError(workflow_id=wf_id, elapsed_seconds=310.5)
        assert err.workflow_id == wf_id
        assert err.elapsed_seconds == 310.5
