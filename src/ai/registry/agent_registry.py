"""AgentRegistry — loads, validates, and resolves AgentDefinition objects.

Instantiated once at startup; injected wherever needed.
All agent config is read exclusively from YAML files under agents_dir.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.ai.registry.agent_definition import AgentDefinition, load_agent_definition
from src.ai.registry.exceptions import AgentNotFoundError, StartupValidationError

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Loads all agent YAML definitions from disk and validates them at startup.

    Implements IAgentRegistry protocol (see interfaces.py).

    Args:
        agents_dir: Directory containing *.yaml agent definition files.
        base_dir: Root directory used to resolve relative system_prompt_file paths.
                  Defaults to agents_dir.parent if not supplied.
    """

    def __init__(
        self,
        agents_dir: Path,
        base_dir: Path | None = None,
    ) -> None:
        self._agents_dir = agents_dir
        self._base_dir = base_dir or agents_dir.parent
        self._definitions: dict[str, AgentDefinition] = {}
        self._load_and_validate()

    # ------------------------------------------------------------------
    # IAgentRegistry protocol
    # ------------------------------------------------------------------

    def resolve(self, role_id: str) -> AgentDefinition:
        """Return the AgentDefinition for the given role_id.

        Raises:
            AgentNotFoundError: If no agent with that role_id is registered.
        """
        try:
            return self._definitions[role_id]
        except KeyError:
            raise AgentNotFoundError(
                role_id=role_id,
                registered_ids=list(self._definitions.keys()),
            ) from None

    def all_definitions(self) -> list[AgentDefinition]:
        """Return all registered AgentDefinition objects (order is stable)."""
        return list(self._definitions.values())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_and_validate(self) -> None:
        """Discover YAML files, parse and validate each, check prompt files exist.

        Skips files without a ``role_id`` key (workflow YAMLs, e.g.
        ``morning_brief_workflow.yaml``, use ``workflow_id`` instead and are
        not agent definitions).
        """
        yaml_paths = sorted(self._agents_dir.glob("*.yaml"))
        failures: list[str] = []

        for yaml_path in yaml_paths:
            # Skip non-agent YAMLs (workflow configs, etc.) by checking for role_id
            try:
                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"{yaml_path.name}: failed to read — {exc}")
                continue

            if raw is None or not isinstance(raw, dict):
                logger.debug("Skipping non-dict YAML: %s", yaml_path.name)
                continue

            if "role_id" not in raw:
                logger.debug(
                    "Skipping non-agent YAML (no role_id): %s", yaml_path.name
                )
                continue

            try:
                defn = load_agent_definition(yaml_path)
            except ValidationError as exc:
                failures.append(
                    f"{yaml_path.name}: schema validation failed — {exc}"
                )
                continue
            except Exception as exc:
                failures.append(f"{yaml_path.name}: failed to load — {exc}")
                continue

            # Verify the referenced system prompt file exists on disk
            prompt_path = self._base_dir / defn.system_prompt_file
            if not prompt_path.exists():
                failures.append(
                    f"{yaml_path.name}: system_prompt_file not found: "
                    f"{defn.system_prompt_file!r} (resolved to {prompt_path})"
                )
                continue

            if defn.role_id in self._definitions:
                failures.append(
                    f"{yaml_path.name}: duplicate role_id={defn.role_id!r} "
                    f"(already loaded from another file)"
                )
                continue

            self._definitions[defn.role_id] = defn
            logger.debug("Loaded agent definition: role_id=%s", defn.role_id)

        if failures:
            raise StartupValidationError(failures=failures)

        logger.info(
            "AgentRegistry initialised with %d agents: %s",
            len(self._definitions),
            sorted(self._definitions.keys()),
        )
