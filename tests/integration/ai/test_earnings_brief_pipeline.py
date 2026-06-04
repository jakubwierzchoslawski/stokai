"""
Integration tests for the full Earnings Risk Brief pipeline.

Tests the end-to-end flow with mocked AI calls and mocked DB repositories.
No real database or LLM required.

PLAN-F-009 TASK-009

Tests cover:
- Full pipeline with mocked AI returns a valid EarningsBriefState
- Idempotency: a second run for the same company+tenant+date is skipped
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.workflows.earnings_brief.state import EarningsBriefState, ScenarioTree


# ── Shared test fixtures ──────────────────────────────────────────────────────


def _make_state(
    company_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> EarningsBriefState:
    return EarningsBriefState(
        workflow_id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        earnings_date=date.today(),
        started_at=datetime.now(tz=timezone.utc),
    )


def _make_registry() -> MagicMock:
    registry = MagicMock()
    defn = MagicMock()
    defn.role_id = "earnings-analyst"
    registry.resolve.return_value = defn
    return registry


_GOOD_SCENARIO_RESULT = {
    "output": {
        "bull": {
            "probability": 0.30,
            "rationale": "Beat expected on strong revenue",
            "macro_drivers": ["low rates"],
            "sector_drivers": ["sector growth"],
            "implied_price_impact_pct": 6.0,
        },
        "base": {
            "probability": 0.50,
            "rationale": "In-line results",
            "macro_drivers": ["stable inflation"],
            "sector_drivers": ["average sector performance"],
            "implied_price_impact_pct": 1.0,
        },
        "bear": {
            "probability": 0.20,
            "rationale": "Margin compression risk",
            "macro_drivers": ["rising costs"],
            "sector_drivers": ["competitive pressure"],
            "implied_price_impact_pct": -5.0,
        },
        "analogies": [],
        "macro_summary": "Macro environment is broadly supportive",
        "sector_summary": "Sector peers reported mixed results",
    },
    "confidence": 0.82,
    "cost_usd": 0.05,
    "input_tokens": 800,
    "output_tokens": 400,
}

_GOOD_RECOMMENDATION_RESULT = {
    "output": {
        "action": "WATCH",
        "rationale": "Monitor closely; base case in-line.",
        "confidence": 0.82,
    },
    "confidence": 0.82,
    "cost_usd": 0.03,
    "input_tokens": 400,
    "output_tokens": 200,
}

_GOOD_NARRATIVE_RESULT = {
    "output": {
        "title": "Earnings Brief: ACME Corp",
        "sections": ["executive_summary", "scenario_tree", "recommendation"],
        "text": "ACME Corp is expected to report Q2 2026 results in line with consensus.",
    },
    "confidence": 0.82,
    "cost_usd": 0.02,
    "input_tokens": 600,
    "output_tokens": 300,
}


# ── Full pipeline test ────────────────────────────────────────────────────────


class TestEarningsBriefPipelineFullFlow:
    """Full Earnings Risk Brief pipeline with mocked AI."""

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_completed_state(self):
        """End-to-end pipeline returns EarningsBriefState with all fields set."""
        from src.ai.workflows.earnings_brief.workflow import build_earnings_brief_workflow

        registry = _make_registry()
        workflow = build_earnings_brief_workflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        with patch.multiple(
            "src.ai.workflows.earnings_brief.workflow",
            _invoke_scenario_analyst=AsyncMock(return_value=_GOOD_SCENARIO_RESULT),
            _invoke_recommendation_agent=AsyncMock(
                return_value=_GOOD_RECOMMENDATION_RESULT
            ),
            _invoke_narrative_writer=AsyncMock(return_value=_GOOD_NARRATIVE_RESULT),
        ):
            result = await workflow.ainvoke(state)

        assert isinstance(result, EarningsBriefState)
        assert result.scenario_tree is not None
        assert isinstance(result.scenario_tree, ScenarioTree)
        assert result.recommendation is not None
        assert result.report is not None
        assert result.overall_confidence is not None
        assert result.overall_confidence == pytest.approx(0.82)
        assert result.requires_hil is False  # 0.82 >= 0.70

    @pytest.mark.asyncio
    async def test_full_pipeline_accumulates_cost(self):
        """Total cost_usd is sum of all agent costs after pipeline completes."""
        from src.ai.workflows.earnings_brief.workflow import build_earnings_brief_workflow

        registry = _make_registry()
        workflow = build_earnings_brief_workflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        with patch.multiple(
            "src.ai.workflows.earnings_brief.workflow",
            _invoke_scenario_analyst=AsyncMock(return_value=_GOOD_SCENARIO_RESULT),
            _invoke_recommendation_agent=AsyncMock(
                return_value=_GOOD_RECOMMENDATION_RESULT
            ),
            _invoke_narrative_writer=AsyncMock(return_value=_GOOD_NARRATIVE_RESULT),
        ):
            result = await workflow.ainvoke(state)

        # 0.05 + 0.03 + 0.02 = 0.10
        assert result.cost_usd == pytest.approx(0.10)

    @pytest.mark.asyncio
    async def test_full_pipeline_validates_scenario_probabilities(self):
        """Pipeline raises ValidationError if scenario probabilities don't sum to 1."""
        from src.ai.workflows.earnings_brief.workflow import build_earnings_brief_workflow
        from pydantic import ValidationError

        registry = _make_registry()
        workflow = build_earnings_brief_workflow(registry=registry, cost_ceiling_usd=5.0)
        state = _make_state()

        bad_scenario_result = {
            **_GOOD_SCENARIO_RESULT,
            "output": {
                **_GOOD_SCENARIO_RESULT["output"],
                "bull": {**_GOOD_SCENARIO_RESULT["output"]["bull"], "probability": 0.50},
                "base": {**_GOOD_SCENARIO_RESULT["output"]["base"], "probability": 0.50},
                "bear": {**_GOOD_SCENARIO_RESULT["output"]["bear"], "probability": 0.50},
            },
        }

        with patch(
            "src.ai.workflows.earnings_brief.workflow._invoke_scenario_analyst",
            AsyncMock(return_value=bad_scenario_result),
        ):
            with pytest.raises((ValidationError, ValueError)):
                await workflow.ainvoke(state)


# ── Idempotency test ──────────────────────────────────────────────────────────


class TestEarningsBriefIdempotency:
    """Idempotency: no duplicate brief runs for the same company+tenant+date."""

    @pytest.mark.asyncio
    async def test_detect_skips_when_brief_already_exists(self):
        """detect_t1_earnings_async skips companies with existing brief runs."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        tenant_id = uuid.uuid4()
        company_id = uuid.uuid4()
        today = date.today()

        mock_event = MagicMock()
        mock_event.company_id = company_id
        mock_event.tenant_id = tenant_id
        mock_event.earnings_date = today

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()

        mock_event_repo.get_upcoming = AsyncMock(return_value=[mock_event])
        mock_run_repo.exists = AsyncMock(return_value=True)  # already exists

        mock_brief_task = MagicMock()
        mock_brief_task.apply_async = MagicMock()

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.earnings_brief_task",
            mock_brief_task,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _detect_t1_earnings_async(
                tenant_id_str=str(tenant_id),
            )

        # No dispatch — brief already exists
        mock_brief_task.apply_async.assert_not_called()
        assert result["dispatched"] == 0
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_detect_dispatches_only_once_per_company_date(self):
        """For a given company+tenant+date, exactly one brief is dispatched."""
        from src.ai.tasks.earnings_brief_task import _detect_t1_earnings_async

        tenant_id = uuid.uuid4()
        company_id = uuid.uuid4()
        today = date.today()

        mock_event = MagicMock()
        mock_event.company_id = company_id
        mock_event.tenant_id = tenant_id
        mock_event.earnings_date = today

        mock_session = AsyncMock()
        mock_event_repo = AsyncMock()
        mock_run_repo = AsyncMock()

        mock_event_repo.get_upcoming = AsyncMock(return_value=[mock_event])
        mock_run_repo.exists = AsyncMock(return_value=False)  # not yet exists

        mock_brief_task = MagicMock()
        mock_brief_task.apply_async = MagicMock()

        with patch(
            "src.ai.tasks.earnings_brief_task._get_db_session"
        ) as mock_ctx, patch(
            "src.ai.tasks.earnings_brief_task.EarningsEventRepository",
            return_value=mock_event_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.EarningsBriefRunRepository",
            return_value=mock_run_repo,
        ), patch(
            "src.ai.tasks.earnings_brief_task.earnings_brief_task",
            mock_brief_task,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _detect_t1_earnings_async(
                tenant_id_str=str(tenant_id),
            )

        # Exactly one dispatch
        mock_brief_task.apply_async.assert_called_once()
        assert result["dispatched"] == 1
        assert result["skipped"] == 0
