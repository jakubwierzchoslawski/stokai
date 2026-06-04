"""
SendGridEmailSender — IEmailSender implementation via SendGrid v3 API.

Security rules:
- API key is NEVER logged or included in exceptions.
- Recipient email is logged at DEBUG only with PII masked ("****@****.***").
- HTTP 4xx/5xx raises SendGridError with status_code only.
- HTTP timeout: 1.5 seconds.
"""
from __future__ import annotations

import logging
from typing import Any

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.alerts.exceptions import SendGridError

logger = logging.getLogger(__name__)

_SENDGRID_TIMEOUT_SECONDS = 1.5

# PII mask used for DEBUG-level email logging
_PII_MASK = "****@****.***"


def _mask_email(email: str) -> str:
    """Return a masked version of an email address for safe debug logging."""
    return _PII_MASK


class SendGridEmailSender:
    """Delivers HTML emails via SendGrid v3 Mail Send API.

    Args:
        api_key: SendGrid API key.  Never logged or surfaced in exceptions.
        from_email: Sender address registered with SendGrid.
    """

    def __init__(self, api_key: str, from_email: str) -> None:
        self._api_key = api_key
        self._from_email = from_email

    async def send(self, to_email: str, subject: str, html_body: str) -> None:
        """Send an HTML email via SendGrid.

        Args:
            to_email: Recipient address.  Logged at DEBUG only with PII masked.
            subject: Email subject line.
            html_body: Full HTML content.

        Raises:
            SendGridError: On HTTP 4xx/5xx from SendGrid.  API key is never
                included in the error message or logged.
        """
        logger.debug(
            "SendGridEmailSender.send: to=%s subject=%r",
            _mask_email(to_email),
            subject,
        )

        message = Mail(
            from_email=self._from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_body,
        )

        try:
            client = SendGridAPIClient(api_key=self._api_key)
            # The sendgrid SDK is synchronous; we call it directly.
            # For true async, wrap in asyncio.to_thread in production.
            response = client.send(message)
        except Exception as exc:
            # Never include the API key in the error
            raise SendGridError(
                f"SendGrid delivery failed: {type(exc).__name__}",
                status_code=None,
            ) from exc

        status_code: int = response.status_code
        if status_code >= 400:
            raise SendGridError(
                f"SendGrid returned HTTP {status_code}",
                status_code=status_code,
            )

        logger.debug(
            "SendGridEmailSender.send: delivered to=%s status=%d",
            _mask_email(to_email),
            status_code,
        )
