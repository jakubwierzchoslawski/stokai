"""
ITier1Judge — abstract interface for Tier-1 LLM-as-judge evaluation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.evaluation.schemas.evaluation_schemas import EvaluationResult


class ITier1Judge(ABC):
    """Abstract judge that evaluates agent outputs against quality dimensions."""

    @abstractmethod
    async def evaluate_output(
        self,
        run_id: UUID,
        agent_role: str,
        prompt_version: str,
        agent_input: dict,
        agent_output: dict,
        tool_outputs: list[dict],
    ) -> EvaluationResult:
        """
        Evaluate one agent output and return the scored EvaluationResult.

        Parameters
        ----------
        run_id:
            Workflow run ID to link this evaluation to.
        agent_role:
            Role identifier of the agent being evaluated.
        prompt_version:
            SHA / label of the prompt version used.
        agent_input:
            The input context passed to the agent.
        agent_output:
            The agent's output to be judged.
        tool_outputs:
            Tool call outputs (bounded to 50 entries).
        """
        ...
