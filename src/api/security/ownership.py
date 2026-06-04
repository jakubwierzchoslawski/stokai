"""
api.security.ownership — IDOR prevention utilities.

Provides verify_resource_ownership and resource_owner_dependency for
FastAPI endpoints that must confirm a resource belongs to the requesting tenant
before returning data.

Security design:
  - Cross-tenant access returns HTTP 404 (not 403) to avoid disclosing
    whether the resource exists at all (prevents enumeration).
  - verify_resource_ownership raises ResourceNotOwnedError which callers
    convert to HTTP 404.
"""
from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, status


class ResourceNotOwnedError(Exception):
    """Raised when the requesting tenant does not own the resource.

    Callers should convert this to HTTP 404 — not 403 — to prevent disclosing
    resource existence to unauthorised tenants (IDOR prevention).
    """


def verify_resource_ownership(
    resource: Any,
    requesting_tenant_id: uuid.UUID,
    resource_id: uuid.UUID | str,
) -> None:
    """Assert that the requesting tenant owns the given resource.

    Args:
        resource: An ORM model instance that exposes a ``tenant_id`` attribute.
        requesting_tenant_id: The tenant UUID from the authenticated user's JWT.
        resource_id: The ID used to look up the resource (used in error messages only).

    Raises:
        ResourceNotOwnedError: If ``resource.tenant_id`` is None (globally-scoped
            resources should not pass through this check), or if it does not match
            ``requesting_tenant_id``.

    Returns:
        None — silently passes when ownership is confirmed.
    """
    resource_tenant_id = getattr(resource, "tenant_id", None)

    if resource_tenant_id is None:
        raise ResourceNotOwnedError(
            f"Resource {resource_id!r} has no tenant_id — ownership cannot be verified."
        )

    # Normalise both to UUID for comparison (resource.tenant_id may be a string
    # if the ORM model uses a String column on certain DB drivers).
    try:
        resource_tid = (
            resource_tenant_id
            if isinstance(resource_tenant_id, uuid.UUID)
            else uuid.UUID(str(resource_tenant_id))
        )
    except (ValueError, AttributeError):
        raise ResourceNotOwnedError(
            f"Resource {resource_id!r} tenant_id is not a valid UUID."
        )

    if resource_tid != requesting_tenant_id:
        raise ResourceNotOwnedError(
            f"Resource {resource_id!r} belongs to a different tenant."
        )


def resource_owner_dependency(
    get_resource_fn: Callable[[uuid.UUID, uuid.UUID], Awaitable[Any]],
) -> Callable:
    """Factory that returns a FastAPI dependency ensuring resource ownership.

    The returned async callable:
      1. Calls ``get_resource_fn(resource_id, tenant_id)`` where ``tenant_id``
         comes from ``get_current_user``.
      2. If the resource is not found (None returned), raises HTTP 404.
      3. Calls ``verify_resource_ownership``; on failure raises HTTP 404.
      4. Returns the resource to the endpoint.

    Usage::

        from src.api.security.ownership import resource_owner_dependency
        from src.storage.repositories.portfolio_repository import PortfolioRepository

        async def _get_portfolio(portfolio_id: UUID, tenant_id: UUID):
            ...  # repository lookup

        get_portfolio_dep = resource_owner_dependency(_get_portfolio)

        @router.get("/portfolios/{portfolio_id}")
        async def get_portfolio(
            portfolio_id: UUID,
            resource = Depends(get_portfolio_dep),
        ):
            return resource

    Args:
        get_resource_fn: Async callable with signature
            ``(resource_id: UUID, tenant_id: UUID) -> Any | None``.
            Must accept two positional UUID arguments.

    Returns:
        An async FastAPI-compatible dependency callable.
    """
    from fastapi import Depends
    from src.api.auth.dependencies import get_current_user
    from src.storage.models.user import User

    async def _dependency(
        resource_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
    ) -> Any:
        tenant_id: uuid.UUID = current_user.tenant_id

        resource = await get_resource_fn(resource_id, tenant_id)

        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Resource not found"},
            )

        try:
            verify_resource_ownership(resource, tenant_id, resource_id)
        except ResourceNotOwnedError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Resource not found"},
            )

        return resource

    return _dependency
