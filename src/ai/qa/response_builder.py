"""
ai.qa.response_builder — QAResponseBuilder: builds QAAnswer from agent output.

PLAN-F-027 TASK-003

QAResponseBuilder.build() accepts raw agent output dict, a cost_limited flag,
and the accumulated cost, and returns a structured QAAnswer.

If cost_limited=True: sets QAAnswer.cost_limited=True and trims sources to 3
(the first 3 are the most relevant — the agent orders them).

Design:
  - No LLM calls — pure data transformation.
  - Extracts sources from agent output's supporting_data.sources or sources.
  - Falls back gracefully if agent output is missing optional fields.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Domain schemas ─────────────────────────────────────────────────────────────


class QASource(BaseModel):
    """A source cited in a Q&A answer."""

    type: str  # "event"|"filing"|"price_bar"|"recommendation"|"semantic_fact"
    id: str
    description: str


class QAAnswer(BaseModel):
    """Structured Q&A answer with cited sources, confidence, and cost metadata."""

    answer_text: str
    sources: list[QASource] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    cost_usd: float = 0.0
    cost_limited: bool = False


# ── Builder ────────────────────────────────────────────────────────────────────

# Maximum sources shown when cost_limited=True (trim to this many)
_MAX_SOURCES_WHEN_LIMITED = 3


class QAResponseBuilder:
    """Transforms raw agent output dict into a typed QAAnswer.

    Usage::

        builder = QAResponseBuilder()
        answer = builder.build(
            agent_output={"answer": "...", "confidence": 0.85, "sources": [...]},
            cost_limited=False,
            accumulated_cost=0.12,
        )
    """

    def build(
        self,
        agent_output: dict[str, Any],
        cost_limited: bool,
        accumulated_cost: float,
    ) -> QAAnswer:
        """Build a QAAnswer from agent output.

        Args:
            agent_output: Dict returned by the qa_analyst agent. Expected keys:
                - answer (str, required)
                - confidence (float, optional, 0.0-1.0)
                - sources (list[dict], optional)
                - supporting_data.sources (list[dict], optional, alternative key)
            cost_limited: If True, sets QAAnswer.cost_limited=True and trims sources.
            accumulated_cost: Total cost_usd for this Q&A session.

        Returns:
            Fully populated QAAnswer.
        """
        answer_text = agent_output.get("answer", "")
        if not isinstance(answer_text, str):
            answer_text = str(answer_text)

        confidence = float(agent_output.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        # Extract sources from agent output
        sources = self._extract_sources(agent_output)

        if cost_limited:
            # Trim sources when cost ceiling was hit
            sources = sources[:_MAX_SOURCES_WHEN_LIMITED]

        return QAAnswer(
            answer_text=answer_text,
            sources=sources,
            confidence=confidence,
            cost_usd=accumulated_cost,
            cost_limited=cost_limited,
        )

    def _extract_sources(self, agent_output: dict[str, Any]) -> list[QASource]:
        """Extract sources from agent output.

        Checks:
          1. Top-level 'sources' key (list of dicts)
          2. 'supporting_data.sources' nested key

        Args:
            agent_output: Raw agent output dict.

        Returns:
            List of QASource objects (empty list if none found).
        """
        raw_sources: list[Any] = []

        # Try top-level sources key first
        if "sources" in agent_output and isinstance(agent_output["sources"], list):
            raw_sources = agent_output["sources"]
        elif "supporting_data" in agent_output:
            sd = agent_output["supporting_data"]
            if isinstance(sd, dict) and "sources" in sd:
                raw_sources = sd["sources"] if isinstance(sd["sources"], list) else []

        sources: list[QASource] = []
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            try:
                sources.append(
                    QASource(
                        type=raw.get("type", "event"),
                        id=str(raw.get("id", "")),
                        description=str(raw.get("description", "")),
                    )
                )
            except Exception:
                # Skip malformed source entries
                continue

        return sources
