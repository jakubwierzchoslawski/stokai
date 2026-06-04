"""Exceptions raised by the agent registry."""
from __future__ import annotations


class AgentNotFoundError(KeyError):
    """Raised when resolve() is called with an unknown role_id."""

    def __init__(self, role_id: str, registered_ids: list[str]) -> None:
        self.role_id = role_id
        self.registered_ids = registered_ids
        super().__init__(
            f"No agent registered with role_id={role_id!r}. "
            f"Registered: {sorted(registered_ids)}"
        )


class StartupValidationError(RuntimeError):
    """Raised during registry initialisation if any definition is invalid."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        bullet_list = "\n  - ".join(failures)
        super().__init__(
            f"AgentRegistry startup validation failed:\n  - {bullet_list}"
        )
