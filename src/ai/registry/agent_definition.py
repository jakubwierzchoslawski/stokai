"""AgentDefinition Pydantic v2 model and YAML loader.

All agent configuration is read from YAML — no hardcoded model names,
tool lists, or limit values in this module.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """LLM model configuration for an agent."""

    provider: str
    model_id: str
    temperature: float = Field(ge=0.0, le=1.0)
    max_tokens: int = Field(gt=0)

    @field_validator("provider")
    @classmethod
    def provider_must_be_anthropic(cls, v: str) -> str:
        """Decision D6: only the Anthropic provider is allowed in MVP."""
        if v != "anthropic":
            raise ValueError(
                f"provider must be 'anthropic' in MVP (Decision D6), got: {v!r}"
            )
        return v


class AgentLimits(BaseModel):
    """Bounded-execution limits for an agent node."""

    max_input_tokens: int = Field(gt=0)
    max_iterations: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    cost_ceiling_usd: float = Field(gt=0.0)


class AgentDefinition(BaseModel):
    """Validated definition of a single named-role agent.

    Loaded from agents/{role_id}.yaml at startup by AgentRegistry.
    All values come exclusively from YAML — no defaults embed model names
    or tool lists.
    """

    role_id: str
    persona: str
    system_prompt_file: str
    model: ModelConfig
    tools: list[str]
    limits: AgentLimits
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    output_schema: dict[str, Any]

    @field_validator("role_id")
    @classmethod
    def role_id_must_be_kebab_case(cls, v: str) -> str:
        """role_id must be lowercase kebab-case (e.g. 'relevance-analyst')."""
        if not re.fullmatch(r"[a-z][a-z0-9-]*", v):
            raise ValueError(
                f"role_id must be kebab-case (lowercase letters, digits, hyphens), "
                f"got: {v!r}"
            )
        return v


def load_agent_definition(path: Path) -> AgentDefinition:
    """Parse a YAML file and return a validated AgentDefinition.

    Args:
        path: Absolute or relative path to an agent YAML definition file.

    Returns:
        Validated AgentDefinition instance.

    Raises:
        pydantic.ValidationError: If the YAML content fails schema validation.
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgentDefinition.model_validate(raw)
