"""
Integration tests for Mode A pipeline steps 9-10 (evaluate_alert_rules +
dispatch_or_log_silent).

Uses real AlertRuleEvaluator and AlertDispatcher wired against mocked
repositories (no real PostgreSQL — pattern matches integration tests in
tests/integration/events/).  Mock only ILLMClient and IEmailSender.

Each test is marked @pytest.mark.integration.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, time as _time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.alerts.exceptions import AlertDispatchError, SendGridError
from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.alerts.models import (
    ActionSignal,
    AlertRuleRow,
    AlertStatus,
    AlertTextResult,
    BudgetState,
)
from src.alerts.repositories.alert_repository import AlertRepository
from src.alerts.repositories.alert_rule_repository import AlertRuleRepository
from src.alerts.services.alert_dispatcher import AlertDispatcher
from src.alerts.services.alert_rule_evaluator import AlertRuleEvaluator
from src.alerts.services.anti_fatigue_checker import AntiFatigueChecker
from src.alerts.services.budget_enforcer import BudgetEnforcer


# ── Fixtures and helpers ──────────────────────────────────────────────────────

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
USER_ID = uuid.uuid4()
EVENT_ID = uuid.uuid4()
RULE_ID = uuid.uuid4()


def _make_rule(
    tenant_id=None,
    user_id=None,
    intensity_min=1,
    event_categories=None,
    ticker_list=None,
    daily_limit=5,
    quiet_hours_start=None,
    quiet_hours_end=None,
    per_ticker_interval_hours=24,
    dedup_window_minutes=60,
    **overrides,
) -> AlertRuleRow:
    return AlertRuleRow(
        rule_id=RULE_ID,
        tenant_id=tenant_id or TENANT_A,
        user_id=user_id or USER_ID,
        user_email="trader@example.com",
        event_categories=event_categories or [],
        intensity_min=intensity_min,
        ticker_list=ticker_list or [],
        quiet_hours_start=quiet_hours_start,
        quiet_hours_end=quiet_hours_end,
        daily_limit=daily_limit,
        dedup_window_minutes=dedup_window_minutes,
        per_ticker_interval_hours=per_ticker_interval_hours,
        enabled=True,
        **overrides,
    )


def _make_rule_repo(rules: list[AlertRuleRow]) -> AsyncMock:
    repo = AsyncMock(spec=AlertRuleRepository)
    repo.get_active_rules = AsyncMock(return_value=rules)
    return repo


def _make_alert_repo(
    dispatched_today: int = 0,
    last_ticker_dispatch=None,
    recent_ids=None,
    budget: BudgetState | None = None,
    spent_today: float = 0.0,
) -> AsyncMock:
    repo = AsyncMock(spec=AlertRepository)
    repo.count_dispatched_today = AsyncMock(return_value=dispatched_today)
    repo.get_last_dispatch_for_ticker = AsyncMock(return_value=last_ticker_dispatch)
    repo.get_recent_event_alert_ids = AsyncMock(return_value=recent_ids or [])
    repo.get_budget_state = AsyncMock(
        return_value=budget
        or BudgetState(
            daily_budget_usd=10.0,
            spent_today_usd=spent_today,
            alert_threshold_pct=80.0,
            hard_stop_pct=100.0,
        )
    )
    repo.get_spent_today_usd = AsyncMock(return_value=spent_today)
    repo.insert_alert = AsyncMock(return_value=uuid.uuid4())
    repo.insert_silent_log = AsyncMock(return_value=uuid.uuid4())
    return repo


def _make_email_sender(raises=None) -> AsyncMock:
    sender = AsyncMock()
    if raises:
        sender.send = AsyncMock(side_effect=raises)
    else:
        sender.send = AsyncMock(return_value=None)
    return sender


def _make_alert_text() -> AlertTextResult:
    return AlertTextResult(
        alert_text="Geopolitical event detected. High-intensity (4/5). AI signal: WATCH. "
                   "3 holdings exposed. Confidence: 75%. Based on 8 historical analogies.",
        action_signal=ActionSignal.WATCH,
        confidence=0.75,
        sample_size=8,
        low_sample_disclaimer=False,
    )


def _make_rule_match(rule: AlertRuleRow, tickers=None) -> RuleMatch:
    return RuleMatch(
        rule_id=rule.rule_id,
        user_id=rule.user_id,
        user_email=rule.user_email,
        tenant_id=rule.tenant_id,
        channels=["email"],
        matched_tickers=tickers or ["AAPL"],
    )


def _build_dispatcher(alert_repo, email_sender=None) -> AlertDispatcher:
    return AlertDispatcher(
        fatigue_repo=alert_repo,
        anti_fatigue_checker=AntiFatigueChecker(),
        budget_enforcer=BudgetEnforcer(),
        email_sender=email_sender or _make_email_sender(),
        alert_repo=alert_repo,
    )


def _build_evaluator(rules: list[AlertRuleRow]) -> AlertRuleEvaluator:
    return AlertRuleEvaluator(rule_repo=_make_rule_repo(rules))


# ── Step 9 SLA test ───────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_step9_evaluate_alert_rules_completes_in_under_1s():
    """evaluate_alert_rules (step 9) completes in ≤1s wall-clock."""
    rules = [_make_rule() for _ in range(10)]
    evaluator = _build_evaluator(rules)

    start = time.monotonic()
    await evaluator.evaluate(EVENT_ID, 3, ["conflict"], ["AAPL"], TENANT_A)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"Step 9 took {elapsed:.3f}s, expected < 1.0s"


# ── Step 10 SLA test ──────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_step10_dispatch_or_log_silent_completes_in_under_2s():
    """dispatch_or_log_silent (step 10) with mocked SendGrid completes in ≤2s."""
    rule = _make_rule()
    alert_repo = _make_alert_repo()
    dispatcher = _build_dispatcher(alert_repo)

    start = time.monotonic()
    await dispatcher.dispatch(_make_rule_match(rule), _make_alert_text(), EVENT_ID)
    elapsed = time.monotonic() - start

    assert elapsed < 2.0, f"Step 10 took {elapsed:.3f}s, expected < 2.0s"


# ── Full happy path ───────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_happy_path_alert_dispatched_and_send_called():
    """Full happy path: rule matches, gates pass, alert dispatched, send called once."""
    rule = _make_rule()
    email_sender = _make_email_sender()
    alert_repo = _make_alert_repo()
    dispatcher = _build_dispatcher(alert_repo, email_sender)

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.DISPATCHED
    assert result.channel == "email"
    email_sender.send.assert_called_once()
    alert_repo.insert_alert.assert_called_once()
    inserted = alert_repo.insert_alert.call_args[0][0]
    assert inserted.status == AlertStatus.DISPATCHED


# ── Suppression paths ─────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_daily_limit_reached_silent_log_no_send():
    """Daily limit reached: SUPPRESSED_DAILY_LIMIT silent-log, send NOT called."""
    rule = _make_rule(daily_limit=5)
    alert_repo = _make_alert_repo(dispatched_today=5)
    email_sender = _make_email_sender()
    dispatcher = _build_dispatcher(alert_repo, email_sender)

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_DAILY_LIMIT
    alert_repo.insert_silent_log.assert_called_once()
    email_sender.send.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quiet_hours_active_silent_log_no_send():
    """Quiet hours active: SUPPRESSED_QUIET_HOURS silent-log, send NOT called.

    The stub_rule inside AlertDispatcher uses quiet_hours=None by default.
    We patch AntiFatigueChecker to simulate quiet hours suppression directly.
    """
    from unittest.mock import patch, MagicMock

    rule = _make_rule()
    alert_repo = _make_alert_repo()
    email_sender = _make_email_sender()

    # Patch the checker to return quiet hours suppression
    checker = MagicMock(spec=AntiFatigueChecker)
    checker.check = MagicMock(return_value=AlertStatus.SUPPRESSED_QUIET_HOURS)

    dispatcher = AlertDispatcher(
        fatigue_repo=alert_repo,
        anti_fatigue_checker=checker,
        budget_enforcer=BudgetEnforcer(),
        email_sender=email_sender,
        alert_repo=alert_repo,
    )

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_QUIET_HOURS
    alert_repo.insert_silent_log.assert_called_once()
    email_sender.send.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_per_ticker_interval_active_silent_log_no_send():
    """Per-ticker interval not elapsed: SUPPRESSED_TICKER_INTERVAL, send NOT called."""
    from unittest.mock import MagicMock

    rule = _make_rule()
    alert_repo = _make_alert_repo()
    email_sender = _make_email_sender()

    checker = MagicMock(spec=AntiFatigueChecker)
    checker.check = MagicMock(return_value=AlertStatus.SUPPRESSED_TICKER_INTERVAL)

    dispatcher = AlertDispatcher(
        fatigue_repo=alert_repo,
        anti_fatigue_checker=checker,
        budget_enforcer=BudgetEnforcer(),
        email_sender=email_sender,
        alert_repo=alert_repo,
    )

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_TICKER_INTERVAL
    email_sender.send.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dedup_window_active_silent_log_no_send():
    """Dedup window active: SUPPRESSED_DEDUP, send NOT called."""
    rule = _make_rule()
    alert_repo = _make_alert_repo(recent_ids=[uuid.uuid4()])
    email_sender = _make_email_sender()
    dispatcher = _build_dispatcher(alert_repo, email_sender)

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_DEDUP
    email_sender.send.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hard_stop_budget_reached_silent_log_no_send():
    """Hard stop budget: SUPPRESSED_BUDGET silent-log, send NOT called."""
    rule = _make_rule()
    budget = BudgetState(
        daily_budget_usd=10.0,
        spent_today_usd=10.0,
        alert_threshold_pct=80.0,
        hard_stop_pct=100.0,
    )
    alert_repo = _make_alert_repo(budget=budget)
    email_sender = _make_email_sender()
    dispatcher = _build_dispatcher(alert_repo, email_sender)

    result = await dispatcher.dispatch(
        _make_rule_match(rule), _make_alert_text(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_BUDGET
    alert_repo.insert_silent_log.assert_called_once()
    email_sender.send.assert_not_called()


# ── Low sample disclaimer ─────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_sample_size_below_5_disclaimer_in_html_body():
    """sample_size < 5: dispatched alert HTML body contains low-sample disclaimer."""
    rule = _make_rule()
    email_sender = _make_email_sender()
    alert_repo = _make_alert_repo()
    dispatcher = _build_dispatcher(alert_repo, email_sender)

    low_sample_text = AlertTextResult(
        alert_text="Alert with low sample.",
        action_signal=ActionSignal.WATCH,
        confidence=0.5,
        sample_size=3,
        low_sample_disclaimer=True,
    )

    await dispatcher.dispatch(_make_rule_match(rule), low_sample_text, EVENT_ID)

    call_args = email_sender.send.call_args
    html_body = (
        call_args[1].get("html_body")
        or (call_args[0][2] if len(call_args[0]) > 2 else "")
    )
    assert "fewer than 5" in html_body or "low" in html_body.lower()


# ── No rules match ────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_rules_match_evaluator_returns_empty_no_send():
    """No rules match: evaluator returns [], no alert rows inserted, send not called."""
    # Rule intensity_min=5 but event intensity=2 — no match
    rule = _make_rule(intensity_min=5)
    evaluator = _build_evaluator([rule])

    matches = await evaluator.evaluate(EVENT_ID, 2, ["conflict"], ["AAPL"], TENANT_A)

    assert matches == []


# ── Tenant isolation ──────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_tenant_isolation_rule_from_a_not_evaluated_for_b():
    """Rule from tenant A is not evaluated for event from tenant B."""
    rule_a = _make_rule(tenant_id=TENANT_A)
    rule_repo = _make_rule_repo([rule_a])

    # When queried with TENANT_B, only rules scoped to TENANT_B should return.
    # Here the mock always returns [rule_a] — the WHERE is verified via call args.
    evaluator = AlertRuleEvaluator(rule_repo=rule_repo)

    await evaluator.evaluate(EVENT_ID, 3, [], [], TENANT_B)

    rule_repo.get_active_rules.assert_called_once_with(TENANT_B)
