"""
api.auth.router — FastAPI router for authentication endpoints.

Endpoints:
  POST /api/v1/auth/login    — credential validation, token issuance
  POST /api/v1/auth/refresh  — refresh token rotation (access token renewal)
  POST /api/v1/auth/logout   — refresh token revocation

Refresh tokens are delivered in HttpOnly cookies (SameSite=Strict).
Access tokens are returned in the response body.
Stack traces are never returned to clients.
Rate limiting: 10/minute on login, 30/minute on refresh (IP-based via SlowAPI).
"""
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from src.api.auth.auth_service import AuthService
from src.api.auth.exceptions import AuthenticationError
from src.api.auth.schemas import LoginRequest, TokenResponse
from src.api.middleware.rate_limit import limiter
from src.config.settings import get_settings

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()

# Cookie configuration constants
_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
_REFRESH_COOKIE_MAX_AGE = _settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def get_auth_service() -> AuthService:
    """FastAPI dependency that provides an AuthService instance.

    In production this is overridden with a real injected service.
    In tests this is overridden via app.dependency_overrides.
    """
    from src.api.auth.token_service import TokenService
    from src.storage.repositories.user_repository import UserRepository
    from src.storage.repositories.refresh_token_repository import RefreshTokenRepository

    raise NotImplementedError(
        "get_auth_service must be overridden with a configured AuthService instance."
    )


def _success_envelope(data: dict) -> dict:
    return {"data": data, "meta": {}, "error": None}


def _error_envelope(code: str, message: str) -> dict:
    return {"data": None, "error": {"code": code, "message": message}}


@auth_router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """Validate credentials and issue JWT access + refresh tokens.

    Returns:
        200 with TokenResponse in data envelope + HttpOnly refresh cookie.
        401 on invalid credentials (generic message — no email/password oracle).
        422 on malformed request body.
    """
    try:
        access_token, token_id, raw_refresh = await auth_service.login(
            email=body.email,
            password=body.password,
            tenant_id=_extract_tenant_id(request),
        )
    except AuthenticationError:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_envelope("UNAUTHORIZED", "Invalid credentials"),
        )

    token_response = TokenResponse(
        access_token=access_token,
        expires_in=_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    json_response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_success_envelope(token_response.model_dump()),
    )
    # Encode token_id + raw token into the cookie value as "<token_id>:<raw_token>"
    cookie_value = f"{token_id}:{raw_refresh}"
    json_response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=cookie_value,
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=_settings.ENVIRONMENT != "local",
    )
    return json_response


@auth_router.post("/refresh")
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    refresh_token: str | None = Cookie(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> JSONResponse:
    """Issue a new access token using a valid refresh token cookie.

    Returns:
        200 with new TokenResponse.
        401 if cookie is missing, token is revoked, or token is expired.
    """
    if refresh_token is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_envelope("UNAUTHORIZED", "Refresh token not provided"),
        )

    try:
        token_id_str, raw_token = _parse_refresh_cookie(refresh_token)
        token_id = uuid.UUID(token_id_str)
        tenant_id = _extract_tenant_id(request)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_envelope("UNAUTHORIZED", "Invalid refresh token"),
        )

    try:
        # For refresh we need the user object — get from a simple DB lookup via repo
        # The auth service refresh method needs user for creating a new access token
        from src.storage.repositories.user_repository import UserRepository
        from src.storage.repositories.refresh_token_repository import RefreshTokenRepository

        # In MVP, pass user=None and let auth_service handle active token lookup
        new_access_token = await auth_service.refresh(
            token_id=token_id,
            raw_token=raw_token,
            tenant_id=tenant_id,
            user=None,  # auth_service handles user lookup via active token
        )
    except (AuthenticationError, Exception):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=_error_envelope("UNAUTHORIZED", "Invalid or expired refresh token"),
        )

    token_response = TokenResponse(
        access_token=new_access_token,
        expires_in=_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=_success_envelope(token_response.model_dump()),
    )


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Revoke the refresh token and clear the HttpOnly cookie.

    Returns:
        204 No Content on success (always — even if token not found).
    """
    if refresh_token is not None:
        try:
            token_id_str, _raw = _parse_refresh_cookie(refresh_token)
            token_id = uuid.UUID(token_id_str)
            tenant_id = _extract_tenant_id(request)
            await auth_service.logout(token_id=token_id, tenant_id=tenant_id)
        except (ValueError, TypeError, Exception):
            pass  # Revocation is best-effort; always clear the cookie

    # Clear the cookie unconditionally
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value="",
        max_age=0,
        path=_REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
    )
    return response


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_refresh_cookie(cookie_value: str) -> tuple[str, str]:
    """Parse '<token_id>:<raw_token>' from the cookie value."""
    parts = cookie_value.split(":", 1)
    if len(parts) != 2:
        raise ValueError("Malformed refresh token cookie")
    return parts[0], parts[1]


def _extract_tenant_id(request: Request) -> uuid.UUID:
    """Extract tenant_id from the request.

    MVP: tenant_id is provided in the X-Tenant-ID header.
    Post-MVP: resolved from subdomain or JWT.
    Raises HTTPException 400 if missing/invalid.
    """
    tenant_header = request.headers.get("X-Tenant-ID")
    if not tenant_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required",
        )
    try:
        return uuid.UUID(tenant_header)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID must be a valid UUID",
        )
