"""Step 9: CONFIDENCE CALC — composite confidence synthesis via Haiku 4.5.

Architecture enforcement:
  P-09 Full AI Lineage — second ai_audit_log entry written for this LLM call.
  C-001 — Haiku 4.5 for confidence synthesis (~$0.03/event).
  AC-001 — confidence stored on state for routing step.

Single Responsibility: LLM synthesis call, confidence extraction, audit log.
Dependency Inversion: LLM client, repository, Langfuse client injected.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from src.event_pipeline.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_CONFIDENCE_PROMPT_TEMPLATE = """\
You are an event confidence analyst. Based on the classification and analogy data,
compute a composite confidence score between 0.0 and 1.0 for this event alert.

Event category: {category}
Event intensity: {intensity}
Number of historical analogues: {analogue_count}

Respond with a single JSON object: {{"confidence": <float between 0.0 and 1.0>}}

Respond with valid JSON only.
"""


class ConfidenceCalcStep:
    """Pipeline Step 9: CONFIDENCE CALC.

    Calls the LLM to synthesise a composite confidence score from the
    classification result and analogy search results.

    Parameters
    ----------
    llm_client:
        Async LLM client exposing:
          ``synthesise_confidence(prompt: str) -> float``
    repo:
        Repository exposing ``write_audit_log(**kwargs)`` as an awaitable.
    langfuse_client:
        Langfuse trace/span lifecycle client.
    model_id:
        Model identifier for the audit log.
    """

    step_name: str = "s09_confidence_calc"

    def __init__(
        self,
        llm_client: Any,
        repo: Any,
        langfuse_client: Any,
        model_id: str = "claude-haiku-4-5",
    ) -> None:
        self._llm = llm_client
        self._repo = repo
        self._langfuse = langfuse_client
        self._model_id = model_id

    async def execute(self, state: PipelineState) -> PipelineState:
        """Call LLM for confidence synthesis and write audit log."""
        category_val = state.category.value if state.category else "UNKNOWN"
        intensity = state.intensity or 0
        analogue_count = len(state.analogues)

        prompt = _CONFIDENCE_PROMPT_TEMPLATE.format(
            category=category_val,
            intensity=intensity,
            analogue_count=analogue_count,
        )

        confidence = await self._llm.synthesise_confidence(prompt)

        # Clamp to [0.0, 1.0]
        confidence = max(0.0, min(1.0, float(confidence)))

        # Write audit log — P-09 Full AI Lineage (second LLM call)
        input_hash = hashlib.sha256(prompt.encode()).hexdigest()
        output_hash = hashlib.sha256(str(confidence).encode()).hexdigest()

        await self._repo.write_audit_log(
            tenant_id=state.tenant_id,
            agent_id="confidence_calc",
            model_id=self._model_id,
            langfuse_trace_id=state.langfuse_trace_id,
            step=self.step_name,
            input_hash=input_hash,
            output_hash=output_hash,
            confidence=confidence,
        )

        logger.info(
            "Step 9 (CONFIDENCE CALC): raw_event_id=%s confidence=%.3f",
            state.raw_event_id,
            confidence,
        )

        return state.model_copy(update={"confidence": confidence})
