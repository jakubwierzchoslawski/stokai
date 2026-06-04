"""Unit tests for AuditService — prompt version history and rollback.

PLAN-F-029 TASK-004
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.admin.audit.audit_service import AuditService, RollbackError
from src.api.admin.audit.audit_api_schemas import RollbackRequest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_service(
    prompt_pub_repo=None,
    eval_repo=None,
    prompt_label_service=None,
) -> AuditService:
    return AuditService(
        decision_repo=AsyncMock(),
        feedback_repo=AsyncMock(),
        golden_dataset_service=AsyncMock(),
        prompt_label_service=prompt_label_service or AsyncMock(),
        prompt_publication_repo=prompt_pub_repo or AsyncMock(),
        evaluation_repo=eval_repo or AsyncMock(),
        episodic_repo=AsyncMock(),
        workflow_runner=AsyncMock(),
        calibration_repo=AsyncMock(),
        calibration_service=AsyncMock(),
    )


def _make_pub(**kwargs):
    pub = MagicMock()
    pub.git_sha = kwargs.get("git_sha", "abc1234" * 5)
    pub.label = kwargs.get("label", "production")
    pub.published_at = kwargs.get("published_at", datetime(2026, 6, 4, tzinfo=timezone.utc))
    pub.rolled_back_at = kwargs.get("rolled_back_at", None)
    return pub


# ── list_prompt_history ────────────────────────────────────────────────────────

class TestListPromptHistory:
    @pytest.mark.asyncio
    async def test_returns_entries_sorted_by_published_at_desc(self):
        dt1 = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
        pub1 = _make_pub(published_at=dt1, git_sha="sha_newer")
        pub2 = _make_pub(published_at=dt2, git_sha="sha_older")

        prompt_pub_repo = AsyncMock()
        prompt_pub_repo.list_by_role = AsyncMock(return_value=[pub1, pub2])
        eval_repo = AsyncMock()
        eval_repo.list_recent_by_version = AsyncMock(return_value=[])

        service = _make_service(prompt_pub_repo=prompt_pub_repo, eval_repo=eval_repo)
        entries = await service.list_prompt_history("narrative_writer", limit=50)

        assert len(entries) == 2
        assert entries[0].published_at == dt1
        assert entries[1].published_at == dt2

    @pytest.mark.asyncio
    async def test_enriches_quality_metrics_from_evaluation_result(self):
        pub = _make_pub()
        eval_result = MagicMock()
        eval_result.scores = {"factual_grounding": 0.9, "confidence_calibration": 0.85}

        prompt_pub_repo = AsyncMock()
        prompt_pub_repo.list_by_role = AsyncMock(return_value=[pub])
        eval_repo = AsyncMock()
        eval_repo.list_recent_by_version = AsyncMock(return_value=[eval_result])

        service = _make_service(prompt_pub_repo=prompt_pub_repo, eval_repo=eval_repo)
        entries = await service.list_prompt_history("narrative_writer")

        assert entries[0].quality_metrics == {"factual_grounding": 0.9, "confidence_calibration": 0.85}

    @pytest.mark.asyncio
    async def test_sets_quality_metrics_none_when_no_evaluation_result(self):
        pub = _make_pub()
        prompt_pub_repo = AsyncMock()
        prompt_pub_repo.list_by_role = AsyncMock(return_value=[pub])
        eval_repo = AsyncMock()
        eval_repo.list_recent_by_version = AsyncMock(return_value=[])

        service = _make_service(prompt_pub_repo=prompt_pub_repo, eval_repo=eval_repo)
        entries = await service.list_prompt_history("narrative_writer")

        assert entries[0].quality_metrics is None

    @pytest.mark.asyncio
    async def test_sets_rolled_back_at_when_rollback_pub_exists(self):
        rollback_ts = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)
        pub = _make_pub(rolled_back_at=rollback_ts)

        prompt_pub_repo = AsyncMock()
        prompt_pub_repo.list_by_role = AsyncMock(return_value=[pub])
        eval_repo = AsyncMock()
        eval_repo.list_recent_by_version = AsyncMock(return_value=[])

        service = _make_service(prompt_pub_repo=prompt_pub_repo, eval_repo=eval_repo)
        entries = await service.list_prompt_history("narrative_writer")

        assert entries[0].rolled_back_at == rollback_ts


# ── rollback_prompt ────────────────────────────────────────────────────────────

class TestRollbackPrompt:
    @pytest.mark.asyncio
    async def test_calls_prompt_label_service_with_correct_args(self):
        prompt_label_service = AsyncMock()
        rollback_result = MagicMock()
        rollback_result.previous_version = "old_sha_1234567"
        rollback_result.effective_at = datetime.now(timezone.utc)
        prompt_label_service.rollback = AsyncMock(return_value=rollback_result)

        service = _make_service(prompt_label_service=prompt_label_service)
        request = RollbackRequest(agent_role="narrative_writer", to_version="abc1234def5678")

        await service.rollback_prompt(request)

        prompt_label_service.rollback.assert_called_once_with(
            "narrative_writer", "abc1234def5678"
        )

    @pytest.mark.asyncio
    async def test_returns_response_with_rolled_back_to(self):
        prompt_label_service = AsyncMock()
        rollback_result = MagicMock()
        rollback_result.previous_version = "old_sha_1234567"
        rollback_result.effective_at = datetime.now(timezone.utc)
        prompt_label_service.rollback = AsyncMock(return_value=rollback_result)

        service = _make_service(prompt_label_service=prompt_label_service)
        request = RollbackRequest(agent_role="narrative_writer", to_version="abc1234def5678")

        result = await service.rollback_prompt(request)
        assert result.rolled_back_to == "abc1234def5678"

    @pytest.mark.asyncio
    async def test_propagates_failure_as_rollback_error(self):
        prompt_label_service = AsyncMock()
        prompt_label_service.rollback = AsyncMock(
            side_effect=Exception("Langfuse label API error")
        )

        service = _make_service(prompt_label_service=prompt_label_service)
        request = RollbackRequest(agent_role="narrative_writer", to_version="abc1234def5678")

        with pytest.raises(RollbackError):
            await service.rollback_prompt(request)
