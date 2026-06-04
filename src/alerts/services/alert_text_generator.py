"""
AlertTextGenerator — generates ~80-word alert text via Sonnet 4.6 (step 8).

Loads system prompt from prompts/alerts/alert_text_generator.md.
Calls ILLMClient.complete with max_tokens=200 and 8-second timeout.
Parses structured JSON into AlertTextResult.
Sets low_sample_disclaimer=True when sample_size < 5.
Records a Langfuse span around the LLM call.
"""
from __future__ import annotations

import json
import logging
import time as time_module
from pathlib import Path
from uuid import UUID

from src.ai.interfaces.i_langfuse_tracer import ILangfuseTracer
from src.ai.interfaces.i_llm_client import ILLMClient
from src.alerts.exceptions import AlertDispatchError
from src.alerts.models import ActionSignal, AlertTextResult

logger = logging.getLogger(__name__)

_MODEL_TAG = "claude-sonnet-4-6"
_MAX_TOKENS = 200
_TIMEOUT_SECONDS = 8.0
_LOW_SAMPLE_THRESHOLD = 5

_PROMPT_PATH = Path("prompts/alerts/alert_text_generator.md")


class AlertTextGenerator:
    """Generates structured alert text using the configured LLM client.

    Args:
        llm_client: ILLMClient implementation (Sonnet 4.6).
        prompts_dir: Base directory for prompt files (default: project root).
    """

    def __init__(
        self,
        llm_client: ILLMClient,
        prompts_dir: Path | None = None,
    ) -> None:
        self._llm = llm_client
        self._prompt_path = (
            (prompts_dir or Path(".")) / "prompts/alerts/alert_text_generator.md"
        )
        self._system_prompt: str | None = None

    def _load_system_prompt(self) -> str:
        """Load and cache the system prompt from disk."""
        if self._system_prompt is None:
            self._system_prompt = self._prompt_path.read_text(encoding="utf-8")
        return self._system_prompt

    async def generate(
        self,
        event_title: str,
        intensity: int,
        analogies: list[dict],
        exposed_company_count: int,
        tenant_id: UUID,
        tracer: ILangfuseTracer,
    ) -> AlertTextResult:
        """Generate structured alert text for an event.

        Args:
            event_title: Human-readable event headline.
            intensity: Classified event intensity (1–5).
            analogies: Historical analogy dicts (each has event_title, similarity, etc.).
            exposed_company_count: Number of portfolio holdings exposed to the event.
            tenant_id: Owning tenant (for trace metadata).
            tracer: Langfuse tracer for span recording.

        Returns:
            AlertTextResult with alert_text, action_signal, confidence, sample_size,
            and low_sample_disclaimer.

        Raises:
            AlertDispatchError: On LLM timeout, malformed JSON, or invalid enum value.
        """
        system_prompt = self._load_system_prompt()
        user_message = self._build_user_message(
            event_title, intensity, analogies, exposed_company_count
        )

        span_id = tracer.start_span(
            trace_id=str(tenant_id),
            name="generate_alert_text",
            input={
                "event_title": event_title,
                "intensity": intensity,
                "analogy_count": len(analogies),
                "exposed_company_count": exposed_company_count,
                "model": _MODEL_TAG,
            },
        )

        start_ms = int(time_module.monotonic() * 1000)
        try:
            content, input_tokens, output_tokens = await self._llm.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=_MAX_TOKENS,
                timeout_seconds=_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            latency_ms = int(time_module.monotonic() * 1000) - start_ms
            tracer.end_span(
                span_id=span_id,
                output={"error": str(exc)},
                cost_usd=0.0,
                latency_ms=latency_ms,
            )
            raise AlertDispatchError(
                f"LLM call failed during alert text generation: {type(exc).__name__}"
            ) from exc

        latency_ms = int(time_module.monotonic() * 1000) - start_ms

        result = self._parse_response(content)

        tracer.end_span(
            span_id=span_id,
            output={
                "action_signal": result.action_signal.value,
                "confidence": result.confidence,
                "sample_size": result.sample_size,
                "model": _MODEL_TAG,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            cost_usd=0.0,  # Cost tracking delegated to pipeline cost_accumulator
            latency_ms=latency_ms,
        )

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_user_message(
        event_title: str,
        intensity: int,
        analogies: list[dict],
        exposed_company_count: int,
    ) -> str:
        """Construct the user-role message for the LLM."""
        analogy_lines = []
        for a in analogies[:5]:  # Cap at 5 analogies in context window
            analogy_lines.append(
                f"- {a.get('event_title', 'Unknown')} "
                f"(similarity: {a.get('similarity_score', 0):.2f}, "
                f"sample_size: {a.get('sample_size', 0)})"
            )
        analogy_text = "\n".join(analogy_lines) if analogy_lines else "No historical analogies available."

        return (
            f"Event: {event_title}\n"
            f"Intensity: {intensity}/5\n"
            f"Holdings exposed: {exposed_company_count}\n"
            f"Historical analogies:\n{analogy_text}\n\n"
            f"Generate the alert JSON now."
        )

    @staticmethod
    def _parse_response(content: str) -> AlertTextResult:
        """Parse LLM JSON response into AlertTextResult.

        Raises:
            AlertDispatchError: On malformed JSON or invalid ActionSignal value.
        """
        # Strip markdown fences if the model includes them despite instructions
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            stripped = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AlertDispatchError(
                f"Alert text generator returned non-JSON response: {exc}"
            ) from exc

        # Validate required fields
        for field in ("alert_text", "action_signal", "confidence", "sample_size"):
            if field not in data:
                raise AlertDispatchError(
                    f"Alert text generator response missing field: {field!r}"
                )

        try:
            action_signal = ActionSignal(data["action_signal"])
        except ValueError:
            raise AlertDispatchError(
                f"Invalid action_signal value: {data['action_signal']!r}. "
                f"Must be one of {[e.value for e in ActionSignal]}"
            )

        sample_size = int(data["sample_size"])
        return AlertTextResult(
            alert_text=str(data["alert_text"]),
            action_signal=action_signal,
            confidence=float(data["confidence"]),
            sample_size=sample_size,
            low_sample_disclaimer=sample_size < _LOW_SAMPLE_THRESHOLD,
        )
