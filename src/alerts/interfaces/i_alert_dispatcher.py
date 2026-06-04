"""
IAlertDispatcher — protocol for dispatching alerts or logging silent events.

Extended from PLAN-F-001:
- dispatch() now returns AlertDispatchResult (was None)
- log_silent() now accepts explicit suppression_status
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel
from typing_extensions import Protocol, runtime_checkable

from src.alerts.interfaces.i_alert_rule_evaluator import RuleMatch
from src.alerts.models import AlertStatus, AlertTextResult


class AlertDispatchResult(BaseModel):
    """Return value from IAlertDispatcher.dispatch describing what happened."""

    alert_id: UUID
    status: AlertStatus
    channel: str  # "email" | "silent"


@runtime_checkable
class IAlertDispatcher(Protocol):
    """Interface for alert delivery and silent-log recording."""

    async def dispatch(
        self,
        rule_match: RuleMatch,
        alert_text_result: AlertTextResult,
        event_id: UUID,
    ) -> AlertDispatchResult:
        """Run the full anti-fatigue + budget chain then send or log-silent.

        Args:
            rule_match: The matched rule containing user and channel info.
            alert_text_result: Structured LLM output (text, signal, confidence).
            event_id: UUID of the source event (for tracing).

        Returns:
            AlertDispatchResult describing disposition (DISPATCHED or suppressed).

        Raises:
            AlertDispatchError: If the downstream delivery fails in a non-recoverable way.
        """
        ...

    async def log_silent(
        self,
        event_id: UUID,
        tenant_id: UUID | None,
        suppression_status: AlertStatus,
    ) -> None:
        """Record that no alert was dispatched for *event_id* at the pipeline level.

        Used when the entire event has no matching rules (no rule_match). When a
        specific rule_match is suppressed the dispatcher handles the silent-log
        internally.

        Args:
            event_id: The event that was silently processed.
            tenant_id: Owning tenant, or None for global events.
            suppression_status: Reason the alert was not dispatched.
        """
        ...
