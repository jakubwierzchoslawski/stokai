"""JWT authentication dependencies for FastAPI.

All endpoints require a valid JWT token by default.
Role-based access: admin | operator | end_user.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedUser:
    """Parsed JWT claims for the current request."""

    def __init__(self, user_id: UUID, tenant_id: UUID, role: str) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_operator_or_above(self) -> bool:
        return self.role in ("admin", "operator")


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Validate JWT and return the current user.

    In production, this decodes and verifies the JWT.
    Raises HTTP 401 on missing/invalid token.
    """
    from src.config.settings import get_settings
    import jwt as pyjwt

    settings = get_settings()
    token = credentials.credentials

    try:
        payload = pyjwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
        )
        user_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
        role = payload.get("role", "end_user")
        return AuthenticatedUser(user_id=user_id, tenant_id=tenant_id, role=role)
    except Exception as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_admin(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Require admin role; raise HTTP 403 otherwise."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
AdminUser = Annotated[AuthenticatedUser, Depends(require_admin)]
