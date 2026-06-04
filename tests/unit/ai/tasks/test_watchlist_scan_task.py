"""
Unit tests for watchlist_scan_generate Celery task.

TDD: written before implementation — PLAN-F-008 TASK-006.

Tests:
  - Skips when feature flag disabled
  - Creates workflow_id and runs
  - Returns hil_pending status
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWatchlistScanTask:
    def test_task_has_correct_name(self):
        """Task must be registered as 'ai.watchlist_scan'."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate
        assert watchlist_scan_generate.name == "ai.watchlist_scan"

    def test_task_has_correct_time_limits(self):
        """Task must have time_limit=480 and soft_time_limit=360."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate
        assert watchlist_scan_generate.time_limit == 480
        assert watchlist_scan_generate.soft_time_limit == 360

    def test_task_has_max_retries_zero(self):
        """Task must have max_retries=0."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate
        assert watchlist_scan_generate.max_retries == 0

    def test_skips_when_feature_flag_disabled(self):
        """Task must return SKIPPED when feature flag is disabled."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=False)

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                env="test",
            )

        assert result["status"] == "SKIPPED"
        assert result["reason"] == "feature_disabled"

    def test_returns_workflow_id_in_result(self):
        """Task must return workflow_id in the result dict."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=False)

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
            )

        assert "workflow_id" in result

    def test_uses_provided_workflow_id(self):
        """Task must use the provided workflow_id if supplied."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        wf_id = str(uuid.uuid4())
        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=False)

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                workflow_id=wf_id,
            )

        assert result["workflow_id"] == wf_id

    def test_returns_hil_pending_false_when_skipped(self):
        """When skipped, hil_pending must be False."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=False)

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
            )

        assert result["hil_pending"] is False

    def test_runs_workflow_when_feature_enabled(self):
        """Task must call _run_watchlist_scan_for_user when feature is enabled."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=True)

        run_result = {
            "workflow_id": str(uuid.uuid4()),
            "status": "COMPLETED",
            "hil_pending": False,
            "cost_usd": 0.10,
        }

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ), patch(
            "src.ai.tasks.watchlist_scan_task._run_watchlist_scan_for_user",
            new=AsyncMock(return_value=run_result),
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
            )

        assert result["status"] == "COMPLETED"

    def test_returns_hil_pending_true_when_workflow_pending(self):
        """Task returns hil_pending=True when workflow routes to HIL."""
        from src.ai.tasks.watchlist_scan_task import watchlist_scan_generate

        mock_flag_svc = MagicMock()
        mock_flag_svc.is_enabled = MagicMock(return_value=True)

        run_result = {
            "workflow_id": str(uuid.uuid4()),
            "status": "HIL_PENDING",
            "hil_pending": True,
            "cost_usd": 0.25,
        }

        with patch(
            "src.ai.tasks.watchlist_scan_task._get_feature_flag_service",
            return_value=mock_flag_svc,
        ), patch(
            "src.ai.tasks.watchlist_scan_task._run_watchlist_scan_for_user",
            new=AsyncMock(return_value=run_result),
        ):
            result = watchlist_scan_generate(
                user_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
            )

        assert result["hil_pending"] is True
