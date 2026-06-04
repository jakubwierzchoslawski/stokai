"""
Unit tests for UserBudgetEnforcer (PLAN-N-004 TASK-004).

TDD: tests were written before the implementation was completed.
All external dependencies (repositories) are mocked.
"""
from __future__ import annotations

import logging
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.ai.cost.errors import UserDailyBudgetExceededError
from src.ai.cost.user_budget_enforcer import UserBudgetEnforcer


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(settings: dict) -> MagicMock:
    user = MagicMock()
    user.settings = settings
    return user


def _make_repos(spent_today: float, user_settings: dict | None = None) -> tuple:
    """Return (cost_repo, user_repo) mocks configured with given values."""
    cost_repo = AsyncMock()
    cost_repo.daily_total_for_user = AsyncMock(return_value=spent_today)

    user_repo = AsyncMock()
    if user_settings is not None:
        user_repo.getById = AsyncMock(return_value=_make_user(user_settings))
    else:
        user_repo.getById = AsyncMock(return_value=_make_user({}))

    return cost_repo, user_repo


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUserBudgetEnforcer:
    """Tests for UserBudgetEnforcer.check_and_alert."""

    async def test_check_allows_dispatch_when_under_alert_threshold(self) -> None:
        """$7.00 spent of $10.00 budget (70%) is under 80% alert threshold; returns None."""
        cost_repo, user_repo = _make_repos(
            spent_today=7.00,
            user_settings={"daily_budget_usd": 10.00, "daily_alert_threshold_pct": 80.0},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        result = await enforcer.check_and_alert(uuid4(), uuid4(), "morning_brief")

        assert result is None

    async def test_check_logs_alert_at_alert_threshold(self, caplog) -> None:
        """$8.00 spent of $10.00 (80%) triggers WARNING BudgetAlertEvent; no exception."""
        user_id = uuid4()
        tenant_id = uuid4()
        cost_repo, user_repo = _make_repos(
            spent_today=8.00,
            user_settings={"daily_budget_usd": 10.00, "daily_alert_threshold_pct": 80.0},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with caplog.at_level(logging.WARNING):
            result = await enforcer.check_and_alert(user_id, tenant_id, "morning_brief")

        assert result is None
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1
        assert "BudgetAlertEvent" in warning_records[0].message or "budget" in warning_records[0].message.lower()

    async def test_check_allows_dispatch_after_alert_threshold(self) -> None:
        """After alert fires at 80%, dispatch still proceeds (returns None)."""
        cost_repo, user_repo = _make_repos(
            spent_today=8.50,
            user_settings={"daily_budget_usd": 10.00, "daily_alert_threshold_pct": 80.0},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        result = await enforcer.check_and_alert(uuid4(), uuid4(), "morning_brief")

        assert result is None

    async def test_check_raises_hard_stop_at_100_pct(self) -> None:
        """$10.00 spent of $10.00 budget (100%) raises UserDailyBudgetExceededError."""
        user_id = uuid4()
        cost_repo, user_repo = _make_repos(
            spent_today=10.00,
            user_settings={"daily_budget_usd": 10.00},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with pytest.raises(UserDailyBudgetExceededError) as exc_info:
            await enforcer.check_and_alert(user_id, uuid4(), "morning_brief")

        assert exc_info.value.user_id == user_id
        assert exc_info.value.daily_budget_usd == pytest.approx(10.00)
        assert exc_info.value.spent_today_usd == pytest.approx(10.00)

    async def test_check_raises_hard_stop_above_100_pct(self) -> None:
        """$10.05 of $10.00 (>100%) also raises UserDailyBudgetExceededError."""
        cost_repo, user_repo = _make_repos(
            spent_today=10.05,
            user_settings={"daily_budget_usd": 10.00},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with pytest.raises(UserDailyBudgetExceededError):
            await enforcer.check_and_alert(uuid4(), uuid4(), "morning_brief")

    async def test_check_allows_when_daily_budget_not_configured(self, caplog) -> None:
        """User with no daily_budget_usd in settings: logs WARNING and allows dispatch."""
        cost_repo, user_repo = _make_repos(
            spent_today=5.00,
            user_settings={},  # no daily_budget_usd
        )
        # Override: return 0.0 for daily_budget_usd to trigger unconfigured path
        user_repo.getById = AsyncMock(
            return_value=_make_user({"daily_budget_usd": 0.0})
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with caplog.at_level(logging.WARNING):
            result = await enforcer.check_and_alert(uuid4(), uuid4(), "morning_brief")

        assert result is None
        assert any("budget" in r.message.lower() for r in caplog.records if r.levelname == "WARNING")

    async def test_check_reads_alert_threshold_from_user_settings(self, caplog) -> None:
        """Custom daily_alert_threshold_pct=60; $6 of $10 (60%) triggers alert."""
        user_id = uuid4()
        tenant_id = uuid4()
        cost_repo, user_repo = _make_repos(
            spent_today=6.00,
            user_settings={
                "daily_budget_usd": 10.00,
                "daily_alert_threshold_pct": 60.0,
            },
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with caplog.at_level(logging.WARNING):
            result = await enforcer.check_and_alert(user_id, tenant_id, "watchlist_scan")

        assert result is None
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warning_records) >= 1

    async def test_check_uses_correct_date_for_daily_total(self) -> None:
        """Verify daily_total_for_user is called with date.today()."""
        user_id = uuid4()
        tenant_id = uuid4()
        cost_repo, user_repo = _make_repos(
            spent_today=1.00,
            user_settings={"daily_budget_usd": 10.00},
        )
        enforcer = UserBudgetEnforcer(cost_repo, user_repo)

        with patch("src.ai.cost.user_budget_enforcer.date") as mock_date:
            mock_date.today.return_value = date(2026, 6, 4)
            await enforcer.check_and_alert(user_id, tenant_id, "morning_brief")

        cost_repo.daily_total_for_user.assert_called_once_with(
            user_id, tenant_id, date(2026, 6, 4)
        )
