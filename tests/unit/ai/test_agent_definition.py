"""Unit tests for AgentDefinition Pydantic model.

TDD: these tests were written before the implementation.
"""
import textwrap
from pathlib import Path

import pytest
import yaml

from src.ai.registry.agent_definition import AgentDefinition, load_agent_definition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_yaml(overrides: dict | None = None) -> dict:
    """Return a minimal valid agent definition dict."""
    base = {
        "role_id": "relevance-analyst",
        "persona": "You are a relevance analyst.",
        "system_prompt_file": "prompts/agents/relevance_analyst.md",
        "model": {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "temperature": 0.3,
            "max_tokens": 2048,
        },
        "tools": ["query_portfolio", "get_market_data"],
        "limits": {
            "max_input_tokens": 8000,
            "max_iterations": 3,
            "timeout_seconds": 60,
            "cost_ceiling_usd": 0.10,
        },
        "confidence_threshold": 0.7,
        "output_schema": {"type": "object", "properties": {}},
    }
    if overrides:
        base.update(overrides)
    return base


def _write_yaml(tmp_path: Path, data: dict, filename: str = "agent.yaml") -> Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# AC-001: valid YAML loads correctly
# ---------------------------------------------------------------------------

class TestValidYamlLoadsToAgentDefinition:
    def test_valid_yaml_loads_to_agent_definition(self, tmp_path: Path) -> None:
        """A minimal valid YAML file should deserialise to AgentDefinition with all fields."""
        data = _minimal_yaml()
        path = _write_yaml(tmp_path, data)

        defn = load_agent_definition(path)

        assert defn.role_id == "relevance-analyst"
        assert defn.persona == "You are a relevance analyst."
        assert defn.system_prompt_file == "prompts/agents/relevance_analyst.md"
        assert defn.model.provider == "anthropic"
        assert defn.model.model_id == "claude-sonnet-4-6"
        assert defn.model.temperature == 0.3
        assert defn.model.max_tokens == 2048
        assert defn.tools == ["query_portfolio", "get_market_data"]
        assert defn.limits.max_input_tokens == 8000
        assert defn.limits.max_iterations == 3
        assert defn.limits.timeout_seconds == 60
        assert defn.limits.cost_ceiling_usd == 0.10
        assert defn.confidence_threshold == 0.7
        assert isinstance(defn.output_schema, dict)


# ---------------------------------------------------------------------------
# AC-001: missing required fields
# ---------------------------------------------------------------------------

class TestMissingRequiredFieldRaisesValidationError:
    REQUIRED_FIELDS = [
        "role_id",
        "persona",
        "system_prompt_file",
        "model",
        "tools",
        "limits",
        "confidence_threshold",
        "output_schema",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_missing_required_field_raises_validation_error(
        self, tmp_path: Path, field: str
    ) -> None:
        """Each required field missing should raise a Pydantic ValidationError."""
        from pydantic import ValidationError

        data = _minimal_yaml()
        del data[field]
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError):
            load_agent_definition(path)


# ---------------------------------------------------------------------------
# AC-001: role_id format validation
# ---------------------------------------------------------------------------

class TestInvalidRoleIdFormatRaisesValidationError:
    def test_invalid_role_id_format_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """PascalCase role_id must be rejected."""
        from pydantic import ValidationError

        data = _minimal_yaml({"role_id": "RelevanceAnalyst"})
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError, match="kebab-case"):
            load_agent_definition(path)

    def test_underscore_role_id_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """Underscore-separated role_id must be rejected (must use hyphens)."""
        from pydantic import ValidationError

        data = _minimal_yaml({"role_id": "relevance_analyst"})
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError, match="kebab-case"):
            load_agent_definition(path)


# ---------------------------------------------------------------------------
# AC-001 / D6: provider must be "anthropic"
# ---------------------------------------------------------------------------

class TestNonAnthropicProviderRaisesValidationError:
    def test_non_anthropic_provider_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """provider='openai' must be rejected (Decision D6: Anthropic only in MVP)."""
        from pydantic import ValidationError

        data = _minimal_yaml()
        data["model"]["provider"] = "openai"
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError, match="anthropic"):
            load_agent_definition(path)


# ---------------------------------------------------------------------------
# Temperature validation
# ---------------------------------------------------------------------------

class TestTemperatureOutOfRangeRaisesValidationError:
    def test_temperature_out_of_range_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """temperature=1.5 must fail Field(ge=0.0, le=1.0) constraint."""
        from pydantic import ValidationError

        data = _minimal_yaml()
        data["model"]["temperature"] = 1.5
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError):
            load_agent_definition(path)


# ---------------------------------------------------------------------------
# Cost ceiling validation
# ---------------------------------------------------------------------------

class TestCostCeilingMustBePositive:
    def test_cost_ceiling_must_be_positive(self, tmp_path: Path) -> None:
        """cost_ceiling_usd=0.0 must fail Field(gt=0.0)."""
        from pydantic import ValidationError

        data = _minimal_yaml()
        data["limits"]["cost_ceiling_usd"] = 0.0
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError):
            load_agent_definition(path)


# ---------------------------------------------------------------------------
# Confidence threshold bounds
# ---------------------------------------------------------------------------

class TestConfidenceThresholdBounds:
    def test_confidence_threshold_zero_is_valid(self, tmp_path: Path) -> None:
        """confidence_threshold=0.0 is at lower bound and must be accepted."""
        data = _minimal_yaml({"confidence_threshold": 0.0})
        path = _write_yaml(tmp_path, data)
        defn = load_agent_definition(path)
        assert defn.confidence_threshold == 0.0

    def test_confidence_threshold_one_is_valid(self, tmp_path: Path) -> None:
        """confidence_threshold=1.0 is at upper bound and must be accepted."""
        data = _minimal_yaml({"confidence_threshold": 1.0})
        path = _write_yaml(tmp_path, data)
        defn = load_agent_definition(path)
        assert defn.confidence_threshold == 1.0

    def test_confidence_threshold_above_one_raises_validation_error(
        self, tmp_path: Path
    ) -> None:
        """confidence_threshold=1.1 must fail Field(le=1.0)."""
        from pydantic import ValidationError

        data = _minimal_yaml({"confidence_threshold": 1.1})
        path = _write_yaml(tmp_path, data)

        with pytest.raises(ValidationError):
            load_agent_definition(path)
