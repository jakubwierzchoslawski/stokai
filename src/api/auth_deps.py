"""
FastAPI authentication and authorisation dependencies.

JWT-based; roles: admin | operator | end_user.
Tokens validated via python-jose against JWT_SECRET_KEY from settings.

Usage:
    current_user = Depends(get_current_user)
    admin_user   = Depends(require_admin)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.settings import get_settings

_bearer = HTTPBearer(auto_error=True)

ROLES = {"admin", "operator", "end_user"}


@dataclass
class CurrentUser:
    """Decoded JWT claim payload available to route handlers."""

    user_id: UUID
    tenant_id: UUID
    role: str
    email: str


def _decode_token(token: str) -> CurrentUser:
    """Decode and validate a JWT access token."""
    from jose import JWTError, jwt

    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token is invalid or expired."},
        ) from exc

    try:
        return CurrentUser(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            role=payload["role"],
            email=payload.get("email", ""),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token payload is malformed."},
        ) from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """Return the decoded CurrentUser from the Bearer token."""
    return _decode_token(credentials.credentials)


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Raise 403 if the current user is not an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required."},
        )
    return current_user
