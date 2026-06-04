"""
api.middleware.rate_limit — IP-based and user-based rate limiting via SlowAPI.

Creates a global Limiter backed by Redis. The limiter instance is imported by
the auth router to apply per-route limits and by main.py to register the
429 error handler on the FastAPI application.

Usage in main.py:
    from src.api.middleware.rate_limit import limiter, rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

Usage in router:
    from slowapi import Limiter
    @router.post("/login")
    @limiter.limit("10/minute")
    async def login(request: Request, ...): ...

    from src.api.middleware.rate_limit import portfolio_write_limit, admin_mutation_limit
    @router.post("/portfolios")
    @portfolio_write_limit
    async def create_portfolio(request: Request, ...): ...
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config.settings import get_settings

_settings = get_settings()

# Global limiter — stored on app.state.limiter by main.py.
# Redis URI is read from settings so limits survive process restarts.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings.REDIS_URL,
)


def get_user_id_from_request(request: Request) -> str:
    """Extract the user ID (sub claim) from the Bearer JWT in the Authorization header.

    Used as the rate-limit key function for authenticated endpoints.  This avoids
    keying by IP address (which can be shared by many users behind NAT) and instead
    applies limits per authenticated user.

    Falls back to the remote IP address if:
      - The Authorization header is absent.
      - The token is malformed or cannot be decoded without verification.

    Note: This function decodes the JWT **without signature verification** purely
    to extract the ``sub`` claim for rate-limit keying. Full verification is
    performed by ``get_current_user`` in the route handler. This is intentional —
    invalid tokens will still fail at the auth dependency.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return get_remote_address(request)

    token = auth_header.removeprefix("Bearer ")
    try:
        # Decode without verification — we only need the sub claim for key bucketing.
        payload = jwt.decode(
            token,
            key="",  # dummy key — verification disabled via options below
            algorithms=[_settings.JWT_ALGORITHM],
            options={"verify_signature": False, "verify_exp": False},
        )
        sub = payload.get("sub")
        if sub:
            return str(sub)
    except (JWTError, Exception):
        pass

    return get_remote_address(request)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured 429 response conforming to the project error envelope."""
    return JSONResponse(
        status_code=429,
        content={
            "data": None,
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please try again later.",
            },
        },
    )


# ── Pre-configured rate-limit decorators for feature routers ─────────────────

# 100 writes per minute per authenticated user (keyed by JWT sub claim).
# Applied to portfolio creation / update / delete endpoints.
portfolio_write_limit = limiter.limit(
    "100/minute",
    key_func=get_user_id_from_request,
)

# 60 mutations per minute per authenticated admin user.
# Applied to admin-only endpoints (user management, tenant configuration, etc.).
admin_mutation_limit = limiter.limit(
    "60/minute",
    key_func=get_user_id_from_request,
)
