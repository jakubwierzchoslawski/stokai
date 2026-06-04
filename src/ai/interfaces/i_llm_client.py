"""
ILLMClient — protocol for Anthropic (and future) language model clients.
"""
from __future__ import annotations

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class ILLMClient(Protocol):
    """Minimal interface for synchronous/async text completion.

    Implementations wrap a specific model provider (Anthropic, etc.) and
    expose a single *complete* method that is awaited by pipeline steps.
    """

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> tuple[str, int, int]:
        """Run a text completion.

        Args:
            system_prompt: The system-role prompt.
            user_message: The user-role message.
            max_tokens: Maximum completion tokens to generate.
            timeout_seconds: Hard wall-clock timeout for the API call.

        Returns:
            A 3-tuple of (content_str, input_tokens, output_tokens).

        Raises:
            StepTimeoutError: When the request exceeds *timeout_seconds*.
            PipelineError: On provider API errors.
        """
        ...
