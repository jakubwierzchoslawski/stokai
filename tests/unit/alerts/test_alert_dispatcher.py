"""
Unit tests for AlertDispatcher (PLAN-F-005 implementation).

All external dependencies are mocked. Tests verify suppression paths,
happy-path dispatch, SendGridError escalation, and disclaimer inclusion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.alerts.exceptions import AlertDispatchError, BudgetHardStopError, SendGridError
from src.alerts.interfaces.i_alert_dispatcher import AlertDispatchResult
from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.alerts.models import ActionSignal, AlertStatus, AlertTextResult, BudgetState
from src.alerts.services.alert_dispatcher import AlertDispatcher
from src.alerts.services.anti_fatigue_checker import AntiFatigueChecker
from src.alerts.services.budget_enforcer import BudgetEnforcer


USER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()
EVENT_ID = uuid.uuid4()
RULE_ID = uuid.uuid4()


def _make_rule_match(**overrides) -> RuleMatch:
    base = dict(
        rule_id=RULE_ID,
        user_id=USER_ID,
        user_email="trader@example.com",
        tenant_id=TENANT_ID,
        channels=["email"],
        matched_tickers=["AAPL"],
    )
    base.update(overrides)
    return RuleMatch(**base)


def _make_alert_text_result(**overrides) -> AlertTextResult:
    base = dict(
        alert_text="An important event occurred affecting your holdings. AI signal: WATCH.",
        action_signal=ActionSignal.WATCH,
        confidence=0.75,
        sample_size=8,
        low_sample_disclaimer=False,
    )
    base.update(overrides)
    return AlertTextResult(**base)


def _make_fatigue_repo(
    dispatched_today: int = 0,
    last_dispatch=None,
    recent_ids=None,
    budget_state=None,
    spent_today=0.0,
) -> AsyncMock:
    repo = AsyncMock()
    repo.count_dispatched_today = AsyncMock(return_value=dispatched_today)
    repo.get_last_dispatch_for_ticker = AsyncMock(return_value=last_dispatch)
    repo.get_recent_event_alert_ids = AsyncMock(return_value=recent_ids or [])
    repo.get_budget_state = AsyncMock(
        return_value=budget_state
        or BudgetState(
            daily_budget_usd=10.0,
            spent_today_usd=spent_today,
            alert_threshold_pct=80.0,
            hard_stop_pct=100.0,
        )
    )
    repo.get_spent_today_usd = AsyncMock(return_value=spent_today)
    return repo


def _make_alert_repo() -> AsyncMock:
    repo = AsyncMock()
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


def _make_dispatcher(
    fatigue_repo=None,
    anti_fatigue_checker=None,
    budget_enforcer=None,
    email_sender=None,
    alert_repo=None,
) -> AlertDispatcher:
    return AlertDispatcher(
        fatigue_repo=fatigue_repo or _make_fatigue_repo(),
        anti_fatigue_checker=anti_fatigue_checker or AntiFatigueChecker(),
        budget_enforcer=budget_enforcer or BudgetEnforcer(),
        email_sender=email_sender or _make_email_sender(),
        alert_repo=alert_repo or _make_alert_repo(),
    )


# ── Anti-fatigue suppression ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_limit_reached_returns_suppressed_and_silent_logs():
    """At daily limit: returns SUPPRESSED_DAILY_LIMIT, insert_silent_log called, send NOT called."""
    # daily_limit=5 in stub_rule; dispatched_today=5 → suppressed
    fatigue_repo = _make_fatigue_repo(dispatched_today=5)
    alert_repo = _make_alert_repo()
    email_sender = _make_email_sender()

    dispatcher = _make_dispatcher(
        fatigue_repo=fatigue_repo,
        alert_repo=alert_repo,
        email_sender=email_sender,
    )

    result = await dispatcher.dispatch(
        _make_rule_match(), _make_alert_text_result(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_DAILY_LIMIT
    assert result.channel == "silent"
    alert_repo.insert_silent_log.assert_called_once()
    email_sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_budget_hard_stop_returns_suppressed_budget_and_silent_logs():
    """Budget hard stop: returns SUPPRESSED_BUDGET, insert_silent_log called, send NOT called."""
    # spent=10, budget=10, hard_stop=100% → hard stop raises
    budget = BudgetState(
        daily_budget_usd=10.0,
        spent_today_usd=10.0,
        alert_threshold_pct=80.0,
        hard_stop_pct=100.0,
    )
    fatigue_repo = _make_fatigue_repo(budget_state=budget)
    alert_repo = _make_alert_repo()
    email_sender = _make_email_sender()

    dispatcher = _make_dispatcher(
        fatigue_repo=fatigue_repo,
        alert_repo=alert_repo,
        email_sender=email_sender,
    )

    result = await dispatcher.dispatch(
        _make_rule_match(), _make_alert_text_result(), EVENT_ID
    )

    assert result.status == AlertStatus.SUPPRESSED_BUDGET
    assert result.channel == "silent"
    alert_repo.insert_silent_log.assert_called_once()
    email_sender.send.assert_not_called()


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_gates_pass_email_sender_called_with_correct_args():
    """All gates pass: IEmailSender.send called with to_email, subject, html_body."""
    email_sender = _make_email_sender()
    alert_repo = _make_alert_repo()

    dispatcher = _make_dispatcher(
        email_sender=email_sender,
        alert_repo=alert_repo,
    )
    rule_match = _make_rule_match(user_email="trader@example.com")
    text_result = _make_alert_text_result()

    await dispatcher.dispatch(rule_match, text_result, EVENT_ID)

    email_sender.send.assert_called_once()
    call_kwargs = email_sender.send.call_args[1] if email_sender.send.call_args[1] else {}
    call_args = email_sender.send.call_args[0]
    # Accept either positional or keyword args
    to_email = call_kwargs.get("to_email") or call_args[0]
    assert to_email == "trader@example.com"


@pytest.mark.asyncio
async def test_all_gates_pass_insert_alert_called_with_dispatched_status():
    """All gates pass: insert_alert called with status=DISPATCHED, channel='email'."""
    alert_repo = _make_alert_repo()

    dispatcher = _make_dispatcher(alert_repo=alert_repo)

    result = await dispatcher.dispatch(
        _make_rule_match(), _make_alert_text_result(), EVENT_ID
    )

    assert result.status == AlertStatus.DISPATCHED
    assert result.channel == "email"
    alert_repo.insert_alert.assert_called_once()
    inserted_row = alert_repo.insert_alert.call_args[0][0]
    assert inserted_row.status == AlertStatus.DISPATCHED
    assert inserted_row.channel == "email"


# ── SendGridError escalation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sendgrid_error_raises_alert_dispatch_error_no_silent_log():
    """SendGridError during send raises AlertDispatchError; no silent-log inserted."""
    email_sender = _make_email_sender(raises=SendGridError("Failed", status_code=500))
    alert_repo = _make_alert_repo()

    dispatcher = _make_dispatcher(email_sender=email_sender, alert_repo=alert_repo)

    with pytest.raises(AlertDispatchError):
        await dispatcher.dispatch(
            _make_rule_match(), _make_alert_text_result(), EVENT_ID
        )

    alert_repo.insert_silent_log.assert_not_called()


# ── Low sample disclaimer ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_low_sample_disclaimer_in_html_body_when_flag_true():
    """low_sample_disclaimer=True results in disclaimer text in the html_body sent."""
    email_sender = _make_email_sender()

    dispatcher = _make_dispatcher(email_sender=email_sender)
    text_result = _make_alert_text_result(low_sample_disclaimer=True)

    await dispatcher.dispatch(_make_rule_match(), text_result, EVENT_ID)

    call_args = email_sender.send.call_args
    html_body = (
        call_args[1].get("html_body")
        or (call_args[0][2] if len(call_args[0]) > 2 else "")
    )
    assert "fewer than 5" in html_body or "low" in html_body.lower()


# ── log_silent ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_silent_completes_without_error():
    """log_silent with suppression_status completes without raising."""
    dispatcher = _make_dispatcher()

    # Should not raise
    await dispatcher.log_silent(EVENT_ID, TENANT_ID, AlertStatus.SUPPRESSED_DEDUP)
