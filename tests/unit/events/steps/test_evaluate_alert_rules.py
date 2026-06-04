"""
Unit tests for the evaluate_alert_rules step.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.events.cost_accumulator import CostAccumulator
from src.events.models import ClassificationResult, PipelineContext, RawEvent
from src.events.steps.evaluate_alert_rules import evaluate_alert_rules


def _make_ctx(intensity: int = 4) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "T", "summary": "S"},
        ),
        event_id=uuid.uuid4(),
        classification=ClassificationResult(
            category=["sanctions"],
            intensity=intensity,
            sentiment="negative",
            geo_regions=["EMEA"],
            affected_sectors=["energy"],
            cameo_code="163",
        ),
        cost_accumulator=CostAccumulator(),
        langfuse_trace_id="trace-001",
    )


def _make_rule_match() -> RuleMatch:
    return RuleMatch(
        rule_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        channels=["email"],
    )


@pytest.mark.asyncio
class TestEvaluateAlertRules:

    async def test_matches_stored_in_ctx_rule_match(self) -> None:
        ctx = _make_ctx(intensity=4)
        matches = [_make_rule_match()]
        evaluator = AsyncMock()
        evaluator.evaluate = AsyncMock(return_value=matches)

        result = await evaluate_alert_rules(ctx, evaluator)

        assert result.rule_match == matches
        evaluator.evaluate.assert_called_once()

    async def test_no_matches_stored_as_empty_list(self) -> None:
        ctx = _make_ctx(intensity=2)
        evaluator = AsyncMock()
        evaluator.evaluate = AsyncMock(return_value=[])

        result = await evaluate_alert_rules(ctx, evaluator)

        assert result.rule_match == []
