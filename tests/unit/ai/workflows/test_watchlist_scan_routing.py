"""
Unit tests for WatchlistScan routing/dispatch nodes.

TDD: written before implementation — PLAN-F-008 TASK-004.

Nodes tested:
  evaluate_quality   — calls Tier1JudgeService, sets overall_confidence
  hil_enqueue        — enqueues in HIL with 17:45 UTC deadline
  block_and_notify   — logs, does NOT dispatch (no email)
  dispatch           — inserts Brief(brief_type="watchlist_scan"), sends email
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.watchlist_scan_nodes import (
    block_and_notify,
    dispatch,
    evaluate_quality,
    hil_enqueue,
)
from src.ai.workflows.watchlist_scan_state import WatchlistScanState


def _make_state(**kwargs) -> WatchlistScanState:
    defaults = {
        "workflow_id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "started_at": datetime.now(tz=timezone.utc),
    }
    defaults.update(kwargs)
    return WatchlistScanState(**defaults)


# ── evaluate_quality ──────────────────────────────────────────────────────────


class TestEvaluateQuality:
    @pytest.mark.asyncio
    async def test_sets_overall_confidence_from_judge(self):
        """evaluate_quality must set overall_confidence from Tier1JudgeService."""
        judge_result = MagicMock()
        judge_result.confidence = 0.78

        tier1_judge = AsyncMock()
        tier1_judge.evaluate = AsyncMock(return_value=judge_result)

        state = _make_state(overall_confidence=0.0)
        result = await evaluate_quality(state, tier1_judge=tier1_judge)

        assert abs(result.overall_confidence - 0.78) < 1e-9

    @pytest.mark.asyncio
    async def test_calls_tier1_judge_with_state(self):
        """tier1_judge.evaluate must be called with the current state."""
        judge_result = MagicMock()
        judge_result.confidence = 0.65

        tier1_judge = AsyncMock()
        tier1_judge.evaluate = AsyncMock(return_value=judge_result)

        state = _make_state()
        await evaluate_quality(state, tier1_judge=tier1_judge)

        tier1_judge.evaluate.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_preserves_existing_confidence_when_judge_returns_none(self):
        """If judge output has no confidence attribute, keep existing value."""
        judge_result = MagicMock(spec=[])  # no confidence attribute

        tier1_judge = AsyncMock()
        tier1_judge.evaluate = AsyncMock(return_value=judge_result)

        state = _make_state(overall_confidence=0.55)
        result = await evaluate_quality(state, tier1_judge=tier1_judge)

        assert abs(result.overall_confidence - 0.55) < 1e-9


# ── hil_enqueue ───────────────────────────────────────────────────────────────


class TestHilEnqueue:
    @pytest.mark.asyncio
    async def test_calls_hil_repo_with_create(self):
        """hil_enqueue must call hil_repo.create with a HILQueueItemCreate DTO."""
        hil_repo = AsyncMock()
        created_item = MagicMock()
        hil_repo.create = AsyncMock(return_value=created_item)

        state = _make_state(overall_confidence=0.55)
        await hil_enqueue(state, hil_repo=hil_repo)

        hil_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_requires_hil_true(self):
        """After hil_enqueue, state.requires_hil must be True."""
        hil_repo = AsyncMock()
        hil_repo.create = AsyncMock(return_value=MagicMock())

        state = _make_state()
        result = await hil_enqueue(state, hil_repo=hil_repo)

        assert result.requires_hil is True

    @pytest.mark.asyncio
    async def test_deadline_is_17_45_utc(self):
        """HIL deadline must be 17:45 UTC."""
        from src.storage.repositories.hil_queue_repository import HILQueueItemCreate

        captured_dto = None

        async def capture_create(dto):
            nonlocal captured_dto
            captured_dto = dto
            return MagicMock()

        hil_repo = AsyncMock()
        hil_repo.create = capture_create

        state = _make_state()
        await hil_enqueue(state, hil_repo=hil_repo)

        assert captured_dto is not None
        assert captured_dto.scheduled_send_at.hour == 17
        assert captured_dto.scheduled_send_at.minute == 45

    @pytest.mark.asyncio
    async def test_dto_includes_correct_workflow_type(self):
        """HILQueueItemCreate DTO must have workflow_type='watchlist_scan'."""
        captured_dto = None

        async def capture_create(dto):
            nonlocal captured_dto
            captured_dto = dto
            return MagicMock()

        hil_repo = AsyncMock()
        hil_repo.create = capture_create

        state = _make_state()
        await hil_enqueue(state, hil_repo=hil_repo)

        assert captured_dto.workflow_type == "watchlist_scan"


# ── block_and_notify ──────────────────────────────────────────────────────────


class TestBlockAndNotify:
    @pytest.mark.asyncio
    async def test_does_not_dispatch_email(self):
        """block_and_notify must NOT send any email."""
        state = _make_state(overall_confidence=0.20)

        # We pass no email service — if it tries to call it, it will fail
        result = await block_and_notify(state)

        # Simply reaching here without error proves no email was sent
        assert result is not None

    @pytest.mark.asyncio
    async def test_sets_hil_reason_with_confidence(self):
        """block_and_notify must set hil_reason indicating the low confidence."""
        state = _make_state(overall_confidence=0.25)
        result = await block_and_notify(state)

        assert result.hil_reason is not None
        assert "blocked" in result.hil_reason.lower() or "0.25" in result.hil_reason

    @pytest.mark.asyncio
    async def test_does_not_change_requires_hil(self):
        """block_and_notify sets requires_hil=False (this is not a HIL path)."""
        state = _make_state(requires_hil=False)
        result = await block_and_notify(state)

        assert result.requires_hil is False


# ── dispatch ─────────────────────────────────────────────────────────────────


class TestDispatch:
    @pytest.mark.asyncio
    async def test_inserts_brief_with_watchlist_scan_type(self):
        """dispatch must insert a Brief with type='watchlist_scan'."""
        inserted_brief = None

        async def capture_insert(brief):
            nonlocal inserted_brief
            inserted_brief = brief
            mock_row = MagicMock()
            mock_row.brief_id = uuid.uuid4()
            return mock_row

        brief_repo = AsyncMock()
        brief_repo.insert_memo = capture_insert

        email_service = AsyncMock()
        email_service.send_watchlist_scan = AsyncMock()

        state = _make_state(
            overall_confidence=0.80,
            report={"headline": "Afternoon scan"},
        )
        await dispatch(state, brief_repo=brief_repo, email_service=email_service)

        assert inserted_brief is not None
        assert inserted_brief.type == "watchlist_scan"

    @pytest.mark.asyncio
    async def test_sends_email(self):
        """dispatch must call email_service.send_watchlist_scan."""
        brief_repo = AsyncMock()
        mock_row = MagicMock()
        mock_row.brief_id = uuid.uuid4()
        brief_repo.insert_memo = AsyncMock(return_value=mock_row)

        email_service = AsyncMock()
        email_service.send_watchlist_scan = AsyncMock()

        state = _make_state(overall_confidence=0.80)
        await dispatch(state, brief_repo=brief_repo, email_service=email_service)

        email_service.send_watchlist_scan.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_sets_brief_id_on_state(self):
        """dispatch must set state.brief_id with the inserted row ID."""
        expected_brief_id = uuid.uuid4()

        brief_repo = AsyncMock()
        mock_row = MagicMock()
        mock_row.brief_id = expected_brief_id
        brief_repo.insert_memo = AsyncMock(return_value=mock_row)

        email_service = AsyncMock()
        email_service.send_watchlist_scan = AsyncMock()

        state = _make_state()
        result = await dispatch(state, brief_repo=brief_repo, email_service=email_service)

        assert result.brief_id == expected_brief_id

    @pytest.mark.asyncio
    async def test_brief_content_uses_report_or_empty_dict(self):
        """Brief content must be state.report when available."""
        report_data = {"sections": ["overview", "risk"]}
        inserted_brief = None

        async def capture_insert(brief):
            nonlocal inserted_brief
            inserted_brief = brief
            mock_row = MagicMock()
            mock_row.brief_id = uuid.uuid4()
            return mock_row

        brief_repo = AsyncMock()
        brief_repo.insert_memo = capture_insert

        email_service = AsyncMock()
        email_service.send_watchlist_scan = AsyncMock()

        state = _make_state(report=report_data)
        await dispatch(state, brief_repo=brief_repo, email_service=email_service)

        assert inserted_brief.content == report_data
