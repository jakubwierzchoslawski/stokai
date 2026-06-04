"""
portfolio.exceptions — domain exceptions for portfolio and watchlist operations.
"""
from __future__ import annotations


class NotFoundError(Exception):
    """Raised when a requested resource does not exist or belongs to another tenant."""

    def __init__(self, resource: str = "Resource", resource_id: object = None) -> None:
        msg = f"{resource} not found"
        if resource_id is not None:
            msg = f"{resource} {resource_id!r} not found"
        super().__init__(msg)


class ConflictError(Exception):
    """Raised when a uniqueness constraint would be violated."""

    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message)


class ValidationError(Exception):
    """Raised when input data fails domain validation."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message)
