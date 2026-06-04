"""
Unit tests for AnthropicLLMClient.

Mocks anthropic.AsyncAnthropic so no real API key is required.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.exceptions import PipelineError, StepTimeoutError


class FakeAnthropicMessage:
    """Minimal stand-in for the Anthropic messages response object."""

    def __init__(self, content: str, input_tokens: int, output_tokens: int) -> None:
        self.content = [MagicMock(text=content)]
        self.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)


@pytest.mark.asyncio
class TestAnthropicLLMClient:
    """Tests for AnthropicLLMClient.complete()."""

    async def test_successful_completion_returns_content_and_token_counts(self) -> None:
        from src.ai.anthropic_client import AnthropicLLMClient

        fake_response = FakeAnthropicMessage(
            content='{"key": "value"}', input_tokens=50, output_tokens=20
        )
        mock_messages = AsyncMock(return_value=fake_response)

        with patch("src.ai.anthropic_client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create = mock_messages
            mock_anthropic.AsyncAnthropic.return_value = mock_client_instance

            client = AnthropicLLMClient(
                api_key="sk-test-key", default_model="claude-haiku-4-5"
            )
            content, input_tokens, output_tokens = await client.complete(
                system_prompt="You are a classifier.",
                user_message="Classify this event.",
                max_tokens=200,
                timeout_seconds=5.0,
            )

        assert content == '{"key": "value"}'
        assert input_tokens == 50
        assert output_tokens == 20

    async def test_timeout_raises_step_timeout_error(self) -> None:
        from src.ai.anthropic_client import AnthropicLLMClient

        async def slow_create(*args, **kwargs):
            await asyncio.sleep(999)

        with patch("src.ai.anthropic_client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create = slow_create
            mock_anthropic.AsyncAnthropic.return_value = mock_client_instance

            client = AnthropicLLMClient(
                api_key="sk-test-key", default_model="claude-haiku-4-5"
            )
            with pytest.raises(StepTimeoutError):
                await client.complete(
                    system_prompt="sys",
                    user_message="user",
                    max_tokens=100,
                    timeout_seconds=0.01,
                )

    async def test_api_error_wrapped_in_pipeline_error_without_key(self) -> None:
        from src.ai.anthropic_client import AnthropicLLMClient

        with patch("src.ai.anthropic_client.anthropic") as mock_anthropic:
            # Simulate an API error class
            mock_anthropic.APIError = Exception

            mock_client_instance = MagicMock()
            mock_client_instance.messages.create = AsyncMock(
                side_effect=Exception("Internal Server Error")
            )
            mock_anthropic.AsyncAnthropic.return_value = mock_client_instance

            client = AnthropicLLMClient(
                api_key="sk-super-secret", default_model="claude-haiku-4-5"
            )
            with pytest.raises(PipelineError) as exc_info:
                await client.complete("sys", "user", 100, 5.0)

            # API key must NOT appear in the exception message
            assert "sk-super-secret" not in str(exc_info.value)

    async def test_max_tokens_forwarded_to_api(self) -> None:
        from src.ai.anthropic_client import AnthropicLLMClient

        fake_response = FakeAnthropicMessage("result", 10, 5)
        mock_messages = AsyncMock(return_value=fake_response)

        with patch("src.ai.anthropic_client.anthropic") as mock_anthropic:
            mock_client_instance = MagicMock()
            mock_client_instance.messages.create = mock_messages
            mock_anthropic.AsyncAnthropic.return_value = mock_client_instance

            client = AnthropicLLMClient(
                api_key="sk-test", default_model="claude-haiku-4-5"
            )
            await client.complete("sys", "user", max_tokens=512, timeout_seconds=5.0)

        call_kwargs = mock_messages.call_args.kwargs
        assert call_kwargs.get("max_tokens") == 512
