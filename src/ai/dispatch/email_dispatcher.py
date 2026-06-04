"""
ai.dispatch.email_dispatcher — SendGrid email dispatch for Morning Brief.

Provides:
  - EmailDispatcher.send_morning_brief(to, subject, html_body, brief_id) -> bool

Returns True on HTTP 2xx, False on 4xx/5xx (logs error, does not raise).
Uses an injectable HTTP client for testability (inject a mock in unit tests).

PLAN-F-006 TASK-006.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

logger = logging.getLogger(__name__)

# Sentinel indicating no SENDGRID_API_KEY is configured
_SENDGRID_DISABLED = "disabled"


@runtime_checkable
class IHttpClient(Protocol):
    """Minimal protocol for an async HTTP client used by EmailDispatcher.

    The default implementation uses httpx.AsyncClient.
    Tests inject a mock.
    """

    async def post(self, url: str, *, json: dict, headers: dict) -> Any:
        """POST json body to url with headers; return a response-like object."""
        ...


class DefaultHttpClient:
    """Production HTTP client wrapping httpx.AsyncClient.

    Sends a single POST request and returns the response.  Does NOT pool
    connections — each email call opens a short-lived client.  Suitable for
    low-frequency scheduled tasks (Morning Brief runs once daily).
    """

    async def post(self, url: str, *, json: dict, headers: dict) -> Any:
        """POST via httpx and return the response."""
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx is required for EmailDispatcher; add it to pyproject.toml"
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(url, json=json, headers=headers)


class EmailDispatcher:
    """Sends the Morning Brief via the SendGrid v3 Mail Send API.

    Constructor injection:
      - api_key: SendGrid API key (from settings.SENDGRID_API_KEY).
      - from_email: Verified sender address (settings.SENDGRID_FROM_EMAIL).
      - http_client: Optional IHttpClient override (defaults to DefaultHttpClient).

    When api_key is blank or 'disabled', send_morning_brief() immediately
    returns False and logs a warning — this prevents failures in dev/test
    environments without a real SendGrid account.
    """

    _SENDGRID_MAIL_URL = "https://api.sendgrid.com/v3/mail/send"

    def __init__(
        self,
        api_key: str,
        from_email: str,
        http_client: IHttpClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._http_client: IHttpClient = http_client or DefaultHttpClient()

    async def send_morning_brief(
        self,
        to: str,
        subject: str,
        html_body: str,
        brief_id: UUID,
    ) -> bool:
        """Send the morning brief email via SendGrid.

        Builds a SendGrid v3 API payload and POSTs it.  Returns True on HTTP
        2xx (202 Accepted is the expected SendGrid success code), False on any
        4xx/5xx error.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html_body: HTML content of the brief.
            brief_id: UUID of the Brief DB row (attached as a custom header
                      X-Brief-Id for traceability).

        Returns:
            True — email accepted by SendGrid.
            False — API key not configured, or HTTP 4xx/5xx returned.
        """
        if not self._api_key or self._api_key == _SENDGRID_DISABLED:
            logger.warning(
                "EmailDispatcher.send_morning_brief: SENDGRID_API_KEY not configured "
                "— email suppressed for brief_id=%s to=%s",
                brief_id,
                to,
            )
            return False

        payload = {
            "personalizations": [
                {
                    "to": [{"email": to}],
                    "subject": subject,
                }
            ],
            "from": {"email": self._from_email},
            "content": [{"type": "text/html", "value": html_body}],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Brief-Id": str(brief_id),
        }

        try:
            response = await self._http_client.post(
                self._SENDGRID_MAIL_URL,
                json=payload,
                headers=headers,
            )

            status_code = getattr(response, "status_code", None)

            if status_code is not None and 200 <= status_code < 300:
                logger.info(
                    "EmailDispatcher.send_morning_brief: accepted "
                    "status=%s brief_id=%s to=%s",
                    status_code,
                    brief_id,
                    to,
                )
                return True

            logger.error(
                "EmailDispatcher.send_morning_brief: failed "
                "status=%s brief_id=%s to=%s",
                status_code,
                brief_id,
                to,
            )
            return False

        except Exception as exc:
            logger.exception(
                "EmailDispatcher.send_morning_brief: unexpected error "
                "brief_id=%s to=%s: %s",
                brief_id,
                to,
                exc,
            )
            return False
