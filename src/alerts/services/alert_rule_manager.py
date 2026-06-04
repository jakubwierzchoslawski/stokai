"""
AlertRuleManager — business logic for alert rule CRUD (PLAN-F-025).

Validates domain constraints before delegating to AlertRuleCrudRepository.
Never leaks whether a resource exists when the caller is unauthorized.
"""
from __future__ import annotations

import logging
from uuid import UUID

from src.alerts.exceptions import NotFoundError, ValidationError
from src.alerts.repositories.alert_rule_crud_repository import AlertRuleCrudRepository
from src.alerts.schemas import (
    AlertRuleResponse,
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
)

logger = logging.getLogger(__name__)

_INTENSITY_MIN = 1
_INTENSITY_MAX = 5


class AlertRuleManager:
    """Domain service that validates and delegates alert rule operations.

    Args:
        repo: AlertRuleCrudRepository (or compatible mock in tests).
    """

    def __init__(self, repo: AlertRuleCrudRepository) -> None:
        self._repo = repo

    # ── Validation ─────────────────────────────────────────────────────────

    @staticmethod
    def _validate_create(request: CreateAlertRuleRequest) -> None:
        if not (_INTENSITY_MIN <= request.intensity_min <= _INTENSITY_MAX):
            raise ValidationError(
                f"intensity_min must be between {_INTENSITY_MIN} and {_INTENSITY_MAX}; "
                f"got {request.intensity_min}"
            )
        if request.per_ticker_interval_hours <= 0:
            raise ValidationError(
                f"per_ticker_interval_hours must be > 0; "
                f"got {request.per_ticker_interval_hours}"
            )

    # ── Public API ─────────────────────────────────────────────────────────

    async def create_rule(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        request: CreateAlertRuleRequest,
    ) -> UUID:
        """Validate and insert a new alert rule.

        Raises:
            ValidationError: if intensity_min not in [1,5] or per_ticker_interval_hours≤0.
        """
        self._validate_create(request)
        rule_id = await self._repo.insert(
            user_id=user_id,
            tenant_id=tenant_id,
            name=request.name,
            event_category_filter=request.event_category_filter,
            intensity_min=request.intensity_min,
            ticker_list=request.ticker_list,
            quiet_hours_start=request.quiet_hours_start,
            quiet_hours_end=request.quiet_hours_end,
            per_ticker_interval_hours=request.per_ticker_interval_hours,
            channels=request.channels,
        )
        logger.info("AlertRuleManager.create_rule: rule_id=%s user=%s", rule_id, user_id)
        return rule_id

    async def list_rules(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> list[AlertRuleResponse]:
        """Return all alert rules for the authenticated user."""
        return await self._repo.get_by_user(user_id=user_id, tenant_id=tenant_id)

    async def update_rule(
        self,
        *,
        rule_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
        request: UpdateAlertRuleRequest,
    ) -> None:
        """Partial-update an alert rule.

        Raises:
            NotFoundError: if the rule doesn't exist or belongs to a different user.
            ValidationError: if intensity_min or per_ticker_interval_hours are out of range.
        """
        existing = await self._repo.get_by_id(
            rule_id=rule_id, user_id=user_id, tenant_id=tenant_id
        )
        if existing is None:
            raise NotFoundError("AlertRule", rule_id)

        # Validate changed fields
        if request.intensity_min is not None:
            if not (_INTENSITY_MIN <= request.intensity_min <= _INTENSITY_MAX):
                raise ValidationError(
                    f"intensity_min must be between {_INTENSITY_MIN} and {_INTENSITY_MAX}"
                )
        if request.per_ticker_interval_hours is not None:
            if request.per_ticker_interval_hours <= 0:
                raise ValidationError("per_ticker_interval_hours must be > 0")

        await self._repo.update(
            rule_id=rule_id,
            user_id=user_id,
            tenant_id=tenant_id,
            name=request.name,
            enabled=request.enabled,
            event_category_filter=request.event_category_filter,
            intensity_min=request.intensity_min,
            ticker_list=request.ticker_list,
            quiet_hours_start=request.quiet_hours_start,
            quiet_hours_end=request.quiet_hours_end,
            per_ticker_interval_hours=request.per_ticker_interval_hours,
            channels=request.channels,
        )
        logger.info("AlertRuleManager.update_rule: rule_id=%s", rule_id)

    async def delete_rule(
        self, *, rule_id: UUID, user_id: UUID, tenant_id: UUID
    ) -> None:
        """Hard-delete an alert rule.

        Raises:
            NotFoundError: if the rule doesn't exist or belongs to a different user.
        """
        existing = await self._repo.get_by_id(
            rule_id=rule_id, user_id=user_id, tenant_id=tenant_id
        )
        if existing is None:
            raise NotFoundError("AlertRule", rule_id)

        await self._repo.delete(rule_id=rule_id, user_id=user_id, tenant_id=tenant_id)
        logger.info("AlertRuleManager.delete_rule: rule_id=%s", rule_id)
