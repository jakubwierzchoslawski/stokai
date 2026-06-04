"""
api.auth — Authentication and authorization module.

Exposes FastAPI dependencies for use by other modules:
  from src.api.auth import get_current_user, require_admin, require_operator_or_above
"""
from src.api.auth.dependencies import (
    get_current_user,
    require_admin,
    require_operator_or_above,
)

__all__ = ["get_current_user", "require_admin", "require_operator_or_above"]
