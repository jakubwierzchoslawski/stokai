"""Unit tests for AuditService — decision log and override operations.

PLAN-F-029 TASK-003
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.decision_log.schemas.ai_decision_schemas import (
    AIDecisionDetail,
    AIDecisionRow,
    DecisionLogFilter,
)
from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem
from src.ai.memory.schemas.feedback_schemas import FeedbackType, UserFeedback
from src.api.admin.audit.audit_api_schemas import (
    AdminOverrideRequest,
    AdminOverrideResponse,
)
from src.api.admin.audit.audit_service import AuditService, NotFoundError


# ── Helpers ────────────────────────────────────────────────────────────────────

TENANT_ID = uuid.uuid4()
ADMIN_USER_ID = uuid.uuid4()
DECISION_ID = uuid.uuid4()
FEEDBACK_ID = uuid.uuid4()
CANDIDATE_ID = uuid.uuid4()


def _make_detail(**kwargs) -> AIDecisionDetail:
    defaults = dict(
        decision_id=DECISION_ID,
        agent_role="narrative_writer",
        model="claude-haiku",
        prompt_version="abc1234" * 5,
        confidence=0.75,
        inputs_summary="Summary",
        inputs_full='{"event": "data"}',
        retrieved_analogs=[{"ticker": "AAPL"}, {"ticker": "MSFT"}],
        action_signal="HOLD",
        company_ticker="AAPL",
        output_text="Output text",
        langfuse_trace_url="https://langfuse.example.com/trace/abc",
        workflow_run_id=None,
        created_at=datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return AIDecisionDetail(**defaults)


def _make_service(
    decision_repo=None,
    feedback_repo=None,
    golden_dataset_service=None,
) -> AuditService:
    return AuditService(
        decision_repo=decision_repo or AsyncMock(),
        feedback_repo=feedback_repo or AsyncMock(),
        golden_dataset_service=golden_dataset_service or AsyncMock(),
        prompt_label_service=AsyncMock(),
        prompt_publication_repo=AsyncMock(),
        evaluation_repo=AsyncMock(),
        episodic_repo=AsyncMock(),
        workflow_runner=AsyncMock(),
        calibration_repo=AsyncMock(),
        calibration_service=AsyncMock(),
    )


# ── list_decisions ─────────────────────────────────────────────────────────────

class TestListDecisions:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self):
        row = MagicMock(spec=AIDecisionRow)
        decision_repo = AsyncMock()
        decision_repo.list_paginated = AsyncMock(return_value=([row], None))
        service = _make_service(decision_repo=decision_repo)

        results, cursor = await service.list_decisions(DecisionLogFilter())
        assert results == [row]
        assert cursor is None
        decision_repo.list_paginated.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_filters_to_repository(self):
        decision_repo = AsyncMock()
        decision_repo.list_paginated = AsyncMock(return_value=([], None))
        service = _make_service(decision_repo=decision_repo)

        filters = DecisionLogFilter(confidence_min=0.7, agent_role="classifier")
        await service.list_decisions(filters)
        call_args = decision_repo.list_paginated.call_args
        passed_filters = call_args[0][0]
        assert passed_filters.confidence_min == 0.7
        assert passed_filters.agent_role == "classifier"


# ── get_decision_detail ────────────────────────────────────────────────────────

class TestGetDecisionDetail:
    @pytest.mark.asyncio
    async def test_returns_detail_when_found(self):
        detail = _make_detail()
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=detail)
        service = _make_service(decision_repo=decision_repo)

        result = await service.get_decision_detail(DECISION_ID)
        assert result.decision_id == DECISION_ID

    @pytest.mark.asyncio
    async def test_raises_not_found_when_absent(self):
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=None)
        service = _make_service(decision_repo=decision_repo)

        with pytest.raises(NotFoundError):
            await service.get_decision_detail(uuid.uuid4())


# ── apply_override ─────────────────────────────────────────────────────────────

class TestApplyOverride:
    def _make_feedback_result(self) -> UserFeedback:
        return UserFeedback(
            feedback_id=FEEDBACK_ID,
            tenant_id=TENANT_ID,
            feedback_type="reject_with_feedback",
            source="hil_action",
            submitted_at=datetime.now(timezone.utc),
        )

    def _make_candidate_result(self) -> GoldenDatasetItem:
        return GoldenDatasetItem(
            item_id=CANDIDATE_ID,
            input={},
            expected_output={},
            quality_metrics={},
            source="admin_override",
            active=False,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_calls_feedback_repo_with_admin_override_type(self):
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=_make_detail())
        feedback_repo = AsyncMock()
        feedback_repo.append_feedback = AsyncMock(return_value=self._make_feedback_result())
        golden_svc = AsyncMock()
        golden_svc.create_candidate = AsyncMock(return_value=self._make_candidate_result())

        service = _make_service(
            decision_repo=decision_repo,
            feedback_repo=feedback_repo,
            golden_dataset_service=golden_svc,
        )

        request = AdminOverrideRequest(
            decision_id=DECISION_ID,
            corrected_output="A much better output that is correct",
            override_reason="The original output was factually incorrect and misleading",
        )
        await service.apply_override(request, ADMIN_USER_ID, TENANT_ID)

        feedback_repo.append_feedback.assert_called_once()
        call_kwargs = feedback_repo.append_feedback.call_args[0][0]
        assert call_kwargs.feedback_type == FeedbackType.REJECT_WITH_FEEDBACK
        assert call_kwargs.source.value == "hil_action"

    @pytest.mark.asyncio
    async def test_calls_golden_dataset_with_admin_override_source(self):
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=_make_detail())
        feedback_repo = AsyncMock()
        feedback_repo.append_feedback = AsyncMock(return_value=self._make_feedback_result())
        golden_svc = AsyncMock()
        golden_svc.create_candidate = AsyncMock(return_value=self._make_candidate_result())

        service = _make_service(
            decision_repo=decision_repo,
            feedback_repo=feedback_repo,
            golden_dataset_service=golden_svc,
        )

        request = AdminOverrideRequest(
            decision_id=DECISION_ID,
            corrected_output="A much better output that is correct",
            override_reason="The original output was factually incorrect and misleading",
        )
        await service.apply_override(request, ADMIN_USER_ID, TENANT_ID)

        golden_svc.create_candidate.assert_called_once()
        call_arg = golden_svc.create_candidate.call_args[0][0]
        assert call_arg.source == "admin_override"

    @pytest.mark.asyncio
    async def test_returns_pending_review_status(self):
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=_make_detail())
        feedback_repo = AsyncMock()
        feedback_repo.append_feedback = AsyncMock(return_value=self._make_feedback_result())
        golden_svc = AsyncMock()
        golden_svc.create_candidate = AsyncMock(return_value=self._make_candidate_result())

        service = _make_service(
            decision_repo=decision_repo,
            feedback_repo=feedback_repo,
            golden_dataset_service=golden_svc,
        )

        request = AdminOverrideRequest(
            decision_id=DECISION_ID,
            corrected_output="A much better output that is correct",
            override_reason="The original output was factually incorrect and misleading",
        )
        result = await service.apply_override(request, ADMIN_USER_ID, TENANT_ID)
        assert result.status == "pending_review"

    @pytest.mark.asyncio
    async def test_raises_not_found_without_calling_downstream(self):
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=None)
        feedback_repo = AsyncMock()
        golden_svc = AsyncMock()

        service = _make_service(
            decision_repo=decision_repo,
            feedback_repo=feedback_repo,
            golden_dataset_service=golden_svc,
        )

        with pytest.raises(NotFoundError):
            await service.apply_override(
                AdminOverrideRequest(
                    decision_id=uuid.uuid4(),
                    corrected_output="Corrected output text here",
                    override_reason="The output was factually incorrect and required correction",
                ),
                ADMIN_USER_ID,
                TENANT_ID,
            )

        feedback_repo.append_feedback.assert_not_called()
        golden_svc.create_candidate.assert_not_called()

    @pytest.mark.asyncio
    async def test_proposed_adjustment_contains_role_and_confidence(self):
        detail = _make_detail(agent_role="narrative_writer", confidence=0.75)
        decision_repo = AsyncMock()
        decision_repo.get_by_id = AsyncMock(return_value=detail)
        feedback_repo = AsyncMock()
        feedback_repo.append_feedback = AsyncMock(return_value=self._make_feedback_result())
        golden_svc = AsyncMock()
        golden_svc.create_candidate = AsyncMock(return_value=self._make_candidate_result())

        service = _make_service(
            decision_repo=decision_repo,
            feedback_repo=feedback_repo,
            golden_dataset_service=golden_svc,
        )

        result = await service.apply_override(
            AdminOverrideRequest(
                decision_id=DECISION_ID,
                corrected_output="A much better output that is correct",
                override_reason="The original output was factually incorrect and misleading",
            ),
            ADMIN_USER_ID,
            TENANT_ID,
        )

        assert "narrative_writer" in result.proposed_prompt_adjustment
        assert "0.75" in result.proposed_prompt_adjustment
