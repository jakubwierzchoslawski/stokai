"""
Unit tests for TASK-005: Tier1JudgeService and evaluate_quality_node.

TDD: written before the implementations exist.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_run_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_eval_result(run_id: uuid.UUID, quality: float = 0.85) -> EvaluationResult:
    return EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=run_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={
            "factual_grounding": 0.9,
            "confidence_calibration": 0.8,
            "internal_consistency": 0.85,
            "tool_use_appropriateness": 0.8,
        },
        overall_quality=quality,
        prompt_version="abc123",
        evaluated_at=datetime.now(tz=timezone.utc),
    )


# ── Tier1JudgeService tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tier1_judge_service_returns_evaluation_result():
    """evaluate_output should return an EvaluationResult with overall_quality set."""
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = _make_run_id()
    mock_repo = AsyncMock()
    eval_result = _make_eval_result(run_id)
    mock_repo.insert_result = AsyncMock(return_value=eval_result)

    mock_llm = AsyncMock()
    judge_json = json.dumps({
        "factual_grounding": 0.9,
        "confidence_calibration": 0.8,
        "internal_consistency": 0.85,
        "tool_use_appropriateness": 0.8,
        "overall_quality": 0.85,
        "reasoning": "Good recommendation.",
    })
    mock_llm.complete = AsyncMock(return_value=(judge_json, 100, 200))

    mock_prompt_loader = MagicMock()
    mock_prompt_loader.load = MagicMock(return_value="You are a judge...")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_prompt_loader,
    )

    result = await service.evaluate_output(
        run_id=run_id,
        agent_role="recommendation-analyst",
        prompt_version="abc123",
        agent_input={"query": "Analyse AAPL"},
        agent_output={"signal": "BUY", "confidence": 0.8},
        tool_outputs=[{"tool": "price_data", "result": {}}],
    )

    assert result.run_id == run_id
    assert 0.0 <= result.overall_quality <= 1.0
    mock_repo.insert_result.assert_called_once()


@pytest.mark.asyncio
async def test_tier1_judge_service_malformed_json_returns_fallback():
    """Malformed LLM JSON response should produce fallback result with overall_quality=0.0."""
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = _make_run_id()
    mock_repo = AsyncMock()
    fallback_result = EvaluationResult(
        eval_id=uuid.uuid4(),
        run_id=run_id,
        eval_type="tier_1",
        judge_model="claude-opus-4-7",
        scores={},
        overall_quality=0.0,
        prompt_version="unknown",
        evaluated_at=datetime.now(tz=timezone.utc),
    )
    mock_repo.insert_result = AsyncMock(return_value=fallback_result)

    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=("NOT VALID JSON {{{", 10, 20))

    mock_prompt_loader = MagicMock()
    mock_prompt_loader.load = MagicMock(return_value="You are a judge...")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_prompt_loader,
    )

    # Should NOT raise — malformed JSON is handled gracefully
    result = await service.evaluate_output(
        run_id=run_id,
        agent_role="recommendation-analyst",
        prompt_version="abc123",
        agent_input={},
        agent_output={},
        tool_outputs=[],
    )
    assert result.overall_quality == 0.0


@pytest.mark.asyncio
async def test_tier1_judge_service_tool_outputs_bounded_to_50():
    """tool_outputs longer than 50 should be truncated to 50 before sending to judge."""
    from src.ai.evaluation.services.tier1_judge_service import Tier1JudgeService

    run_id = _make_run_id()
    mock_repo = AsyncMock()
    eval_result = _make_eval_result(run_id)
    mock_repo.insert_result = AsyncMock(return_value=eval_result)

    captured_calls: list[Any] = []

    async def _capture_complete(system_prompt, user_message, max_tokens, timeout_seconds):
        captured_calls.append(user_message)
        return (
            json.dumps({
                "factual_grounding": 0.9,
                "confidence_calibration": 0.8,
                "internal_consistency": 0.85,
                "tool_use_appropriateness": 0.8,
                "overall_quality": 0.85,
                "reasoning": "OK",
            }),
            100,
            200,
        )

    mock_llm = AsyncMock()
    mock_llm.complete = _capture_complete

    mock_prompt_loader = MagicMock()
    mock_prompt_loader.load = MagicMock(return_value="judge prompt")

    service = Tier1JudgeService(
        llm_client=mock_llm,
        evaluation_repo=mock_repo,
        prompt_loader=mock_prompt_loader,
    )

    tool_outputs = [{"tool": f"t{i}"} for i in range(100)]

    await service.evaluate_output(
        run_id=run_id,
        agent_role="analyst",
        prompt_version="v1",
        agent_input={},
        agent_output={},
        tool_outputs=tool_outputs,
    )

    # Verify the payload sent to the LLM only has 50 tool_outputs
    assert len(captured_calls) == 1
    payload = json.loads(captured_calls[0])
    assert len(payload["tool_outputs"]) == 50


# ── evaluate_quality_node tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_quality_node_sets_confidence_score():
    """evaluate_quality_node should set state.confidence_scores['tier1_eval']."""
    from src.ai.evaluation.nodes.evaluate_quality_node import evaluate_quality_node
    from src.ai.workflows.state import WorkflowState, WorkflowType

    run_id = uuid.uuid4()
    state = WorkflowState(
        workflow_id=run_id,
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
        recommendation={"signal": "BUY"},
    )

    mock_service = AsyncMock()
    eval_result = _make_eval_result(run_id, quality=0.75)
    mock_service.evaluate_output = AsyncMock(return_value=eval_result)

    result_state = await evaluate_quality_node(state, tier1_judge=mock_service)

    assert result_state.confidence_scores.get("tier1_eval") == 0.75


@pytest.mark.asyncio
async def test_evaluate_quality_node_continues_on_service_error():
    """evaluate_quality_node should catch exceptions and continue without raising."""
    from src.ai.evaluation.nodes.evaluate_quality_node import evaluate_quality_node
    from src.ai.workflows.state import WorkflowState, WorkflowType

    state = WorkflowState(
        workflow_id=uuid.uuid4(),
        workflow_type=WorkflowType.ON_DEMAND,
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        started_at=datetime.now(tz=timezone.utc),
    )

    mock_service = AsyncMock()
    mock_service.evaluate_output = AsyncMock(
        side_effect=TimeoutError("LLM timed out")
    )

    # Should NOT raise
    result_state = await evaluate_quality_node(state, tier1_judge=mock_service)

    # State should be returned unchanged (no tier1_eval key set)
    assert "tier1_eval" not in result_state.confidence_scores
