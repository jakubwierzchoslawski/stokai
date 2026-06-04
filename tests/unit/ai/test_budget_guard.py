"""
Unit tests for BudgetGuard.

PLAN-F-030 TASK-005
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.budget_guard import BudgetGuard, BudgetHardStopError, BudgetStatus


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_cost_repo(monthly_spend: float) -> AsyncMock:
    repo = AsyncMock()
    repo.aggregate_monthly = AsyncMock(return_value=monthly_spend)
    return repo


def _make_user_repo(threshold_usd: float = 100.0) -> AsyncMock:
    repo = AsyncMock()
    admin_user = MagicMock()
    admin_user.user_id = uuid.uuid4()
    admin_user.settings = {"budget_threshold_usd": threshold_usd}
    repo.get_admin_for_tenant = AsyncMock(return_value=admin_user)
    repo.update_settings = AsyncMock()
    return repo


def _audit_events() -> list[tuple[str, str]]:
    """Return a mutable list to capture audit calls."""
    return []


def _make_guard(
    spend: float,
    threshold: float = 100.0,
) -> tuple[BudgetGuard, list]:
    cost_repo = _make_cost_repo(spend)
    user_repo = _make_user_repo(threshold)
    events: list[tuple[str, str]] = []

    def audit(level: str, msg: str) -> None:
        events.append((level, msg))

    guard = BudgetGuard(
        cost_repo=cost_repo,
        user_repo=user_repo,
        audit_logger=audit,
    )
    return guard, events


# ── assert_under_limit ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAssertUnderLimit:
    async def test_no_raise_at_zero_percent(self) -> None:
        """0% spend → no exception, no audit."""
        guard, events = _make_guard(spend=0.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        await guard.assert_under_limit(tenant_id)

        assert events == []

    async def test_no_raise_at_79_percent(self) -> None:
        """79% spend → no exception, no audit."""
        guard, events = _make_guard(spend=79.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        await guard.assert_under_limit(tenant_id)

        assert events == []

    async def test_no_raise_at_80_percent_but_warning_audit_written(self) -> None:
        """80% spend → no exception but WARNING audit event written."""
        guard, events = _make_guard(spend=80.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        await guard.assert_under_limit(tenant_id)

        assert any(level == "WARNING" for level, _ in events)

    async def test_raises_at_100_percent_with_hard_stop_audit(self) -> None:
        """100% spend → BudgetHardStopError raised + CRITICAL audit."""
        guard, events = _make_guard(spend=100.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        with pytest.raises(BudgetHardStopError):
            await guard.assert_under_limit(tenant_id)

        assert any(level == "CRITICAL" for level, _ in events)

    async def test_raises_when_exceeds_100_percent(self) -> None:
        """120% spend → BudgetHardStopError raised."""
        guard, events = _make_guard(spend=120.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        with pytest.raises(BudgetHardStopError):
            await guard.assert_under_limit(tenant_id)


# ── get_budget_status ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetBudgetStatus:
    async def test_status_at_82_percent(self) -> None:
        """82% spend → warning_active=True, hard_stop=False."""
        guard, _ = _make_guard(spend=82.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        status = await guard.get_budget_status(tenant_id)

        assert status.spend_usd == 82.0
        assert status.threshold_usd == 100.0
        assert abs(status.pct_used - 82.0) < 0.01
        assert status.warning_active is True
        assert status.hard_stop_active is False

    async def test_hard_stop_active_at_100_percent(self) -> None:
        """100% spend → hard_stop_active=True."""
        guard, _ = _make_guard(spend=100.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        status = await guard.get_budget_status(tenant_id)

        assert status.hard_stop_active is True

    async def test_no_warning_below_80_percent(self) -> None:
        """50% spend → warning_active=False, hard_stop=False."""
        guard, _ = _make_guard(spend=50.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        status = await guard.get_budget_status(tenant_id)

        assert status.warning_active is False
        assert status.hard_stop_active is False


# ── set_threshold ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSetThreshold:
    async def test_set_threshold_persists_and_used_in_subsequent_status(self) -> None:
        """set_threshold stores new value; subsequent get_budget_status uses it."""
        cost_repo = _make_cost_repo(50.0)
        user_repo = _make_user_repo(threshold_usd=100.0)
        guard = BudgetGuard(cost_repo=cost_repo, user_repo=user_repo)
        tenant_id = uuid.uuid4()

        await guard.set_threshold(tenant_id, 200.0)

        # Simulate that user_repo now returns updated threshold
        admin_user = MagicMock()
        admin_user.user_id = uuid.uuid4()
        admin_user.settings = {"budget_threshold_usd": 200.0}
        user_repo.get_admin_for_tenant = AsyncMock(return_value=admin_user)

        status = await guard.get_budget_status(tenant_id)
        assert status.threshold_usd == 200.0

    async def test_set_threshold_calls_update_settings(self) -> None:
        """set_threshold calls user_repo.update_settings with new value."""
        cost_repo = _make_cost_repo(0.0)
        user_repo = _make_user_repo(threshold_usd=100.0)
        guard = BudgetGuard(cost_repo=cost_repo, user_repo=user_repo)
        tenant_id = uuid.uuid4()

        await guard.set_threshold(tenant_id, 150.0)

        user_repo.update_settings.assert_called_once()
        call_kwargs = user_repo.update_settings.call_args
        settings_arg = call_kwargs[0][1]  # second positional arg
        assert settings_arg["budget_threshold_usd"] == 150.0


# ── Integration: Celery entry point ───────────────────────────────────────────


@pytest.mark.asyncio
class TestBudgetGuardCeleryIntegration:
    async def test_raises_from_mocked_celery_entry_prevents_task_body(self) -> None:
        """assert_under_limit raises BudgetHardStopError from within a mock Celery task."""
        guard, events = _make_guard(spend=100.0, threshold=100.0)
        tenant_id = uuid.uuid4()

        async def fake_celery_task():
            await guard.assert_under_limit(tenant_id)
            return "task_completed"  # should never reach here

        with pytest.raises(BudgetHardStopError):
            await fake_celery_task()
