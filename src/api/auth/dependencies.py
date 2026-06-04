"""
api.auth.dependencies — FastAPI dependency functions for authentication and authorization.

Three public dependencies:
  - get_current_user: validates Bearer JWT and returns the authenticated User.
  - require_admin: HTTP 403 unless the user has role=admin.
  - require_operator_or_above: HTTP 403 unless the user has role=admin or operator.

Security rules:
  - Expired or tampered JWT -> HTTP 401 (never 403, to avoid leaking auth state).
  - User not found in DB -> HTTP 401 (not 404, to prevent user enumeration).
  - tenant_id mismatch between token and DB row -> HTTP 401 (IDOR guard).
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth.token_service import InvalidTokenError, TokenExpiredError, TokenService
from src.config.settings import get_settings
from src.storage.models.user import User, UserRole
from src.storage.repositories.user_repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_settings = get_settings()
_token_service = TokenService(settings=_settings)


async def get_db() -> AsyncSession:  # type: ignore[return]
    """Provide an async database session.

    Imported from src.api.dependencies in production; re-exported here for
    convenience. Tests override via app.dependency_overrides.
    """
    from src.api.dependencies import get_db as _get_db
    async for session in _get_db():
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate a Bearer JWT; return the authenticated User.

    Raises:
        HTTPException 401: expired token, tampered signature, user not found,
                           or tenant_id mismatch (IDOR guard).
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHORIZED", "message": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        claims = _token_service.decodeAccessToken(token)
    except (TokenExpiredError, InvalidTokenError):
        raise _unauthorized

    try:
        user_id = uuid.UUID(claims.sub)
        tenant_id = uuid.UUID(claims.tenant_id)
    except (ValueError, AttributeError):
        raise _unauthorized

    user_repo = UserRepository(session=db)
    user = await user_repo.getById(user_id=user_id, tenant_id=tenant_id)

    if user is None:
        raise _unauthorized

    # IDOR guard: confirm the tenant_id embedded in the token matches DB row
    if str(user.tenant_id) != claims.tenant_id:
        raise _unauthorized

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to have role=admin.

    Raises:
        HTTPException 403: if the user's role is not admin.
    """
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Admin role required"},
        )
    return current_user


async def require_operator_or_above(current_user: User = Depends(get_current_user)) -> User:
    """Require the current user to have role=admin or role=operator.

    Raises:
        HTTPException 403: if the user's role is end_user.
    """
    if current_user.role == UserRole.end_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Operator or admin role required"},
        )
    return current_user
