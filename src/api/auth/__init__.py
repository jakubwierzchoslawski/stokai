"""
api.auth — Authentication and authorization module.

Exposes FastAPI dependencies for use by other modules:
  from src.api.auth import get_current_user, require_admin, require_operator_or_above
  from src.api.auth import CurrentUser, AdminUser  (Annotated type aliases)
"""
from src.api.auth.dependencies import (
    get_current_user,
    require_admin,
    require_operator_or_above,
)

# Type aliases imported by scoring routers. Source of truth is auth_deps.py
# which is used by the company_detail_router and other lightweight endpoints.
from src.api.auth_deps import CurrentUser  # noqa: F401
from src.api.auth_deps import require_admin as _require_admin_deps

from typing import Annotated
from fastapi import Depends
AdminUser = Annotated[CurrentUser, Depends(_require_admin_deps)]  # type: ignore[misc]

__all__ = [
    "get_current_user",
    "require_admin",
    "require_operator_or_above",
    "CurrentUser",
    "AdminUser",
]
