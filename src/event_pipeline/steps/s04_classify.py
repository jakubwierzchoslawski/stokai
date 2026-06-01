"""Step 4: CLASSIFY — Haiku 4.5 LLM classification of event category and intensity.

Architecture enforcement:
  P-01 Provider Abstraction — LLM accessed via injected client abstraction.
  P-09 Full AI Lineage — ai_audit_log entry written per classify call.
  C-005 — model config from YAML; provider swap requires only YAML edit.
  AC-004 — validates category against 6-value enum and intensity 1–5.

Single Responsibility: LLM call, response validation, and audit log write.
Dependency Inversion: LLM client, repository, and Langfuse client injected.
"""
from __future__ import annotations

import logging
from typing import Any

from src.event_pipeline.exceptions import (
    ClassificationError,
    InvalidCategoryError,
    InvalidIntensityError,
)
from src.event_pipeline.pipeline_state import EventCategory, PipelineState

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {c.value for c in EventCategory}
_CLASSIFY_PROMPT_TEMPLATE = """\
You are an event classification assistant. Classify the following event.

Event description:
{description}

Respond with a JSON object containing exactly two fields:
- "category": one of {categories}
- "intensity": integer from 1 (very low) to 5 (very high)

Respond with valid JSON only. No explanation.
"""


class ClassifyStep:
    """Pipeline Step 4: CLASSIFY.

    Calls the LLM client with a structured prompt and validates the response.
    Writes an ai_audit_log entry with model metadata and trace ID.

    Parameters
    ----------
    llm_client:
        Async LLM client exposing ``classify(description) -> dict``.
    repo:
        Repository exposing ``write_audit_log(**kwargs)`` as an awaitable.
    langfuse_client:
        Langfuse trace/span lifecycle client.
    model_id:
        Model identifier for the audit log (default: claude-haiku-4-5).
    """

    step_name: str = "s04_classify"

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
        """Classify the event and validate LLM output."""
        description = state.event_description or str(state.payload.raw_payload)

        prompt = _CLASSIFY_PROMPT_TEMPLATE.format(
            description=description,
            categories=", ".join(sorted(_VALID_CATEGORIES)),
        )

        try:
            result = await self._llm.classify(prompt)
        except Exception as exc:
            raise ClassificationError(
                step_name=self.step_name,
                detail=f"LLM call failed: {exc}",
            ) from exc

        category_raw = result.get("category", "")
        intensity_raw = result.get("intensity")

        # Validate category
        if category_raw not in _VALID_CATEGORIES:
            raise InvalidCategoryError(
                step_name=self.step_name,
                detail=(
                    f"LLM returned unknown category {category_raw!r}. "
                    f"Valid values: {sorted(_VALID_CATEGORIES)}"
                ),
            )

        # Validate intensity
        try:
            intensity = int(intensity_raw)
        except (TypeError, ValueError):
            raise InvalidIntensityError(
                step_name=self.step_name,
                detail=f"LLM returned non-integer intensity: {intensity_raw!r}",
            )

        if not 1 <= intensity <= 5:
            raise InvalidIntensityError(
                step_name=self.step_name,
                detail=f"LLM returned intensity {intensity} outside range 1–5",
            )

        # Write audit log — P-09 Full AI Lineage
        await self._repo.write_audit_log(
            tenant_id=state.tenant_id,
            agent_id="classify_event",
            model_id=self._model_id,
            langfuse_trace_id=state.langfuse_trace_id,
            step=self.step_name,
            input_hash=_hash_text(description),
            output_hash=_hash_text(str(result)),
            confidence=None,  # classify step does not produce a confidence score
        )

        category = EventCategory(category_raw)
        logger.info(
            "Step 4 (CLASSIFY): raw_event_id=%s category=%s intensity=%d",
            state.raw_event_id,
            category.value,
            intensity,
        )

        return state.model_copy(update={
            "category": category,
            "intensity": intensity,
        })


def _hash_text(text: str) -> str:
    """Return SHA-256 hex digest of text for audit logging."""
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()
