---
req_id: REQ-N-008
slug: n-ai-observability
title: AI Observability via Langfuse
type: non-functional
nfr_category: Observability
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "four-layer-memory-subsystem: AI reasoning steps stored to DB as part of episodic memory" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, observability, langfuse, ai]
  story_points:
  components: [observability, langfuse]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — AI Observability via Langfuse

## Domain Context
Langfuse self-hosted is mandatory from Phase 4. Every workflow run must produce one hierarchical trace. All AI reasoning steps stored to DB for audit. Prompt SHA recorded as Langfuse version label for traceability.

## Summary
Every Mode A and Mode B workflow run must produce one hierarchical Langfuse trace capturing all agent invocations, tool calls, prompt versions, model used, confidence, cost, and latency. AI reasoning steps must be stored in the database for audit. Langfuse is self-hosted (PostgreSQL + Clickhouse).

## Detailed Description
As specified in architectural-considerations-digest.md non-functional signals and architecture signals:

**Langfuse self-hosted:** Langfuse runs as a self-hosted service (PostgreSQL + Clickhouse backend) from day one. No LangSmith or external observability SaaS dependency.

**Hierarchical trace structure per workflow run:**
- Trace root: workflow_id, workflow_type, tenant_id, user_id
- Span per agent invocation: agent_role, model, prompt_version (SHA), input_tokens, output_tokens, cost_usd, latency_ms, confidence
- Span per tool call: tool_name, args_hash, result_rows, cached, latency_ms, error_type
- Span per LLM call (within agents): model, prompt, completion, tokens, cost

**DB storage (audit):** Every agent invocation and tool call row is also written to PostgreSQL (agent_invocation, tool_call tables in Layer 1 episodic memory), enabling replay and audit independent of Langfuse.

**Prompt version traceability:** prompt SHA is recorded on every agent invocation span, creating a direct chain from production behaviour to the git commit that produced the prompt.

## Desired Outcome
Every AI decision can be traced from final output back through each agent's reasoning steps, tool calls, and prompt version used, enabling complete audit, debugging, and the admin replay capability.

## Acceptance Criteria
- [ ] AC-001: Given any Mode A or Mode B workflow run, a Langfuse trace exists with a root span for the workflow and child spans for each agent invocation and tool call, all linked by the same workflow_id.
- [ ] AC-002: Given any agent invocation span in Langfuse, it records: agent_role, model_id, prompt_version (git SHA), input_tokens, output_tokens, cost_usd, latency_ms, and confidence.
- [ ] AC-003: Given any agent invocation, a corresponding agent_invocation row is present in PostgreSQL with matching workflow_run_id, agent_role, prompt_version, and cost_usd.
- [ ] AC-004: Given the Langfuse self-hosted service is started via Docker Compose, it is accessible on its configured port and accepts trace writes from the application without any external SaaS dependency.

## Out of Scope
- LangSmith or other hosted observability SaaS
- Application performance monitoring (APM) for non-AI components

## NFR-Specific Fields

### Measurable Target
- 100% of workflow runs produce at least one Langfuse trace with all required spans (verified via Langfuse trace count = workflow_run count over 24-hour windows)
- 0 workflow runs with missing agent_invocation rows in PostgreSQL (Layer 1 completeness)
- Langfuse self-hosted: deployed without external network dependency beyond Docker Compose

### Verification Method
- Method: Automated test asserting Langfuse trace existence after each workflow execution; DB row count assertions for agent_invocation
- Tool/Process: pytest integration tests querying Langfuse API + PostgreSQL; Langfuse UI completeness review
- Frequency: Per release; continuous sampling in production
- Owner: DevOps / QA

### Category Rationale
Observability NFR because the admin audit console, HIL queue, and continuous improvement loop all depend on complete AI reasoning traces. Missing traces break the audit and improvement feedback cycles.

## Subtasks
- [ ] ST-001: Set up self-hosted Langfuse Docker Compose service (PostgreSQL + Clickhouse) — complexity: M
- [ ] ST-002: Implement Langfuse trace creation per workflow run — complexity: M
- [ ] ST-003: Implement child span creation per agent invocation and tool call — complexity: M
- [ ] ST-004: Implement prompt SHA recording on agent invocation spans — complexity: S
- [ ] ST-005: Integration tests asserting trace completeness — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Non-Functional Signals; Architecture Signals; Integration Points | Langfuse self-hosted, hierarchical traces, prompt SHA as version label, PostgreSQL + Clickhouse |
