"""
alerts.api.alert_rules_router — Full CRUD for alert rules (PLAN-F-025).

Endpoints:
  GET    /api/v1/alert-rules               — list user's rules
  POST   /api/v1/alert-rules               — create a rule (201)
  PATCH  /api/v1/alert-rules/{rule_id}     — partial update (200)
  DELETE /api/v1/alert-rules/{rule_id}     — hard delete (204)

NotFoundError → 404.  ValidationError → 422.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import CurrentUser, get_current_user
from src.api.dependencies import get_db
from src.alerts.exceptions import NotFoundError, ValidationError
from src.alerts.repositories.alert_rule_crud_repository import AlertRuleCrudRepository
from src.alerts.schemas import (
    AlertRuleResponse,
    CreateAlertRuleRequest,
    UpdateAlertRuleRequest,
)
from src.alerts.services.alert_rule_manager import AlertRuleManager

alert_rules_router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


# ── Dependencies ──────────────────────────────────────────────────────────────


async def _get_alert_rule_manager(
    db: AsyncSession = Depends(get_db),
) -> AlertRuleManager:
    repo = AlertRuleCrudRepository(db)
    return AlertRuleManager(repo)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _success(data) -> dict:
    return {"data": data, "error": None}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@alert_rules_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List alert rules for the authenticated user",
)
async def list_alert_rules(
    current_user: CurrentUser = Depends(get_current_user),
    manager: AlertRuleManager = Depends(_get_alert_rule_manager),
) -> dict:
    rules = await manager.list_rules(
        user_id=current_user.user_id, tenant_id=current_user.tenant_id
    )
    return _success([r.model_dump() for r in rules])


@alert_rules_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new alert rule",
)
async def create_alert_rule(
    body: CreateAlertRuleRequest,
    current_user: CurrentUser = Depends(get_current_user),
    manager: AlertRuleManager = Depends(_get_alert_rule_manager),
) -> dict:
    try:
        rule_id = await manager.create_rule(
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            request=body,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    return _success({"rule_id": str(rule_id)})


@alert_rules_router.patch(
    "/{rule_id}",
    status_code=status.HTTP_200_OK,
    summary="Partial-update an alert rule",
)
async def update_alert_rule(
    rule_id: UUID,
    body: UpdateAlertRuleRequest,
    current_user: CurrentUser = Depends(get_current_user),
    manager: AlertRuleManager = Depends(_get_alert_rule_manager),
) -> dict:
    try:
        await manager.update_rule(
            rule_id=rule_id,
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            request=body,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": str(exc)},
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc
    return _success({"rule_id": str(rule_id)})


@alert_rules_router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert rule",
)
async def delete_alert_rule(
    rule_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    manager: AlertRuleManager = Depends(_get_alert_rule_manager),
) -> None:
    try:
        await manager.delete_rule(
            rule_id=rule_id,
            user_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": str(exc)},
        ) from exc
