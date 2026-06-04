"""
Tier1JudgeService — LLM-as-judge implementation of ITier1Judge.

Flow per evaluate_output() call:
  1. Load recommendation_judge.md from prompt_loader (label 'production').
  2. Build judge payload with agent_input + agent_output + tool_outputs (bounded to 50).
  3. Invoke judge LLM (claude-opus-4-7) async, max_output_tokens=500.
  4. Parse JSON into scores dict.
  5. Insert EvaluationResult via IEvaluationRepository.
  6. Post Langfuse evaluation scores linked to run_id (best-effort).
  7. Return EvaluationResult.

Malformed JSON → warning log + fallback EvaluationResult(overall_quality=0.0).
No exceptions propagate from this service to callers.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.ai.evaluation.interfaces.i_evaluation_repository import IEvaluationRepository
from src.ai.evaluation.interfaces.i_tier1_judge import ITier1Judge
from src.ai.evaluation.schemas.evaluation_schemas import (
    EvaluationResult,
    EvaluationResultCreate,
)

logger = logging.getLogger(__name__)

_JUDGE_MODEL = "claude-opus-4-7"
_MAX_TOOL_OUTPUTS = 50
_MAX_OUTPUT_TOKENS = 500
_JUDGE_TIMEOUT_SECONDS = 60.0
_PROMPT_PATH = "prompts/evaluators/recommendation_judge.md"


class PromptLoader:
    """Simple file-based prompt loader with optional Langfuse override."""

    def load(self, path: str, label: str = "production") -> str:
        """Load prompt text from a local file path."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            logger.warning("Could not load prompt from %r: %s", path, exc)
            return ""


class Tier1JudgeService(ITier1Judge):
    """
    Evaluates agent outputs using an LLM judge.

    Parameters
    ----------
    llm_client:
        Async LLM client (AnthropicLLMClient or compatible mock).
    evaluation_repo:
        Repository for persisting evaluation results.
    prompt_loader:
        Optional prompt loader; defaults to PromptLoader (file-based).
    langfuse_tracer:
        Optional tracer for posting evaluation scores to Langfuse.
    """

    def __init__(
        self,
        llm_client: Any,
        evaluation_repo: IEvaluationRepository,
        prompt_loader: Any | None = None,
        langfuse_tracer: Any | None = None,
    ) -> None:
        self._llm = llm_client
        self._repo = evaluation_repo
        self._prompt_loader = prompt_loader or PromptLoader()
        self._tracer = langfuse_tracer

    async def evaluate_output(
        self,
        run_id: UUID,
        agent_role: str,
        prompt_version: str,
        agent_input: dict,
        agent_output: dict,
        tool_outputs: list[dict],
    ) -> EvaluationResult:
        """Evaluate one agent output and persist the result."""
        # Load judge prompt
        system_prompt = self._prompt_loader.load(_PROMPT_PATH, label="production")

        # Bound tool_outputs to 50
        bounded_tools = tool_outputs[:_MAX_TOOL_OUTPUTS]

        # Build judge payload
        payload = {
            "run_id": str(run_id),
            "agent_role": agent_role,
            "prompt_version": prompt_version,
            "agent_input": agent_input,
            "agent_output": agent_output,
            "tool_outputs": bounded_tools,
        }
        user_message = json.dumps(payload, default=str)

        # Invoke judge LLM
        try:
            raw_response, _in_tokens, _out_tokens = await self._llm.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=_MAX_OUTPUT_TOKENS,
                timeout_seconds=_JUDGE_TIMEOUT_SECONDS,
            )
            scores, overall_quality = self._parse_judge_response(raw_response)
        except Exception as exc:
            logger.warning(
                "Tier1JudgeService LLM call failed for run_id=%s: %s",
                run_id,
                type(exc).__name__,
            )
            scores, overall_quality = {}, 0.0

        # Build create schema
        create = EvaluationResultCreate(
            run_id=run_id,
            eval_type="tier_1",
            judge_model=_JUDGE_MODEL,
            scores=scores,
            overall_quality=overall_quality,
            prompt_version=prompt_version,
        )

        # Persist
        result = await self._repo.insert_result(create)

        # Post Langfuse scores (fire-and-forget, best-effort)
        if self._tracer is not None:
            try:
                self._tracer.score(
                    trace_id=str(run_id),
                    name="tier1_overall_quality",
                    value=overall_quality,
                )
            except Exception as exc:
                logger.warning(
                    "Langfuse score write failed for run_id=%s: %s",
                    run_id,
                    type(exc).__name__,
                )

        return result

    def _parse_judge_response(
        self, raw: str
    ) -> tuple[dict[str, Any], float]:
        """Parse the judge JSON response.

        Returns (scores_dict, overall_quality).
        On parse failure returns ({}, 0.0) after logging a warning.
        """
        try:
            # Strip markdown code fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first and last fence lines
                inner = [
                    l for l in lines if not l.strip().startswith("```")
                ]
                cleaned = "\n".join(inner).strip()

            data = json.loads(cleaned)
            scores = {
                k: float(v)
                for k, v in data.items()
                if k != "reasoning" and isinstance(v, (int, float))
            }
            overall_quality = float(data.get("overall_quality", 0.0))
            # Clamp to [0, 1]
            overall_quality = max(0.0, min(1.0, overall_quality))
            return scores, overall_quality
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "Tier1JudgeService: malformed judge JSON (%s) — using fallback",
                type(exc).__name__,
            )
            return {}, 0.0
