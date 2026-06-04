"""Unit tests for AuditService — workflow history and re-run operations.

PLAN-F-029 TASK-005
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.admin.audit.audit_service import AuditService, NotFoundError
from src.api.admin.audit.audit_api_schemas import RerunRequest


# ── Helpers ────────────────────────────────────────────────────────────────────

ADMIN_USER_ID = uuid.uuid4()


def _make_service(episodic_repo=None, workflow_runner=None) -> AuditService:
    return AuditService(
        decision_repo=AsyncMock(),
        feedback_repo=AsyncMock(),
        golden_dataset_service=AsyncMock(),
        prompt_label_service=AsyncMock(),
        prompt_publication_repo=AsyncMock(),
        evaluation_repo=AsyncMock(),
        episodic_repo=episodic_repo or AsyncMock(),
        workflow_runner=workflow_runner or AsyncMock(),
        calibration_repo=AsyncMock(),
        calibration_service=AsyncMock(),
    )


def _make_run(**kwargs):
    run = MagicMock()
    run.workflow_id = kwargs.get("workflow_id", uuid.uuid4())
    run.workflow_type = kwargs.get("workflow_type", "mode_b_analysis")
    run.status = kwargs.get("status", "completed")
    run.started_at = kwargs.get("started_at", datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc))
    run.completed_at = kwargs.get("completed_at", None)
    run.cost_usd = kwargs.get("cost_usd", 0.05)
    run.langfuse_trace_id = kwargs.get("langfuse_trace_id", None)
    run.final_state = kwargs.get("final_state", {"inputs": {"company": "AAPL"}})
    return run


def _make_inv(**kwargs):
    inv = MagicMock()
    inv.invocation_id = kwargs.get("invocation_id", uuid.uuid4())
    inv.agent_role_id = kwargs.get("agent_role_id", "narrative_writer")
    inv.model_used = kwargs.get("model_used", "claude-haiku")
    inv.prompt_version = kwargs.get("prompt_version", "abc1234")
    inv.confidence = kwargs.get("confidence", 0.85)
    inv.cost_usd = kwargs.get("cost_usd", 0.01)
    inv.duration_ms = kwargs.get("duration_ms", 500)
    inv.input_tokens = kwargs.get("input_tokens", 100)
    inv.output_tokens = kwargs.get("output_tokens", 200)
    return inv


def _make_tc(**kwargs):
    tc = MagicMock()
    tc.tool_call_id = kwargs.get("tool_call_id", uuid.uuid4())
    tc.invocation_id = kwargs.get("invocation_id", uuid.uuid4())
    tc.tool_name = kwargs.get("tool_name", "search_analogues")
    tc.duration_ms = kwargs.get("duration_ms", 100)
    tc.cost_tier = kwargs.get("cost_tier", "free")
    tc.cached = kwargs.get("cached", False)
    return tc


# ── list_workflow_runs ─────────────────────────────────────────────────────────

class TestListWorkflowRuns:
    @pytest.mark.asyncio
    async def test_returns_summaries_with_correct_fields(self):
        run = _make_run()
        episodic_repo = AsyncMock()
        episodic_repo.list_recent_runs = AsyncMock(return_value=([run], None))

        service = _make_service(episodic_repo=episodic_repo)
        results, cursor = await service.list_workflow_runs(cursor=None, limit=10)

        assert len(results) == 1
        assert results[0].workflow_type == "mode_b_analysis"
        assert cursor is None

    @pytest.mark.asyncio
    async def test_cursor_pagination_two_pages_no_overlap(self):
        run1 = _make_run(workflow_id=uuid.uuid4())
        run2 = _make_run(workflow_id=uuid.uuid4())

        episodic_repo = AsyncMock()
        episodic_repo.list_recent_runs = AsyncMock(return_value=([run1], "cursor_page2"))

        service = _make_service(episodic_repo=episodic_repo)
        results1, cursor1 = await service.list_workflow_runs(cursor=None, limit=1)

        # Page 2 uses returned cursor
        episodic_repo.list_recent_runs = AsyncMock(return_value=([run2], None))
        results2, cursor2 = await service.list_workflow_runs(cursor=cursor1, limit=1)

        wf_ids_1 = {r.workflow_id for r in results1}
        wf_ids_2 = {r.workflow_id for r in results2}
        assert wf_ids_1.isdisjoint(wf_ids_2), "Pages must not overlap"


# ── get_workflow_detail ────────────────────────────────────────────────────────

class TestGetWorkflowDetail:
    @pytest.mark.asyncio
    async def test_returns_detail_with_agent_invocations_and_tool_calls(self):
        run_id = uuid.uuid4()
        run = _make_run(workflow_id=run_id)
        inv_id = uuid.uuid4()
        inv = _make_inv(invocation_id=inv_id)
        tc = _make_tc(invocation_id=inv_id)

        episodic_repo = AsyncMock()
        episodic_repo.get_workflow_run = AsyncMock(return_value=run)
        episodic_repo.list_invocations_for_run = AsyncMock(return_value=[inv])
        episodic_repo.list_tool_calls_for_run = AsyncMock(return_value=[tc])

        service = _make_service(episodic_repo=episodic_repo)
        detail = await service.get_workflow_detail(run_id)

        assert detail.workflow_id == run_id
        assert len(detail.agent_invocations) == 1
        assert len(detail.agent_invocations[0].tool_calls) == 1

    @pytest.mark.asyncio
    async def test_raises_not_found_when_absent(self):
        episodic_repo = AsyncMock()
        episodic_repo.get_workflow_run = AsyncMock(return_value=None)

        service = _make_service(episodic_repo=episodic_repo)

        with pytest.raises(NotFoundError):
            await service.get_workflow_detail(uuid.uuid4())


# ── rerun_workflow ─────────────────────────────────────────────────────────────

class TestRerunWorkflow:
    @pytest.mark.asyncio
    async def test_dispatches_with_correct_workflow_type_and_inputs(self):
        wf_id = uuid.uuid4()
        inputs = {"company": "AAPL", "mode": "full"}
        run = _make_run(
            workflow_id=wf_id,
            workflow_type="mode_b_analysis",
            final_state={"inputs": inputs},
        )
        new_wf_id = uuid.uuid4()

        episodic_repo = AsyncMock()
        episodic_repo.get_workflow_run = AsyncMock(return_value=run)
        workflow_runner = AsyncMock()
        workflow_runner.dispatch = AsyncMock(return_value=new_wf_id)

        service = _make_service(episodic_repo=episodic_repo, workflow_runner=workflow_runner)
        result = await service.rerun_workflow(RerunRequest(workflow_id=wf_id), ADMIN_USER_ID)

        workflow_runner.dispatch.assert_called_once_with(
            workflow_type="mode_b_analysis", inputs=inputs
        )

    @pytest.mark.asyncio
    async def test_returns_new_workflow_id(self):
        wf_id = uuid.uuid4()
        run = _make_run(workflow_id=wf_id)
        new_wf_id = uuid.uuid4()

        episodic_repo = AsyncMock()
        episodic_repo.get_workflow_run = AsyncMock(return_value=run)
        workflow_runner = AsyncMock()
        workflow_runner.dispatch = AsyncMock(return_value=new_wf_id)

        service = _make_service(episodic_repo=episodic_repo, workflow_runner=workflow_runner)
        result = await service.rerun_workflow(RerunRequest(workflow_id=wf_id), ADMIN_USER_ID)

        assert result.new_workflow_id == new_wf_id

    @pytest.mark.asyncio
    async def test_raises_not_found_when_source_absent(self):
        episodic_repo = AsyncMock()
        episodic_repo.get_workflow_run = AsyncMock(return_value=None)

        service = _make_service(episodic_repo=episodic_repo)

        with pytest.raises(NotFoundError):
            await service.rerun_workflow(
                RerunRequest(workflow_id=uuid.uuid4()), ADMIN_USER_ID
            )
