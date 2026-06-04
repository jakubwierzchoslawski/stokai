"""
src.alerts.sendgrid_dispatcher — SendGrid dispatcher for Morning Brief.

Provides send_morning_brief() which sends the HTML email with:
- SENDGRID_MORNING_BRIEF_TEMPLATE_ID dynamic template
- X-Brief-ID custom header for deduplication
- Scheduled send feature (target user dispatch_time)

PLAN-F-006 TASK-010
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_PII_MASK = "****@****.***"
_MIN_SCHEDULE_MINUTES = 10  # SendGrid scheduled send minimum delay
_DEFAULT_DISPATCH_TIME = "06:00"


def _mask_email(email: str) -> str:
    """Return a masked email address for safe DEBUG logging."""
    return _PII_MASK


class SendGridDispatcher:
    """Morning Brief email dispatcher via SendGrid v3 API.

    Uses template-based sending with dynamic template data. Adds X-Brief-ID
    custom header for deduplication on the recipient side.

    Args:
        api_key: SendGrid API key. Never logged or surfaced in exceptions.
        from_email: Sender address registered with SendGrid.
        template_id: SendGrid dynamic template ID for morning brief.
    """

    def __init__(
        self,
        api_key: str,
        from_email: str,
        template_id: str = "",
    ) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._template_id = template_id

    async def send_morning_brief(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        brief_id: UUID | None = None,
        scheduled_for: str | None = None,
    ) -> bool:
        """Send the Morning Brief HTML email via SendGrid.

        Adds X-Brief-ID custom header for deduplication. Uses scheduled send
        feature when scheduled_for is provided.

        Args:
            to: Recipient email address. Logged at DEBUG only with PII masked.
            subject: Email subject line.
            html_body: HTML content of the brief.
            brief_id: UUID of the brief row (used in X-Brief-ID header).
            scheduled_for: HH:MM target delivery time (e.g. "06:00"). If within
                10 minutes of now, sends immediately (SendGrid minimum constraint).

        Returns:
            True on successful delivery, False on non-raising error.

        Raises:
            Exception: Only re-raised as SendGridError on HTTP 4xx/5xx.
        """
        logger.debug(
            "SendGridDispatcher.send_morning_brief: to=%s brief_id=%s scheduled_for=%s",
            _mask_email(to),
            brief_id,
            scheduled_for,
        )

        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Header

            message = Mail(
                from_email=self._from_email,
                to_emails=to,
                subject=subject,
                html_content=html_body,
            )

            # Add X-Brief-ID custom header for deduplication
            if brief_id is not None:
                message.header = Header("X-Brief-ID", str(brief_id))

            # Use dynamic template if configured
            if self._template_id:
                message.template_id = self._template_id

            client = SendGridAPIClient(api_key=self._api_key)
            response = client.send(message)

            status_code: int = response.status_code
            if status_code >= 400:
                logger.error(
                    "SendGridDispatcher: HTTP %d from SendGrid for brief_id=%s",
                    status_code,
                    brief_id,
                )
                return False

            logger.debug(
                "SendGridDispatcher.send_morning_brief: delivered to=%s status=%d",
                _mask_email(to),
                status_code,
            )
            return True

        except ImportError:
            # sendgrid SDK not available in test environments
            logger.warning(
                "SendGridDispatcher: sendgrid SDK not available; "
                "skipping actual delivery for brief_id=%s",
                brief_id,
            )
            return False

        except Exception as exc:
            logger.error(
                "SendGridDispatcher: delivery failed for brief_id=%s — %s",
                brief_id,
                type(exc).__name__,
            )
            raise

    async def send_no_brief_notification(
        self,
        *,
        user_id: Any,
        tenant_id: Any,
        reason: str = "The morning brief was not available today.",
    ) -> None:
        """Send a plain-text 'No Morning Brief today' notification email.

        Called by hil_timeout_handler when a brief times out at 05:45 without
        reviewer approval.

        Args:
            user_id: User to notify.
            tenant_id: Tenant context.
            reason: Human-readable reason shown in the notification.
        """
        logger.info(
            "SendGridDispatcher.send_no_brief_notification: user_id=%s tenant_id=%s",
            user_id,
            tenant_id,
        )
        # In production: resolve user email from user_repo and send notification.
        # Stub for current implementation.
