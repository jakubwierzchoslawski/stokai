"""
Integration tests for Tier-1 evaluation flow.

Tests the full path: Tier1JudgeService → EvaluationRepository → EvaluationResult.
Uses mocked Anthropic client (no real API calls).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)


# ── Full tier-1 flow: JudgeService invokes LLM, parses, inserts ───────────────


@pytest.mark.asyncio
async def test_tier1_flow_end_to_end_with_mock_llm():
    """
    Integration test: Tier1JudgeService calls LLM → parses JSON →
    inserts via repo → returns EvaluationResult.

    Anthropic client is mocked; no network I/O.
    """
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = uuid.uuid4()

    # Mock LLM (Anthropic client)
    judge_json = json.dumps({
        "factual_grounding": 0.88,
        "confidence_calibration": 0.82,
        "internal_consistency": 0.90,
        "tool_use_appropriateness": 0.75,
        "overall_quality": 0.85,
        "reasoning": "Well-grounded recommendation with strong evidence.",
    })
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=(judge_json, 120, 180))

    # Mock repository
    expected_result = EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=run_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={
            "factual_grounding": 0.88,
            "confidence_calibration": 0.82,
            "internal_consistency": 0.90,
            "tool_use_appropriateness": 0.75,
        },
        overall_quality=0.85,
        prompt_version="v1.0",
        evaluated_at=datetime.now(tz=timezone.utc),
    )
    mock_repo = AsyncMock()
    mock_repo.insert_result = AsyncMock(return_value=expected_result)

    mock_loader = MagicMock()
    mock_loader.load = MagicMock(return_value="You are a judge evaluating recommendations.")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_loader,
    )

    result = await service.evaluate_output(
        run_id=run_id,
        agent_role="recommendation-analyst",
        prompt_version="v1.0",
        agent_input={
            "company_id": str(uuid.uuid4()),
            "market_context": "Q1 2026 earnings season",
        },
        agent_output={
            "signal": "BUY",
            "confidence": 0.82,
            "rationale": "Strong revenue growth with margin expansion.",
        },
        tool_outputs=[
            {"tool": "get_price_data", "result": {"close": 185.50}},
            {"tool": "get_earnings", "result": {"eps": 2.35, "yoy_growth": 0.15}},
        ],
    )

    assert result.run_id == run_id
    assert result.overall_quality == 0.85
    assert result.judge_model == "claude-opus-4-7"
    mock_repo.insert_result.assert_called_once()


@pytest.mark.asyncio
async def test_tier1_flow_langfuse_score_posted():
    """Integration: Langfuse tracer receives score after successful evaluation."""
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = uuid.uuid4()
    judge_json = json.dumps({
        "factual_grounding": 0.9,
        "overall_quality": 0.9,
        "reasoning": "Excellent.",
    })

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=(judge_json, 80, 100))

    eval_result = EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=run_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={"factual_grounding": 0.9},
        overall_quality=0.9,
        prompt_version="v1",
        evaluated_at=datetime.now(tz=timezone.utc),
    )
    mock_repo = AsyncMock()
    mock_repo.insert_result = AsyncMock(return_value=eval_result)

    mock_tracer = MagicMock()
    mock_tracer.score = MagicMock()

    mock_loader = MagicMock()
    mock_loader.load = MagicMock(return_value="judge prompt")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_loader,
        langfuse_tracer=mock_tracer,
    )

    await service.evaluate_output(
        run_id=run_id,
        agent_role="analyst",
        prompt_version="v1",
        agent_input={},
        agent_output={"signal": "BUY"},
        tool_outputs=[],
    )

    mock_tracer.score.assert_called_once_with(
        trace_id=str(run_id),
        name="tier1_overall_quality",
        value=0.9,
    )


@pytest.mark.asyncio
async def test_tier1_flow_llm_timeout_returns_fallback():
    """Integration: LLM timeout should produce fallback result (overall_quality=0.0)."""
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = uuid.uuid4()
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=TimeoutError("LLM timed out"))

    fallback = EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=run_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={},
        overall_quality=0.0,
        prompt_version="v1",
        evaluated_at=datetime.now(tz=timezone.utc),
    )
    mock_repo = AsyncMock()
    mock_repo.insert_result = AsyncMock(return_value=fallback)

    mock_loader = MagicMock()
    mock_loader.load = MagicMock(return_value="judge prompt")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_loader,
    )

    result = await service.evaluate_output(
        run_id=run_id,
        agent_role="analyst",
        prompt_version="v1",
        agent_input={},
        agent_output={},
        tool_outputs=[],
    )

    assert result.overall_quality == 0.0
    mock_repo.insert_result.assert_called_once()
