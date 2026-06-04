"""
api.auth.exceptions — Shared exception types for the auth module.
"""


class AuthenticationError(Exception):
    """Raised when authentication fails (wrong credentials, expired token, etc.).

    The message is intentionally generic — callers must not reveal whether
    the email or password was the cause of failure.
    """
