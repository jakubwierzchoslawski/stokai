"""
AlertDispatcher — IAlertDispatcher implementation.

Delivers alerts via SendGrid email API. Silent events are logged at INFO level.
SendGrid API key comes from the SENDGRID_API_KEY environment variable.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import sendgrid
from sendgrid.helpers.mail import Mail

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.events.exceptions import PipelineError

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """Dispatches alerts via SendGrid and logs silent events.

    Args:
        sendgrid_api_key: SendGrid API key (from SENDGRID_API_KEY env var).
        from_email: Sender email address.
        user_email_resolver: Callable that maps user_id -> email address string.
    """

    def __init__(
        self,
        sendgrid_api_key: str,
        from_email: str,
        user_email_resolver: Callable[[UUID], str],
    ) -> None:
        self._api_key = sendgrid_api_key
        self._from_email = from_email
        self._resolve_email = user_email_resolver

    # ── IAlertDispatcher ──────────────────────────────────────────────────────

    async def dispatch(
        self,
        rule_match: RuleMatch,
        alert_text: str,
        event_id: UUID,
    ) -> None:
        """Send an alert email via SendGrid.

        Args:
            rule_match: The matched rule with user and channel info.
            alert_text: ~80-word alert text to include in the email.
            event_id: Source event UUID (included in email for traceability).

        Raises:
            PipelineError: If the SendGrid API call fails.
        """
        to_email = self._resolve_email(rule_match.user_id)
        subject = f"StokAI Market Alert — Event {event_id}"

        message = Mail(
            from_email=self._from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=alert_text,
        )

        try:
            client = sendgrid.SendGridAPIClient(api_key=self._api_key)
            response = client.send(message)
            logger.info(
                "Alert dispatched via SendGrid: event=%s user=%s status=%s",
                event_id,
                rule_match.user_id,
                response.status_code,
            )
        except Exception as exc:
            raise PipelineError(
                f"SendGrid dispatch failed: {type(exc).__name__}"
            ) from None

    async def log_silent(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
    ) -> None:
        """Log that no alert was dispatched for this event."""
        logger.info(
            "Silent event: no alert dispatched for event_id=%s tenant_id=%s",
            event_id,
            tenant_id,
        )
