"""
Unit tests for AlertRuleEvaluator (PLAN-F-005 implementation).

IAlertRuleRepository is mocked — no DB required.
All filter logic (intensity, category, ticker) is verified.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.alerts.models import AlertRuleRow
from src.alerts.services.alert_rule_evaluator import AlertRuleEvaluator


EVENT_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_rule(**overrides) -> AlertRuleRow:
    base = dict(
        rule_id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        user_id=uuid.uuid4(),
        user_email="u@e.com",
        event_categories=[],
        intensity_min=1,
        ticker_list=[],
        quiet_hours_start=None,
        quiet_hours_end=None,
        daily_limit=5,
        dedup_window_minutes=60,
        per_ticker_interval_hours=24,
        enabled=True,
    )
    base.update(overrides)
    return AlertRuleRow(**base)


def _repo(rules: list[AlertRuleRow]) -> AsyncMock:
    repo = AsyncMock()
    repo.get_active_rules = AsyncMock(return_value=rules)
    return repo


# ── Intensity filter ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rule_intensity_min_3_matches_event_intensity_3():
    """Rule with intensity_min=3 matches event with intensity=3."""
    rule = _make_rule(intensity_min=3)
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 3, ["trade"], ["AAPL"], TENANT_ID)

    assert len(matches) == 1


@pytest.mark.asyncio
async def test_rule_intensity_min_3_does_not_match_event_intensity_2():
    """Rule with intensity_min=3 does not match event with intensity=2."""
    rule = _make_rule(intensity_min=3)
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, ["trade"], ["AAPL"], TENANT_ID)

    assert matches == []


# ── Category filter ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_event_categories_on_rule_matches_any_category():
    """Rule with event_categories=[] matches any event category (wildcard)."""
    rule = _make_rule(event_categories=[])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, ["geopolitical"], ["AAPL"], TENANT_ID)

    assert len(matches) == 1


@pytest.mark.asyncio
async def test_category_mismatch_excludes_rule():
    """Rule with event_categories=["conflict"] does not match event with categories=["trade"]."""
    rule = _make_rule(event_categories=["conflict"])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, ["trade"], [], TENANT_ID)

    assert matches == []


@pytest.mark.asyncio
async def test_category_partial_match_includes_rule():
    """Rule matches when at least one category overlaps."""
    rule = _make_rule(event_categories=["conflict", "sanctions"])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, ["sanctions", "trade"], [], TENANT_ID)

    assert len(matches) == 1


# ── Ticker filter ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_ticker_list_on_rule_matches_regardless():
    """Rule with ticker_list=[] matches regardless of matched_tickers."""
    rule = _make_rule(ticker_list=[])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, [], ["MSFT", "GOOG"], TENANT_ID)

    assert len(matches) == 1


@pytest.mark.asyncio
async def test_ticker_list_aapl_matches_only_when_aapl_in_tickers():
    """Rule with ticker_list=["AAPL"] matches only when "AAPL" in matched_tickers."""
    rule = _make_rule(ticker_list=["AAPL"])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    # Should match
    matches = await evaluator.evaluate(EVENT_ID, 2, [], ["AAPL", "TSLA"], TENANT_ID)
    assert len(matches) == 1

    # Should not match
    matches2 = await evaluator.evaluate(EVENT_ID, 2, [], ["TSLA"], TENANT_ID)
    assert matches2 == []


@pytest.mark.asyncio
async def test_matched_tickers_on_result_is_intersection():
    """RuleMatch.matched_tickers contains only tickers that intersected the rule's list."""
    rule = _make_rule(ticker_list=["AAPL", "MSFT"])
    evaluator = AlertRuleEvaluator(_repo([rule]))

    matches = await evaluator.evaluate(EVENT_ID, 2, [], ["AAPL", "TSLA"], TENANT_ID)

    assert len(matches) == 1
    assert "AAPL" in matches[0].matched_tickers
    assert "TSLA" not in matches[0].matched_tickers


# ── Empty results ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_empty_list_when_no_active_rules():
    """Returns empty list when get_active_rules returns no rows."""
    evaluator = AlertRuleEvaluator(_repo([]))

    matches = await evaluator.evaluate(EVENT_ID, 3, ["conflict"], ["AAPL"], TENANT_ID)

    assert matches == []


# ── Multiple rules ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_rules_multiple_matches():
    """Returns multiple RuleMatch objects when multiple rules match."""
    rules = [_make_rule(intensity_min=1) for _ in range(3)]
    evaluator = AlertRuleEvaluator(_repo(rules))

    matches = await evaluator.evaluate(EVENT_ID, 2, [], [], TENANT_ID)

    assert len(matches) == 3


# ── tenant_id=None handling ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_id_none_returns_empty_list():
    """tenant_id=None returns empty list without calling the repo."""
    repo = _repo([_make_rule()])
    evaluator = AlertRuleEvaluator(repo)

    matches = await evaluator.evaluate(EVENT_ID, 3, [], [], None)

    assert matches == []
    repo.get_active_rules.assert_not_called()
