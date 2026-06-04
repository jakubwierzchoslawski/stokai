"""
Custom exceptions for the alerts module.

Each exception carries user_id and event_id for log correlation so that
structured loggers can filter and trace alert failures without surfacing
PII or secrets.
"""
from __future__ import annotations

from uuid import UUID


class AlertDispatchError(Exception):
    """Raised when an alert cannot be dispatched due to a non-recoverable error.

    This covers LLM parse failures, timeout on alert-text generation, and
    upstream delivery errors that the caller must handle explicitly.

    Args:
        message: Human-readable description of the failure.
        user_id: UUID of the affected user, or None if unavailable.
        event_id: UUID of the source event, or None if unavailable.
    """

    def __init__(
        self,
        message: str,
        user_id: UUID | None = None,
        event_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.user_id = user_id
        self.event_id = event_id


class BudgetHardStopError(Exception):
    """Raised when a user's daily hard-stop budget percentage is reached.

    Callers must catch this and insert a SUPPRESSED_BUDGET silent-log row.
    This exception is never swallowed silently — the pipeline must log it.

    Args:
        user_id: UUID of the affected user, or None if unavailable.
        event_id: UUID of the source event, or None if unavailable.
        spent_today_usd: Amount spent so far today in USD.
        daily_budget_usd: Configured daily budget cap in USD.
    """

    def __init__(
        self,
        message: str,
        user_id: UUID | None = None,
        event_id: UUID | None = None,
        spent_today_usd: float = 0.0,
        daily_budget_usd: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.user_id = user_id
        self.event_id = event_id
        self.spent_today_usd = spent_today_usd
        self.daily_budget_usd = daily_budget_usd


class NotFoundError(Exception):
    """Raised when a requested alert-domain resource does not exist or belongs
    to another user/tenant.  Never reveals whether the resource exists."""

    def __init__(self, resource: str = "Resource", resource_id: object = None) -> None:
        msg = f"{resource} not found"
        if resource_id is not None:
            msg = f"{resource} {resource_id!r} not found"
        super().__init__(msg)


class ValidationError(Exception):
    """Raised when alert-domain input fails validation rules."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message)


class SendGridError(Exception):
    """Raised when the SendGrid API returns a non-2xx response.

    The API key is NEVER included in this exception or its message.
    Only the HTTP status code is surfaced for safe logging.

    Args:
        message: Human-readable description of the failure.
        status_code: HTTP status code returned by SendGrid.
        user_id: UUID of the affected user, or None if unavailable.
        event_id: UUID of the source event, or None if unavailable.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        user_id: UUID | None = None,
        event_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.user_id = user_id
        self.event_id = event_id
