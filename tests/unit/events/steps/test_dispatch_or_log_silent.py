"""
Unit tests for dispatch_or_log_silent step.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.events.cost_accumulator import CostAccumulator
from src.events.models import ClassificationResult, PipelineContext, RawEvent
from src.events.steps.dispatch_or_log_silent import dispatch_or_log_silent


def _make_ctx(rule_matches=None) -> PipelineContext:
    return PipelineContext(
        raw_event=RawEvent(
            source_provider="gdelt",
            occurred_at=datetime(2024, 1, 15, tzinfo=timezone.utc),
            raw_payload={"title": "T", "summary": "S"},
        ),
        event_id=uuid.uuid4(),
        classification=ClassificationResult(
            category=["conflict"],
            intensity=4,
            sentiment="negative",
            geo_regions=["EMEA"],
            affected_sectors=["energy"],
            cameo_code="14",
        ),
        alert_text="Critical energy sector alert: sanctions imposed.",
        rule_match=rule_matches,
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
class TestDispatchOrLogSilent:

    async def test_dispatch_called_once_per_match(self) -> None:
        matches = [_make_rule_match(), _make_rule_match()]
        ctx = _make_ctx(rule_matches=matches)
        dispatcher = AsyncMock()
        alert_repo = AsyncMock()
        alert_repo.insert_alert = AsyncMock(return_value=uuid.uuid4())

        result = await dispatch_or_log_silent(ctx, dispatcher, alert_repo)

        assert dispatcher.dispatch.call_count == 2
        assert dispatcher.log_silent.call_count == 0
        assert result.alert_dispatched is True

    async def test_log_silent_called_when_no_matches(self) -> None:
        ctx = _make_ctx(rule_matches=[])
        dispatcher = AsyncMock()
        alert_repo = AsyncMock()

        result = await dispatch_or_log_silent(ctx, dispatcher, alert_repo)

        dispatcher.log_silent.assert_called_once()
        dispatcher.dispatch.assert_not_called()
        assert result.silent_logged is True

    async def test_insert_silent_log_called_when_no_rules_matched(self) -> None:
        ctx = _make_ctx(rule_matches=[])
        dispatcher = AsyncMock()
        alert_repo = AsyncMock()

        await dispatch_or_log_silent(ctx, dispatcher, alert_repo)

        alert_repo.insert_silent_log.assert_called_once_with(
            ctx.event_id, ctx.raw_event.tenant_id
        )
