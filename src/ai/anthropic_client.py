"""
AnthropicLLMClient — ILLMClient implementation backed by the Anthropic API.

Security note: the API key is stored in memory only; it is never logged,
included in exception messages, or serialised.
"""
from __future__ import annotations

import asyncio
import logging

import anthropic

from src.events.exceptions import PipelineError, StepTimeoutError

logger = logging.getLogger(__name__)


class AnthropicLLMClient:
    """Async LLM client backed by Anthropic's Messages API.

    Args:
        api_key: Anthropic API key — never logged or included in exceptions.
        default_model: Model identifier used when complete() is called.
    """

    def __init__(self, api_key: str, default_model: str) -> None:
        # Store key only on the underlying SDK client, not as a plain attribute
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    # ── ILLMClient ────────────────────────────────────────────────────────────

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> tuple[str, int, int]:
        """Run a text completion with a hard wall-clock timeout.

        Returns:
            (content_str, input_tokens, output_tokens)

        Raises:
            StepTimeoutError: When the request exceeds *timeout_seconds*.
            PipelineError: On any Anthropic API error (sanitised message).
        """
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._default_model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise StepTimeoutError(
                f"LLM completion timed out after {timeout_seconds}s"
            ) from exc
        except anthropic.APIError as exc:
            # Sanitise: re-raise without including raw exception details
            # that might carry request headers containing the API key.
            raise PipelineError(
                f"Anthropic API error: {type(exc).__name__}"
            ) from None
        except Exception as exc:
            raise PipelineError(
                f"Unexpected error during LLM completion: {type(exc).__name__}"
            ) from None

        content = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return content, input_tokens, output_tokens
