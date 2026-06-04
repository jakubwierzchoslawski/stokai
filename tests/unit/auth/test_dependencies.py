"""
Unit tests for FastAPI auth dependencies.

Tests cover get_current_user, require_admin, and require_operator_or_above.
All external collaborators (TokenService, UserRepository, DB session) are mocked.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.auth.token_service import AccessTokenClaims, InvalidTokenError, TokenExpiredError
from src.storage.models.user import User, UserRole


def _make_claims(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str = "admin",
) -> AccessTokenClaims:
    import time
    now = int(time.time())
    return AccessTokenClaims(
        sub=str(user_id),
        tenant_id=str(tenant_id),
        role=role,
        iat=now,
        exp=now + 900,
    )


def _make_user(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: UserRole = UserRole.admin,
) -> MagicMock:
    user = MagicMock(spec=User)
    user.user_id = user_id
    user.tenant_id = tenant_id
    user.role = role
    return user


# ── get_current_user ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_current_user_valid_token_returns_user() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    claims = _make_claims(user_id, tenant_id, role="admin")
    user = _make_user(user_id, tenant_id, UserRole.admin)

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.getById.return_value = user

    with (
        patch("src.api.auth.dependencies._token_service") as mock_ts,
        patch("src.api.auth.dependencies.UserRepository", return_value=mock_repo),
    ):
        mock_ts.decodeAccessToken.return_value = claims

        from src.api.auth.dependencies import get_current_user
        result = await get_current_user(token="valid.jwt.token", db=mock_db)

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_expired_token_raises_401() -> None:
    mock_db = AsyncMock()

    with patch("src.api.auth.dependencies._token_service") as mock_ts:
        mock_ts.decodeAccessToken.side_effect = TokenExpiredError("expired")

        from src.api.auth.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="expired.token", db=mock_db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_tampered_token_raises_401() -> None:
    mock_db = AsyncMock()

    with patch("src.api.auth.dependencies._token_service") as mock_ts:
        mock_ts.decodeAccessToken.side_effect = InvalidTokenError("invalid")

        from src.api.auth.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="tampered.token", db=mock_db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_user_not_found_in_db_raises_401() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    claims = _make_claims(user_id, tenant_id)

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.getById.return_value = None  # not found

    with (
        patch("src.api.auth.dependencies._token_service") as mock_ts,
        patch("src.api.auth.dependencies.UserRepository", return_value=mock_repo),
    ):
        mock_ts.decodeAccessToken.return_value = claims

        from src.api.auth.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="valid.jwt.token", db=mock_db)

    # Must be 401, NOT 404 (to prevent user enumeration)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_tenant_mismatch_raises_401() -> None:
    """IDOR guard: token.tenant_id != user.tenant_id must yield HTTP 401."""
    user_id = uuid.uuid4()
    token_tenant_id = uuid.uuid4()
    db_tenant_id = uuid.uuid4()  # different tenant in DB row

    claims = _make_claims(user_id, token_tenant_id)
    # User is returned from DB but has a different tenant_id
    user = _make_user(user_id, db_tenant_id, UserRole.admin)

    mock_db = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.getById.return_value = user

    with (
        patch("src.api.auth.dependencies._token_service") as mock_ts,
        patch("src.api.auth.dependencies.UserRepository", return_value=mock_repo),
    ):
        mock_ts.decodeAccessToken.return_value = claims

        from src.api.auth.dependencies import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="valid.jwt.token", db=mock_db)

    assert exc_info.value.status_code == 401


# ── require_admin ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_admin_passes_for_admin_role() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.admin)

    from src.api.auth.dependencies import require_admin
    result = await require_admin(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_raises_403_for_operator() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.operator)

    from src.api.auth.dependencies import require_admin
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(current_user=user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_raises_403_for_end_user() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.end_user)

    from src.api.auth.dependencies import require_admin
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(current_user=user)
    assert exc_info.value.status_code == 403


# ── require_operator_or_above ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_require_operator_or_above_passes_for_admin() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.admin)

    from src.api.auth.dependencies import require_operator_or_above
    result = await require_operator_or_above(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_operator_or_above_passes_for_operator() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.operator)

    from src.api.auth.dependencies import require_operator_or_above
    result = await require_operator_or_above(current_user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_operator_or_above_raises_403_for_end_user() -> None:
    user = _make_user(uuid.uuid4(), uuid.uuid4(), UserRole.end_user)

    from src.api.auth.dependencies import require_operator_or_above
    with pytest.raises(HTTPException) as exc_info:
        await require_operator_or_above(current_user=user)
    assert exc_info.value.status_code == 403
