---
req_id: REQ-F-011
slug: agent-registry-and-definitions
title: Agent Registry and Definitions
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, agents, configuration]
  story_points:
  components: [ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Agent Registry and Definitions

## Domain Context
The agent system defines nine named-role agents that power all Mode B deliberative workflows. Each agent is defined in a YAML file at `agents/{role_id}.yaml`. Agent behaviour is data-driven and configurable without code changes. Anthropic-only models in MVP (C-003 resolved).

## Summary
The system must provide nine named-role agent YAML definitions covering all roles required by Mode B workflows, each specifying role_id, persona, system_prompt_file, model, tools, limits, confidence_threshold, and output_schema; the evaluate_quality node must always be second-to-last and Narrative Writer always last in every workflow.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 4–7, 21, 22, 27–30 and §Architecture Signals, agents are defined externally in YAML files. This decouples agent behaviour from code. The nine named roles (C-003 resolved — Anthropic-only):

1. **Relevance Analyst** (Sonnet 4.6) — filters events for portfolio/watchlist relevance
2. **Anomaly Detector** (Sonnet 4.6) — identifies unusual market movements
3. **Exposure Analyst** (Sonnet 4.6) — maps event exposures across portfolio
4. **Historical Context Agent** (Opus 4.7) — retrieves and interprets historical analogies; reused across all 5 workflows
5. **Recommendation Synthesizer** (Opus 4.7) — synthesizes action recommendations
6. **Earnings Context Agent** (Opus 4.7) — macro/sector scenario tree for earnings workflows
7. **Event Deep-Dive Agent** (Opus 4.7) — comprehensive single-event analysis, produces memo
8. **Narrative Writer** (Opus 4.7) — always last; produces final human-readable output
9. **Q&A Analyst** (Opus 4.7) — interactive Q&A, max_iterations=10; all others: 3–5

Each YAML definition includes:
- `role_id`: kebab-case identifier
- `persona`: character description for the agent
- `system_prompt_file`: path to the prompt file in `prompts/`
- `model`: provider, model_id, temperature, max_tokens
- `tools`: list of tool names (only those listed may be used — runtime-enforced)
- `limits`: max_input_tokens, max_iterations, timeout_seconds, cost_ceiling_usd
- `confidence_threshold`: float, configurable per workflow
- `output_schema`: JSON schema for structured output

Enforcement of "tools only as listed" must be runtime-verified, not convention-only.

## Desired Outcome
All Mode B workflows execute using consistently defined, version-controlled agent configurations that can be updated without code changes, with enforced tool and cost boundaries preventing runaway execution.

## Acceptance Criteria
- [ ] AC-001: Given the codebase, nine `agents/{role_id}.yaml` files exist, each containing all required fields (role_id, persona, system_prompt_file, model, tools, limits, confidence_threshold, output_schema).
- [ ] AC-002: Given a workflow executes an agent node, the agent can only invoke tools listed in its YAML `tools` field; an attempt to call an unlisted tool raises a runtime error and is logged.
- [ ] AC-003: Given an agent node execution, the system enforces max_input_tokens, max_iterations, timeout_seconds, and cost_ceiling_usd limits and terminates the node with a structured error when any limit is exceeded.
- [ ] AC-004: Given any workflow definition, evaluate_quality is the second-to-last node and Narrative Writer is the last node; workflow definitions violating this structural rule fail validation at startup.
- [ ] AC-005: Given the Q&A Analyst agent YAML, max_iterations is 10; all other agent YAMLs specify max_iterations in the range 3–5.
- [ ] AC-006: Given a model field in an agent YAML is changed (e.g. temperature adjusted), reloading the agent without redeploying code uses the updated configuration.

## Out of Scope
- Multi-provider LLM routing (Anthropic-only in MVP per C-003)
- Automatic agent discovery beyond the nine defined roles
- Tool implementation (covered by tool-library requirement)

## Data Models
```
AgentDefinition (YAML schema):
  role_id: string (kebab-case)
  persona: string
  system_prompt_file: string (path under prompts/)
  model:
    provider: string  # "anthropic" only in MVP
    model_id: string  # e.g. "claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"
    temperature: float
    max_tokens: int
  tools: string[]
  limits:
    max_input_tokens: int
    max_iterations: int  # Q&A Analyst: 10; others: 3-5
    timeout_seconds: int
    cost_ceiling_usd: float
  confidence_threshold: float
  output_schema: object (JSON Schema)
```

## Process Sequence
1. System startup loads all `agents/{role_id}.yaml` files and validates against schema
2. Workflow executor resolves agent by role_id at runtime
3. Agent node invoked with WorkflowState; limits registered with execution context
4. Tool calls validated against allowed tools list before execution
5. Limits enforced during execution; structured errors on violation
6. Output validated against output_schema before returning to WorkflowState

## Subtasks
- [ ] ST-001: Define YAML schema and loader with validation — complexity: M
- [ ] ST-002: Write all 9 agent YAML definition files — complexity: M
- [ ] ST-003: Implement runtime tool-call enforcement guard — complexity: M
- [ ] ST-004: Implement max_input_tokens, max_iterations, timeout_seconds, cost_ceiling_usd enforcement — complexity: M
- [ ] ST-005: Implement workflow structural validator (evaluate_quality second-to-last, Narrative Writer last) — complexity: S
- [ ] ST-006: Unit tests for limit enforcement, tool guard, schema validation — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 4-7, 21, 22, 27-30; §Architecture Signals; §Integration Points | Nine agents, YAML structure, tool enforcement, structural rules, model assignments |
