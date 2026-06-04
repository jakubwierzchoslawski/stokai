---
plan_id: PLAN-F-011
slug: agent-registry-and-definitions
title: Agent Registry and Definitions
linked_requirement: REQ-F-011
type: functional
status: done
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-003, reason: "per-agent cost_ceiling_usd enforced in agent YAML and at runtime" }
  - { id: REQ-N-004, reason: "per-agent cost_ceiling_usd also caps Mode B per-report spend" }
  - { id: REQ-N-008, reason: "every agent invocation logs prompt_version (git SHA) to Langfuse" }
dependencies: []
executed_at: 2026-06-03T00:00:00Z
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-011 — Agent Registry and Definitions

## Linked Requirement
**REQ-F-011** — Agent Registry and Definitions
Status: approved | Jira:

## Objective
Build the foundational agent layer for Mode B deliberative workflows. This plan introduces: (1) nine YAML definition files under `agents/` that declare every named-role agent without requiring code changes to reconfigure them; (2) nine system-prompt files under `prompts/agents/`; (3) a Pydantic-validated `AgentDefinition` data model and `AgentRegistry` class that loads, validates, and resolves agents by `role_id` at startup; (4) a runtime `ToolGuard` that rejects any tool call not listed in an agent's YAML before it reaches the LLM; (5) an `ExecutionLimiter` that enforces `max_input_tokens`, `max_iterations`, `timeout_seconds`, and `cost_ceiling_usd` and terminates nodes with a structured `LimitExceededError`; (6) a `WorkflowStructureValidator` that verifies the `evaluate_quality → narrative_writer` tail invariant on every workflow graph before execution; and (7) a Langfuse decorator that attaches `prompt_version` (git SHA) to every agent-invocation span. All model names, tool lists, and limits are read exclusively from YAML — no hardcoded values anywhere in the Python code.

## Architecture Context
This plan operates entirely within the `ai` backend module (Architecture §5 and §7). It introduces the `src/ai/` package and its sub-packages. It does not touch any other module directly but establishes the interfaces that `src/ai/` will expose to all Mode B workflow graphs (Architecture §7.1–7.2). The `AgentRegistry` is the single source of truth for all agent configuration at runtime — workflow nodes call `registry.resolve(role_id)` to obtain a validated `AgentDefinition`. The `ToolGuard` wraps every `AgentNode` before it is handed to the LangGraph graph (Architecture §7.1 bounded execution). The `WorkflowStructureValidator` runs at startup alongside schema validation, preventing misconfigured workflow graphs from ever reaching production (Architecture §7.1 cross-workflow invariants). Langfuse observability (Architecture §12.4) is wired here via an invocation decorator so every downstream workflow automatically carries `prompt_version`.

## Applied NFR Constraints
| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-003 | Per-agent `cost_ceiling_usd` must be enforced | `ExecutionLimiter` reads the ceiling from `AgentDefinition.limits.cost_ceiling_usd` and raises `LimitExceededError` when accumulated spend reaches the ceiling during a node execution |
| REQ-N-004 | Per-report cost ceiling is the sum of per-agent ceilings | `AgentDefinition.limits.cost_ceiling_usd` values are designed so the sum across agents in one workflow does not exceed the per-workflow ceiling; this plan documents the ceiling budget allocation in the YAML files |
| REQ-N-008 | Every agent invocation logs `prompt_version` (git SHA) to Langfuse | `LangfuseInvocationLogger` decorator resolves the git SHA of the system-prompt file at invocation time and records it as `prompt_version` on the Langfuse span |

## Component Design

### New Components
```
Package: src/ai/
  ├── __init__.py
  ├── registry/
  │   ├── __init__.py
  │   ├── agent_definition.py       — Pydantic AgentDefinition model and sub-models
  │   ├── agent_registry.py         — AgentRegistry class (IAgentRegistry interface + impl)
  │   └── interfaces.py             — IAgentRegistry protocol
  ├── guards/
  │   ├── __init__.py
  │   └── tool_guard.py             — ToolGuard (validates tool calls against YAML allowlist)
  ├── limits/
  │   ├── __init__.py
  │   ├── execution_limiter.py      — ExecutionLimiter (token / iteration / timeout / cost)
  │   └── errors.py                 — LimitExceededError (structured), LimitType enum
  ├── observability/
  │   ├── __init__.py
  │   └── langfuse_invocation_logger.py  — decorator: attaches prompt_version to Langfuse span
  └── validators/
      ├── __init__.py
      └── workflow_structure_validator.py — WorkflowStructureValidator

Configuration files (not Python code):
agents/
  relevance-analyst.yaml
  anomaly-detector.yaml
  exposure-analyst.yaml
  historical-context-agent.yaml
  recommendation-synthesizer.yaml
  narrative-writer.yaml
  earnings-context-agent.yaml
  event-deep-dive-agent.yaml
  qa-analyst.yaml

Prompt stubs (Markdown, minimal placeholder for MVP):
prompts/agents/
  relevance_analyst.md
  anomaly_detector.md
  exposure_analyst.md
  historical_context_agent.md
  recommendation_synthesizer.md
  narrative_writer.md
  earnings_context_agent.md
  event_deep_dive_agent.md
  qa_analyst.md

Tests:
tests/unit/ai/
  test_agent_definition.py
  test_agent_registry.py
  test_tool_guard.py
  test_execution_limiter.py
  test_workflow_structure_validator.py
  test_langfuse_invocation_logger.py
```

### Modified Components
| File | Change | Reason |
|------|--------|--------|
| `src/config/settings.py` | Add `AGENTS_DIR: str` and `PROMPTS_DIR: str` settings (loaded from env) | Registry must resolve paths from config, never from hardcoded strings |

### Interfaces and Contracts
The executor must implement these exactly.

```python
# src/ai/registry/interfaces.py

from typing import Protocol
from src.ai.registry.agent_definition import AgentDefinition

class IAgentRegistry(Protocol):
    def resolve(self, role_id: str) -> AgentDefinition:
        """Return the validated AgentDefinition for role_id.
        Raises AgentNotFoundError if role_id is not registered."""
        ...

    def all_definitions(self) -> list[AgentDefinition]:
        """Return all loaded AgentDefinition objects."""
        ...
```

```python
# src/ai/registry/agent_definition.py  (key Pydantic models)

from pydantic import BaseModel, Field, field_validator
from typing import Any

class ModelConfig(BaseModel):
    provider: str                    # "anthropic" only in MVP
    model_id: str                    # e.g. "claude-sonnet-4-6"
    temperature: float = Field(ge=0.0, le=1.0)
    max_tokens: int = Field(gt=0)

class AgentLimits(BaseModel):
    max_input_tokens: int = Field(gt=0)
    max_iterations: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    cost_ceiling_usd: float = Field(gt=0.0)

class AgentDefinition(BaseModel):
    role_id: str                          # kebab-case, e.g. "relevance-analyst"
    persona: str
    system_prompt_file: str               # relative path under prompts/
    model: ModelConfig
    tools: list[str]                      # only these tool names may be called
    limits: AgentLimits
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    output_schema: dict[str, Any]         # JSON Schema object

    @field_validator("role_id")
    @classmethod
    def role_id_must_be_kebab_case(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"[a-z][a-z0-9-]*", v):
            raise ValueError(f"role_id must be kebab-case, got: {v!r}")
        return v
```

```python
# src/ai/limits/errors.py

from enum import Enum

class LimitType(str, Enum):
    MAX_INPUT_TOKENS = "max_input_tokens"
    MAX_ITERATIONS   = "max_iterations"
    TIMEOUT          = "timeout_seconds"
    COST_CEILING     = "cost_ceiling_usd"

class LimitExceededError(Exception):
    def __init__(self, limit_type: LimitType, limit_value: float, actual_value: float,
                 agent_role_id: str) -> None:
        self.limit_type   = limit_type
        self.limit_value  = limit_value
        self.actual_value = actual_value
        self.agent_role_id = agent_role_id
        super().__init__(
            f"Agent {agent_role_id!r} exceeded {limit_type}: "
            f"limit={limit_value}, actual={actual_value}"
        )
```

```python
# src/ai/guards/tool_guard.py

class ToolGuard:
    """Validates that a requested tool name is in the agent's allowed-tools list."""

    def __init__(self, allowed_tools: list[str]) -> None:
        self._allowed: frozenset[str] = frozenset(allowed_tools)

    def assert_allowed(self, tool_name: str) -> None:
        """Raise ToolNotAllowedError if tool_name is not in the allowlist."""
        if tool_name not in self._allowed:
            raise ToolNotAllowedError(tool_name, sorted(self._allowed))

class ToolNotAllowedError(RuntimeError):
    def __init__(self, tool_name: str, allowed: list[str]) -> None:
        self.tool_name = tool_name
        self.allowed   = allowed
        super().__init__(
            f"Tool {tool_name!r} is not in the agent's allowed-tools list: {allowed}"
        )
```

---

## Implementation Tasks

### TASK-001: AgentDefinition Pydantic model and YAML schema · M/TDD · agents/relevance-analyst.yaml,agents/anomaly-detector.yaml,agents/exposure-analyst.yaml,agents/historical-context-agent.yaml,agents/recommendation-synthesizer.yaml,agents/narrative-writer.yaml,agents/earnings-context-agent.yaml,agents/event-deep-dive-agent.yaml,agents/qa-analyst.yaml,src/ai/registry/agent_definition.py,src/ai/registry/__init__.py,src/ai/__init__.py,tests/unit/ai/test_agent_definition.py

Define the `AgentDefinition` Pydantic v2 model with all required sub-models (`ModelConfig`, `AgentLimits`). Implement YAML-to-model parsing using PyYAML. The model must reject any YAML that is missing required fields, has an invalid `role_id` format (not kebab-case), sets `provider` to anything other than `"anthropic"`, or specifies a `max_iterations` value outside the allowed range (Q&A Analyst: 10; all others: 3–5). Write the `load_agent_definition(path: Path) -> AgentDefinition` pure function that loads and validates one YAML file. The output_schema field stores the raw JSON Schema dict from the YAML `output_schema` key with no further validation at this layer (schema validation against outputs is handled by the execution layer).

**Tests to write first (TDD):**
- `test_valid_yaml_loads_to_agent_definition` — loads a minimal valid YAML and asserts all fields are present
- `test_missing_required_field_raises_validation_error` — each of: role_id, persona, system_prompt_file, model, tools, limits, confidence_threshold, output_schema
- `test_invalid_role_id_format_raises_validation_error` — role_id `"RelevanceAnalyst"` (PascalCase) must fail
- `test_non_anthropic_provider_raises_validation_error` — provider `"openai"` must fail
- `test_temperature_out_of_range_raises_validation_error` — temperature 1.5 must fail
- `test_cost_ceiling_must_be_positive` — 0.0 must fail
- `test_confidence_threshold_bounds` — 0.0 and 1.0 are valid; 1.1 must fail

**AC covered**: AC-001, AC-005

---

### TASK-002: Nine agent YAML definition files · S/no-TDD · agents/relevance-analyst.yaml,agents/anomaly-detector.yaml,agents/exposure-analyst.yaml,agents/historical-context-agent.yaml,agents/recommendation-synthesizer.yaml,agents/narrative-writer.yaml,agents/earnings-context-agent.yaml,agents/event-deep-dive-agent.yaml,agents/qa-analyst.yaml

Write all nine `agents/{role_id}.yaml` files. Each file must include all required fields. Model assignments follow D6 exactly: `relevance-analyst`, `anomaly-detector`, and `exposure-analyst` use `claude-sonnet-4-6`; the remaining six use `claude-opus-4-7`. The `qa-analyst` YAML must set `max_iterations: 10`. All other agents must set `max_iterations` to a value in [3, 5]. Tools lists must enumerate only the tool names each agent is authorized to use (drawn from Architecture §7.3). Each file includes a representative `output_schema` JSON Schema block. The `system_prompt_file` field in each YAML points to `prompts/agents/{snake_case_role_id}.md`. No model name, tool name, or limit value may appear anywhere in Python source code — all values come from these files.

**AC covered**: AC-001, AC-005, AC-006

---

### TASK-003: Nine system-prompt stub files · XS/no-TDD · prompts/agents/relevance_analyst.md,prompts/agents/anomaly_detector.md,prompts/agents/exposure_analyst.md,prompts/agents/historical_context_agent.md,prompts/agents/recommendation_synthesizer.md,prompts/agents/narrative_writer.md,prompts/agents/earnings_context_agent.md,prompts/agents/event_deep_dive_agent.md,prompts/agents/qa_analyst.md

Create the nine Markdown prompt files referenced by the YAML definitions. Each file must contain: (1) a one-paragraph persona section matching the `persona` field in the corresponding YAML; (2) a numbered task description section; (3) a structured-output instruction section specifying that the agent must respond with a JSON object conforming to the `output_schema`. These are MVP stubs — content quality is intentionally minimal; the prompt pipeline (PLAN-F-014) will manage production-quality versions. The files must exist and be non-empty so the `AgentRegistry` file-existence check passes at startup.

**AC covered**: AC-001

---

### TASK-004: AgentRegistry class · M/TDD · src/ai/registry/agent_registry.py,src/ai/registry/interfaces.py,src/config/settings.py,tests/unit/ai/test_agent_registry.py

Implement `AgentRegistry` behind the `IAgentRegistry` protocol. `AgentRegistry.__init__(agents_dir: Path)` discovers all `*.yaml` files under `agents_dir`, calls `load_agent_definition` for each, and populates an internal `dict[str, AgentDefinition]`. It also verifies that each `system_prompt_file` path exists on disk; if any file is missing, the registry raises `StartupValidationError` with the missing paths listed. `resolve(role_id: str)` does a dict lookup by `role_id` and raises `AgentNotFoundError` if the key is absent. `all_definitions()` returns the full list. The registry is instantiated once at application startup and injected wherever needed — it is never constructed inside a workflow node. Add `AGENTS_DIR` and `PROMPTS_DIR` env-var settings to `src/config/settings.py`.

**Tests to write first (TDD):**
- `test_registry_loads_all_nine_agents` — given a temp directory with nine valid YAMLs, asserts `len(registry.all_definitions()) == 9`
- `test_resolve_returns_correct_definition` — resolve by role_id returns the matching definition
- `test_resolve_unknown_role_id_raises_agent_not_found_error`
- `test_missing_prompt_file_raises_startup_validation_error` — YAML references a non-existent prompt path
- `test_registry_rejects_directory_with_invalid_yaml` — a YAML with a missing required field raises `StartupValidationError`

**AC covered**: AC-001, AC-006

---

### TASK-005: ToolGuard — runtime tool-call enforcement · M/TDD · src/ai/guards/tool_guard.py,src/ai/guards/__init__.py,tests/unit/ai/test_tool_guard.py

Implement `ToolGuard` with an `assert_allowed(tool_name: str) -> None` method. Raise `ToolNotAllowedError(tool_name, sorted(allowed_tools))` when the tool is not in the frozenset of allowed names. The error must be logged at `ERROR` level using Python's structured logger before being re-raised, so that every blocked tool call produces an observable log entry. `ToolGuard` is instantiated per-agent from `AgentDefinition.tools`. It is injected into any `AgentNode` wrapper (defined in PLAN-F-012) — this task defines only the guard itself, not the LangGraph node wrapper. The guard must be pure (no side-effects beyond the log entry) so it is trivially unit-testable without a running LangGraph graph.

**Tests to write first (TDD):**
- `test_allowed_tool_does_not_raise` — a tool in the list passes silently
- `test_disallowed_tool_raises_tool_not_allowed_error` — tool not in list raises with correct attributes
- `test_error_includes_allowed_tools_list` — the exception `.allowed` attribute lists all permitted tools
- `test_guard_is_case_sensitive` — `"GetPortfolio"` is not the same as `"get_portfolio"`
- `test_empty_tools_list_blocks_all_tool_calls` — an agent with `tools: []` must block every call

**AC covered**: AC-002

---

### TASK-006: ExecutionLimiter — max_input_tokens, max_iterations, timeout, cost_ceiling · M/TDD · src/ai/limits/execution_limiter.py,src/ai/limits/errors.py,src/ai/limits/__init__.py,tests/unit/ai/test_execution_limiter.py

Implement `ExecutionLimiter` which accepts an `AgentLimits` instance and exposes four check methods: `check_input_tokens(count: int)`, `check_iteration(current: int)`, `check_elapsed(elapsed_seconds: float)`, and `check_cost(accumulated_usd: float)`. Each method raises `LimitExceededError(limit_type, limit_value, actual_value, agent_role_id)` when the actual value reaches or exceeds the configured limit. The limiter is stateless (callers track state); it only computes comparisons and raises. All four `LimitType` enum members from `errors.py` must map to a specific method so call sites are unambiguous. The timeout check compares `elapsed_seconds` to `AgentLimits.timeout_seconds` and is designed to be called from an `asyncio.wait_for` wrapper in the node executor. `LimitExceededError` must be JSON-serializable (implement `__dict__` or a `.to_dict()` method) so the workflow routing logic can attach it to the `WorkflowState.hil_reason` field without crashing serialization.

**Tests to write first (TDD):**
- `test_check_input_tokens_under_limit_passes`
- `test_check_input_tokens_at_limit_raises_limit_exceeded_error`
- `test_check_iteration_over_limit_raises`
- `test_check_elapsed_over_timeout_raises`
- `test_check_cost_at_ceiling_raises`
- `test_limit_exceeded_error_is_json_serializable` — `json.dumps(err.to_dict())` must not raise
- `test_limit_exceeded_error_includes_agent_role_id`

**AC covered**: AC-003

---

### TASK-007: WorkflowStructureValidator — evaluate_quality second-to-last, narrative_writer last · S/no-TDD · src/ai/validators/workflow_structure_validator.py,src/ai/validators/__init__.py

Implement `WorkflowStructureValidator` with a single method `validate(node_sequence: list[str]) -> None`. It asserts that the sequence ends with `["evaluate_quality", "narrative_writer"]` (in that order, no other nodes after). Raise `WorkflowStructureError` if the invariant is violated. The validator accepts a `list[str]` of node names in execution order; it has no dependency on LangGraph internals so it can be called synchronously at startup, before any Celery worker picks up a workflow task. Each workflow graph builder (PLAN-F-006 through PLAN-F-010) must call this validator during graph construction. Tests are light (S complexity) because the logic is a simple sequence check.

**AC covered**: AC-004

---

### TASK-008: LangfuseInvocationLogger — prompt_version (git SHA) on every agent span · M/TDD · src/ai/observability/langfuse_invocation_logger.py,src/ai/observability/__init__.py,tests/unit/ai/test_langfuse_invocation_logger.py

Implement `LangfuseInvocationLogger` as a context-manager decorator class. On entry it: (1) resolves the git SHA of `AgentDefinition.system_prompt_file` using `subprocess.run(["git", "log", "-1", "--format=%H", "<path>"])` — falls back to `"unknown"` if git is unavailable; (2) opens a Langfuse span with metadata `agent_role_id`, `model_id`, `prompt_version` (git SHA), `workflow_id`, `tenant_id`; (3) stores the span on the context. On exit it records `cost_usd`, `input_tokens`, `output_tokens`, `confidence`, `latency_ms`, and closes the span. Langfuse client is injected as a constructor argument — never instantiated inside the decorator — so tests can substitute a mock without patching globals. In the case where `LANGFUSE_HOST` is not configured (local dev / unit tests), the logger must no-op silently rather than crash.

**Tests to write first (TDD):**
- `test_logger_calls_langfuse_span_with_prompt_version` — mock Langfuse client; assert span is opened with `prompt_version` set to a non-empty string
- `test_logger_records_cost_and_tokens_on_exit` — assert mock span receives `cost_usd` and token counts on close
- `test_logger_no_ops_when_langfuse_client_is_none` — no exception raised when client is `None`
- `test_prompt_version_falls_back_to_unknown_when_git_unavailable` — patch `subprocess.run` to raise `FileNotFoundError`; assert `prompt_version == "unknown"`

**AC covered**: AC-001 (observability completeness per NFR-008)

---

### TASK-009: Startup integration — registry and validators wired into FastAPI lifespan · S/no-TDD · src/ai/startup.py,src/config/settings.py

Write `initialise_ai_module(settings: Settings) -> AgentRegistry` which: (1) constructs `AgentRegistry(agents_dir=Path(settings.AGENTS_DIR))`; (2) calls `WorkflowStructureValidator` against each registered workflow's declared node sequence; (3) raises `StartupValidationError` listing all failures if any check fails; (4) returns the validated registry. Wire this function into the FastAPI `lifespan` context manager so the application process fails fast at startup if any agent YAML is invalid, any prompt file is missing, or any workflow violates the structural invariant. The registry instance is stored in `app.state.agent_registry` for injection into route handlers and Celery tasks.

**AC covered**: AC-001, AC-004, AC-006

---

## Acceptance Criteria Coverage

- AC-001: Nine `agents/{role_id}.yaml` files exist with all required fields validated by `AgentDefinition` → TASK-001, TASK-002, TASK-003, TASK-004, TASK-009
- AC-002: Agent nodes can only invoke tools listed in their YAML; unlisted tool calls raise `ToolNotAllowedError` and are logged → TASK-005
- AC-003: `max_input_tokens`, `max_iterations`, `timeout_seconds`, and `cost_ceiling_usd` are enforced; violations raise `LimitExceededError` → TASK-006
- AC-004: `evaluate_quality` is second-to-last and `narrative_writer` is last; violation detected at startup by `WorkflowStructureValidator` → TASK-007, TASK-009
- AC-005: Q&A Analyst YAML has `max_iterations: 10`; all others have 3–5 (validated by `AgentDefinition` field validator) → TASK-001, TASK-002
- AC-006: Changing a model field in YAML and reloading the registry (without code redeploy) reflects the update; `AgentRegistry` reloads from disk on each `initialise_ai_module` call → TASK-004, TASK-009

## Risks and Notes
- The `WorkflowStructureValidator` in TASK-007 receives a `list[str]` of node names. Workflow graphs (PLAN-F-006 through PLAN-F-010) must expose a `node_sequence()` method that returns this list. The interface contract must be established before those plans are executed — the present plan documents the expected method name so future plan-workers align.
- Git SHA resolution in TASK-008 calls a subprocess. On CI runners or Docker environments without a `.git` directory, this will return `"unknown"`. That is acceptable and tested. The Langfuse span is still created and all other metadata is recorded.
- The `AgentDefinition.output_schema` field stores raw JSON Schema dicts. Schema validation of actual agent outputs against this dict (using `jsonschema.validate`) is deferred to the LangGraph node executor, which is part of PLAN-F-012 (Agent Tool Library). TASK-001 does not implement output validation — it only stores the schema.
- Nine YAML files and nine prompt stubs are pure data. If a future requirement changes any agent's model or tools, the YAML file is edited and the service is restarted — no code review is required for the Python layer. However, a PR touching `agents/` YAML files should include a Tier 2 golden dataset run (PLAN-F-016) as a gate.
- `cost_ceiling_usd` values in the YAML files must be chosen so the sum across all agents in a single workflow run stays within the per-workflow ceiling (REQ-N-004). The YAML files should include comments documenting the per-workflow budget allocation to make this constraint visible to future editors.
