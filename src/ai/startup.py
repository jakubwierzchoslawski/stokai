"""AI module startup — wires AgentRegistry, WorkflowStructureValidator, and ToolRegistry.

Called from the FastAPI lifespan context manager so the application fails
fast at startup if any agent YAML is invalid, any prompt file is missing,
any registered workflow violates the structural invariant, or any tool name
listed in an AgentDefinition.tools list cannot be resolved.

AC-001, AC-004, AC-006
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from src.ai.registry.agent_registry import AgentRegistry
from src.ai.registry.exceptions import StartupValidationError
from src.ai.validators.workflow_structure_validator import (
    WorkflowStructureError,
    WorkflowStructureValidator,
)

if TYPE_CHECKING:
    from src.ai.tools.registry import ToolRegistry
    from src.ai.tools.logging import ToolCallLogger
    from ingestion.cache_or_fetch import CacheOrFetch

logger = logging.getLogger(__name__)


def build_tool_registry(
    cache_or_fetch: "CacheOrFetch",
    tool_logger: "ToolCallLogger",
) -> "ToolRegistry":
    """Instantiate all 16 tool classes and register them in a new ToolRegistry.

    Args:
        cache_or_fetch: The CacheOrFetch cascade instance from PLAN-F-032.
        tool_logger: The ToolCallLogger for DB + Langfuse writes.

    Returns:
        Populated ToolRegistry ready to be stored on app.state.
    """
    from src.ai.tools.registry import ToolRegistry
    from src.ai.tools.families.portfolio_context import (
        GetPortfolioPositions,
        GetWatchlist,
        GetScoringProfile,
    )
    from src.ai.tools.families.company_data import (
        GetCompanyFundamentals,
        GetCompanyScores,
        GetPriceHistory,
    )
    from src.ai.tools.families.events_history import (
        GetEventsByCompany,
        GetEventAnalogies,
        GetAiRecommendationHistory,
    )
    from src.ai.tools.families.exposure_correlation import (
        GetEventExposure,
        GetCompanyExposureHistory,
    )
    from src.ai.tools.families.macro_market import (
        GetMacroIndicators,
        GetSectorPerformance,
    )
    from src.ai.tools.families.memory_track_record import (
        GetSemanticFacts,
        GetProceduralPatterns,
        GetRecommendationOutcomes,
    )

    registry = ToolRegistry()
    tool_classes = [
        # Portfolio Context (3)
        GetPortfolioPositions,
        GetWatchlist,
        GetScoringProfile,
        # Company Data (3)
        GetCompanyFundamentals,
        GetCompanyScores,
        GetPriceHistory,
        # Events + History (3)
        GetEventsByCompany,
        GetEventAnalogies,
        GetAiRecommendationHistory,
        # Exposure + Correlation (2)
        GetEventExposure,
        GetCompanyExposureHistory,
        # Macro + Market (2)
        GetMacroIndicators,
        GetSectorPerformance,
        # Memory + Track Record (3)
        GetSemanticFacts,
        GetProceduralPatterns,
        GetRecommendationOutcomes,
    ]
    for cls in tool_classes:
        registry.register(cls(cache_or_fetch=cache_or_fetch, logger=tool_logger))

    return registry


def initialise_ai_module(
    agents_dir: Path,
    prompts_base_dir: Path | None = None,
    workflow_node_sequences: Sequence[list[str]] | None = None,
    cache_or_fetch: "CacheOrFetch | None" = None,
    tool_logger: "ToolCallLogger | None" = None,
) -> AgentRegistry:
    """Load and validate all agent definitions, workflow structures, and tools.

    Steps:
    1. Construct AgentRegistry from agents_dir — validates all YAML files
       and checks that every referenced prompt file exists.
    2. Run WorkflowStructureValidator against each supplied workflow node
       sequence (if any).
    3. If cache_or_fetch and tool_logger are provided, build ToolRegistry and
       verify every tool_name in every AgentDefinition.tools list resolves.
    4. Raise StartupValidationError listing all failures if any check fails.
    5. Return the validated AgentRegistry (ToolRegistry stored separately on
       app.state by the caller when using build_tool_registry directly).

    Args:
        agents_dir: Directory containing *.yaml agent definition files.
        prompts_base_dir: Root directory for resolving prompt file paths.
                          Defaults to agents_dir.parent.
        workflow_node_sequences: Optional list of node-name sequences to
                                  validate. Each list must end with
                                  ["evaluate_quality", "narrative_writer"].
        cache_or_fetch: Optional CacheOrFetch instance; when provided together
                        with tool_logger, all 16 tools are instantiated and
                        every AgentDefinition.tools entry is validated.
        tool_logger: Optional ToolCallLogger; required when cache_or_fetch
                     is provided.

    Returns:
        Validated AgentRegistry ready for injection into workflow nodes.

    Raises:
        StartupValidationError: If any YAML, prompt, workflow, or tool check fails.
    """
    base_dir = prompts_base_dir or agents_dir.parent
    failures: list[str] = []

    # Step 1: Load and validate agent definitions
    registry: AgentRegistry | None = None
    try:
        registry = AgentRegistry(agents_dir=agents_dir, base_dir=base_dir)
    except StartupValidationError as exc:
        failures.extend(exc.failures)

    # Step 2: Validate workflow structures
    if workflow_node_sequences:
        validator = WorkflowStructureValidator()
        for sequence in workflow_node_sequences:
            try:
                validator.validate(sequence)
            except WorkflowStructureError as exc:
                failures.append(str(exc))

    # Step 3: Validate ToolRegistry (if dependencies provided)
    if cache_or_fetch is not None and tool_logger is not None and registry is not None:
        from src.ai.tools.registry import ToolNotFoundError
        tool_registry = build_tool_registry(cache_or_fetch, tool_logger)
        for defn in registry.all_definitions():
            for tool_name in defn.tools:
                try:
                    tool_registry.resolve(tool_name)
                except ToolNotFoundError:
                    failures.append(
                        f"Agent {defn.role_id!r} references unknown tool {tool_name!r}"
                    )

    # Step 4: Fail fast if anything went wrong
    if failures:
        raise StartupValidationError(failures=failures)

    assert registry is not None  # guaranteed by the failure check above
    logger.info(
        "AI module initialised: %d agents registered",
        len(registry.all_definitions()),
    )
    return registry
