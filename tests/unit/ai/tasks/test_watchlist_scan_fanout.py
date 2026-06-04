"""
Unit tests for watchlist_scan_fanout multi-user fan-out.

TDD: written before implementation — PLAN-F-008 TASK-013.

Tests:
  - Dispatches one task per active user with watchlist
  - Skips users with empty watchlists
  - Feature flag disabled → no dispatch
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.ai.tasks.watchlist_scan_task import _run_fanout


class TestWatchlistScanFanout:
    def test_fanout_task_exists_and_has_correct_name(self):
        """watchlist_scan_fanout task must be named 'ai.watchlist_scan_fanout'."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_fanout
        assert watchlist_scan_fanout.name == "ai.watchlist_scan_fanout"

    def test_fanout_skips_when_feature_disabled(self):
        """fanout returns 0 dispatched when feature flag is disabled."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_fanout

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=False)

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ):
            result = watchlist_scan_fanout(env="test")

        assert result["dispatched_count"] == 0
        assert result.get("reason") == "feature_disabled"

    @pytest.mark.asyncio
    async def test_run_fanout_dispatches_one_task_per_active_user(self):
        """_run_fanout dispatches watchlist_scan_generate.delay once per user."""
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        active_users = [
            {"user_id": user1_id, "tenant_id": tenant_id, "watchlist_size": 3},
            {"user_id": user2_id, "tenant_id": tenant_id, "watchlist_size": 5},
        ]

        with patch(
            "src.ai.tasks.watchlist_scan_task._fetch_active_users_with_watchlist",
            new=AsyncMock(return_value=active_users),
        ), patch(
            "src.ai.tasks.watchlist_scan_task.watchlist_scan_generate"
        ) as mock_task:
            mock_task.delay = MagicMock()
            result = await _run_fanout(env="test")

        assert result["dispatched_count"] == 2
        assert mock_task.delay.call_count == 2

    @pytest.mark.asyncio
    async def test_run_fanout_skips_empty_watchlists(self):
        """_run_fanout skips users with watchlist_size == 0."""
        active_users = [
            {
                "user_id": uuid.uuid4(),
                "tenant_id": uuid.uuid4(),
                "watchlist_size": 0,  # empty — must be skipped
            },
        ]

        with patch(
            "src.ai.tasks.watchlist_scan_task._fetch_active_users_with_watchlist",
            new=AsyncMock(return_value=active_users),
        ), patch(
            "src.ai.tasks.watchlist_scan_task.watchlist_scan_generate"
        ) as mock_task:
            mock_task.delay = MagicMock()
            result = await _run_fanout(env="test")

        assert result["dispatched_count"] == 0
        assert result["skipped_count"] == 1
        mock_task.delay.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_fanout_passes_user_id_and_tenant_id(self):
        """_run_fanout passes correct user_id and tenant_id to each task."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        active_users = [
            {"user_id": user_id, "tenant_id": tenant_id, "watchlist_size": 2},
        ]

        captured_kwargs = []

        def capture_delay(**kwargs):
            captured_kwargs.append(kwargs)

        with patch(
            "src.ai.tasks.watchlist_scan_task._fetch_active_users_with_watchlist",
            new=AsyncMock(return_value=active_users),
        ), patch(
            "src.ai.tasks.watchlist_scan_task.watchlist_scan_generate"
        ) as mock_task:
            mock_task.delay = MagicMock(side_effect=capture_delay)
            await _run_fanout(env="test")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["user_id"] == str(user_id)
        assert captured_kwargs[0]["tenant_id"] == str(tenant_id)

    @pytest.mark.asyncio
    async def test_run_fanout_returns_zero_when_no_users(self):
        """_run_fanout returns dispatched_count=0 when no active users."""
        with patch(
            "src.ai.tasks.watchlist_scan_task._fetch_active_users_with_watchlist",
            new=AsyncMock(return_value=[]),
        ), patch(
            "src.ai.tasks.watchlist_scan_task.watchlist_scan_generate"
        ) as mock_task:
            mock_task.delay = MagicMock()
            result = await _run_fanout(env="test")

        assert result["dispatched_count"] == 0

    @pytest.mark.asyncio
    async def test_run_fanout_handles_mixed_watchlist_sizes(self):
        """_run_fanout dispatches for non-empty, skips empty watchlists."""
        active_users = [
            {"user_id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "watchlist_size": 5},
            {"user_id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "watchlist_size": 0},
            {"user_id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "watchlist_size": 2},
        ]

        with patch(
            "src.ai.tasks.watchlist_scan_task._fetch_active_users_with_watchlist",
            new=AsyncMock(return_value=active_users),
        ), patch(
            "src.ai.tasks.watchlist_scan_task.watchlist_scan_generate"
        ) as mock_task:
            mock_task.delay = MagicMock()
            result = await _run_fanout(env="test")

        assert result["dispatched_count"] == 2
        assert result["skipped_count"] == 1
