"""
api.auth.schemas — Pydantic request/response models for auth endpoints.
"""
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response body returned on successful login or token refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class AccessTokenClaims(BaseModel):
    """Decoded and validated claims from an access JWT.

    Mirrors src.api.auth.token_service.AccessTokenClaims —
    re-exported here so other modules can import from schemas.
    """

    sub: str        # user_id as string
    tenant_id: str
    role: str
    iat: int
    exp: int
