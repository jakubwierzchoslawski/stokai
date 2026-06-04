"""Unit tests for AgentRegistry.

TDD: tests written before implementation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ai.registry.agent_definition import AgentDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_yaml(role_id: str, prompt_rel: str = "") -> dict:
    """Build a minimal valid agent YAML dict."""
    return {
        "role_id": role_id,
        "persona": f"Persona for {role_id}",
        "system_prompt_file": prompt_rel or f"prompts/agents/{role_id.replace('-', '_')}.md",
        "model": {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        "tools": ["get_market_data"],
        "limits": {
            "max_input_tokens": 8000,
            "max_iterations": 3,
            "timeout_seconds": 60,
            "cost_ceiling_usd": 0.10,
        },
        "confidence_threshold": 0.7,
        "output_schema": {},
    }


NINE_ROLE_IDS = [
    "relevance-analyst",
    "anomaly-detector",
    "exposure-analyst",
    "historical-context-agent",
    "recommendation-synthesizer",
    "narrative-writer",
    "earnings-context-agent",
    "event-deep-dive-agent",
    "qa-analyst",
]


def _create_nine_agents(agents_dir: Path, prompts_dir: Path) -> None:
    """Write nine valid YAML files and matching prompt stubs."""
    for role_id in NINE_ROLE_IDS:
        prompt_name = role_id.replace("-", "_") + ".md"
        prompt_path = prompts_dir / prompt_name
        prompt_path.write_text(f"# {role_id} stub\n", encoding="utf-8")

        rel_prompt = f"prompts/agents/{prompt_name}"
        data = _make_agent_yaml(role_id, rel_prompt)
        yaml_path = agents_dir / f"{role_id}.yaml"
        yaml_path.write_text(yaml.dump(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestRegistryLoadsAllNineAgents:
    def test_registry_loads_all_nine_agents(self, tmp_path: Path) -> None:
        """Given a directory with nine valid YAMLs, registry has nine definitions."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        prompts_dir = tmp_path / "prompts" / "agents"
        prompts_dir.mkdir(parents=True)

        _create_nine_agents(agents_dir, prompts_dir)

        from src.ai.registry.agent_registry import AgentRegistry

        registry = AgentRegistry(agents_dir=agents_dir, base_dir=tmp_path)
        assert len(registry.all_definitions()) == 9


class TestResolveReturnsCorrectDefinition:
    def test_resolve_returns_correct_definition(self, tmp_path: Path) -> None:
        """resolve('relevance-analyst') returns the matching definition."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        prompts_dir = tmp_path / "prompts" / "agents"
        prompts_dir.mkdir(parents=True)

        _create_nine_agents(agents_dir, prompts_dir)

        from src.ai.registry.agent_registry import AgentRegistry

        registry = AgentRegistry(agents_dir=agents_dir, base_dir=tmp_path)
        defn = registry.resolve("relevance-analyst")

        assert isinstance(defn, AgentDefinition)
        assert defn.role_id == "relevance-analyst"


class TestResolveUnknownRoleIdRaisesAgentNotFoundError:
    def test_resolve_unknown_role_id_raises_agent_not_found_error(
        self, tmp_path: Path
    ) -> None:
        """resolve() with unknown role_id raises AgentNotFoundError."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        prompts_dir = tmp_path / "prompts" / "agents"
        prompts_dir.mkdir(parents=True)

        _create_nine_agents(agents_dir, prompts_dir)

        from src.ai.registry.agent_registry import AgentRegistry
        from src.ai.registry.exceptions import AgentNotFoundError

        registry = AgentRegistry(agents_dir=agents_dir, base_dir=tmp_path)

        with pytest.raises(AgentNotFoundError, match="no-such-agent"):
            registry.resolve("no-such-agent")


class TestMissingPromptFileRaisesStartupValidationError:
    def test_missing_prompt_file_raises_startup_validation_error(
        self, tmp_path: Path
    ) -> None:
        """If a YAML references a non-existent prompt file, StartupValidationError is raised."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # Write a YAML pointing to a prompt file that does NOT exist
        data = _make_agent_yaml("relevance-analyst", "prompts/agents/nonexistent.md")
        (agents_dir / "relevance-analyst.yaml").write_text(
            yaml.dump(data), encoding="utf-8"
        )

        from src.ai.registry.agent_registry import AgentRegistry
        from src.ai.registry.exceptions import StartupValidationError

        with pytest.raises(StartupValidationError, match="nonexistent.md"):
            AgentRegistry(agents_dir=agents_dir, base_dir=tmp_path)


class TestRegistryRejectsDirectoryWithInvalidYaml:
    def test_registry_rejects_directory_with_invalid_yaml(
        self, tmp_path: Path
    ) -> None:
        """A YAML missing a required field raises StartupValidationError."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()

        # missing 'limits' field
        data = _make_agent_yaml("relevance-analyst")
        del data["limits"]
        (agents_dir / "relevance-analyst.yaml").write_text(
            yaml.dump(data), encoding="utf-8"
        )

        from src.ai.registry.agent_registry import AgentRegistry
        from src.ai.registry.exceptions import StartupValidationError

        with pytest.raises(StartupValidationError):
            AgentRegistry(agents_dir=agents_dir, base_dir=tmp_path)
