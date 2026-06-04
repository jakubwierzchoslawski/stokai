"""
api.security — reusable security utilities for FastAPI endpoints.

Exports:
    verify_resource_ownership — confirm resource.tenant_id == requesting tenant.
    resource_owner_dependency — FastAPI dependency factory for IDOR-safe lookups.
    ResourceNotOwnedError — raised when ownership check fails.
    portfolio_write_limit — SlowAPI rate-limit decorator: 100/minute per user.
    admin_mutation_limit — SlowAPI rate-limit decorator: 60/minute per admin user.
"""
from src.api.security.ownership import (
    ResourceNotOwnedError,
    resource_owner_dependency,
    verify_resource_ownership,
)
from src.api.middleware.rate_limit import portfolio_write_limit, admin_mutation_limit

__all__ = [
    "ResourceNotOwnedError",
    "resource_owner_dependency",
    "verify_resource_ownership",
    "portfolio_write_limit",
    "admin_mutation_limit",
]
