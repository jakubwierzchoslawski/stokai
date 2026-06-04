"""Protocol interfaces for the agent registry."""
from __future__ import annotations

from typing import Protocol

from src.ai.registry.agent_definition import AgentDefinition


class IAgentRegistry(Protocol):
    """Read-only view of the agent registry used by workflow nodes."""

    def resolve(self, role_id: str) -> AgentDefinition:
        """Return the AgentDefinition for the given role_id.

        Raises:
            AgentNotFoundError: If no agent with that role_id is registered.
        """
        ...

    def all_definitions(self) -> list[AgentDefinition]:
        """Return all registered AgentDefinition objects."""
        ...
