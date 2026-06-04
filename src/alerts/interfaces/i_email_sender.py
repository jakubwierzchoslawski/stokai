"""
IEmailSender — protocol for transactional email delivery.

Abstraction layer over SendGrid (or any future provider).  Callers never
interact with the transport directly; they always inject IEmailSender.
"""
from __future__ import annotations

from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class IEmailSender(Protocol):
    """Interface for sending a single transactional email."""

    async def send(self, to_email: str, subject: str, html_body: str) -> None:
        """Send an HTML email.

        Args:
            to_email: Recipient address.  Never logged at ERROR level.
            subject: Email subject line.
            html_body: Full HTML content of the email body.

        Raises:
            SendGridError: On HTTP 4xx / 5xx from the provider.  The API key
                is never included in the error.
        """
        ...
