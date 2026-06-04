"""
Unit tests for EmailDispatcher.

TDD: written before implementation — PLAN-F-006 TASK-006.

Tests:
  - send_morning_brief returns True on HTTP 2xx (202)
  - send_morning_brief returns False on HTTP 4xx/5xx
  - send_morning_brief returns False when api_key is blank
  - Correct SendGrid payload structure (personalizations, from, content)
  - Mock HTTP client injected — no real network calls
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ai.dispatch.email_dispatcher import EmailDispatcher


def _make_dispatcher(
    api_key: str = "SG.test_key",
    from_email: str = "briefs@stokai.io",
    http_client: object | None = None,
) -> EmailDispatcher:
    return EmailDispatcher(
        api_key=api_key,
        from_email=from_email,
        http_client=http_client,
    )


def _make_mock_client(status_code: int) -> AsyncMock:
    """Return an async mock HTTP client that returns the given status code."""
    response = MagicMock()
    response.status_code = status_code

    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    return client


class TestSendMorningBrief:
    @pytest.mark.asyncio
    async def test_returns_true_on_202(self):
        """send_morning_brief must return True when SendGrid responds 202."""
        mock_client = _make_mock_client(202)
        dispatcher = _make_dispatcher(http_client=mock_client)

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_200(self):
        """send_morning_brief must return True for any 2xx status code."""
        mock_client = _make_mock_client(200)
        dispatcher = _make_dispatcher(http_client=mock_client)

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_400(self):
        """send_morning_brief must return False on HTTP 4xx."""
        mock_client = _make_mock_client(400)
        dispatcher = _make_dispatcher(http_client=mock_client)

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_500(self):
        """send_morning_brief must return False on HTTP 5xx."""
        mock_client = _make_mock_client(500)
        dispatcher = _make_dispatcher(http_client=mock_client)

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_api_key_blank(self):
        """send_morning_brief must return False when api_key is blank (no SendGrid)."""
        dispatcher = _make_dispatcher(api_key="")

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_api_key_disabled(self):
        """send_morning_brief must return False when api_key='disabled'."""
        dispatcher = _make_dispatcher(api_key="disabled")

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """send_morning_brief must return False when HTTP client raises."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("Network error"))
        dispatcher = _make_dispatcher(http_client=mock_client)

        result = await dispatcher.send_morning_brief(
            to="trader@example.com",
            subject="Morning Brief",
            html_body="<p>Top events</p>",
            brief_id=uuid.uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_posts_to_sendgrid_url(self):
        """send_morning_brief must POST to the SendGrid v3 mail/send endpoint."""
        mock_client = _make_mock_client(202)
        dispatcher = _make_dispatcher(http_client=mock_client)

        await dispatcher.send_morning_brief(
            to="user@example.com",
            subject="Brief",
            html_body="<p>Content</p>",
            brief_id=uuid.uuid4(),
        )

        mock_client.post.assert_called_once()
        call_url = mock_client.post.call_args.args[0]
        assert "sendgrid.com" in call_url
        assert "mail/send" in call_url

    @pytest.mark.asyncio
    async def test_payload_contains_correct_recipient(self):
        """send_morning_brief must include the 'to' address in the payload."""
        mock_client = _make_mock_client(202)
        dispatcher = _make_dispatcher(http_client=mock_client)
        to_email = "vip@example.com"

        await dispatcher.send_morning_brief(
            to=to_email,
            subject="Morning Brief",
            html_body="<p>Content</p>",
            brief_id=uuid.uuid4(),
        )

        call_json = mock_client.post.call_args.kwargs["json"]
        personalizations = call_json["personalizations"]
        recipients = personalizations[0]["to"]
        assert any(r["email"] == to_email for r in recipients)

    @pytest.mark.asyncio
    async def test_payload_contains_html_content(self):
        """send_morning_brief must include the html_body in the content field."""
        mock_client = _make_mock_client(202)
        dispatcher = _make_dispatcher(http_client=mock_client)
        html = "<h1>Morning Brief</h1><p>Key events...</p>"

        await dispatcher.send_morning_brief(
            to="user@example.com",
            subject="Morning Brief",
            html_body=html,
            brief_id=uuid.uuid4(),
        )

        call_json = mock_client.post.call_args.kwargs["json"]
        content_items = call_json["content"]
        assert any(
            item["type"] == "text/html" and item["value"] == html
            for item in content_items
        )

    @pytest.mark.asyncio
    async def test_authorization_header_set(self):
        """send_morning_brief must set Authorization: Bearer <api_key> header."""
        api_key = "SG.supersecret"
        mock_client = _make_mock_client(202)
        dispatcher = _make_dispatcher(api_key=api_key, http_client=mock_client)

        await dispatcher.send_morning_brief(
            to="user@example.com",
            subject="Brief",
            html_body="<p>x</p>",
            brief_id=uuid.uuid4(),
        )

        call_headers = mock_client.post.call_args.kwargs["headers"]
        assert call_headers["Authorization"] == f"Bearer {api_key}"
