---
req_id: REQ-F-027
slug: qa-chat-interface
title: Q&A Chat Interface
type: functional
status: approved
complexity: M
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
  - ui-design-digest.md
dependencies:
  - { id: "", reason: "agent-registry-and-definitions: Q&A Analyst agent (Opus 4.7, max_iterations=10) must be defined" }
  - { id: "", reason: "tool-library: Q&A Analyst uses tools for portfolio and event data" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: Medium
  labels: [frontend, ai, qa, chat]
  story_points:
  components: [qa-chat, frontend, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Q&A Chat Interface

## Domain Context
The Q&A Chat interface allows users to ask questions about their portfolio and event archive. Scoped to user data only. Powered by the Q&A Analyst agent (Opus 4.7, max_iterations=10). Responses include sources and confidence per answer.

## Summary
The system must provide a Q&A chat interface where users ask questions scoped to their portfolio and event archive, powered by the Q&A Analyst agent (Opus 4.7, max_iterations=10), with responses showing cited sources and a confidence level per answer.

## Detailed Description
As specified in ui-design-digest.md business rule 34 and architectural-considerations-digest.md business rule 28 (Q&A Analyst supports max_iterations=10):

The Q&A Analyst agent is Opus 4.7 with max_iterations=10 (allowing more complex multi-step reasoning than other agents whose limit is 3–5). This higher iteration count accommodates multi-turn question decomposition.

Scope constraint: all tool calls are scoped to the user's portfolio companies and event archive. The Q&A Analyst cannot query data about companies outside the user's portfolio/watchlist without explicit expansion.

Every response includes:
- Answer text
- Sources: list of cited data points (event names, dates, document references)
- Confidence level (0–1)

Per-agent cost_ceiling_usd and timeout_seconds are enforced from the YAML definition. If the agent reaches its cost ceiling during a question, it returns a partial answer with a cost-limited flag.

## Desired Outcome
Users can ask natural language questions about their portfolio's geopolitical exposure and event history, receiving grounded, confidence-scored answers with cited sources within the agent's cost and iteration budget.

## Acceptance Criteria
- [ ] AC-001: Given a user submits a question about their portfolio, the Q&A Analyst agent runs with max_iterations=10 and returns an answer scoped to data accessible via the user's portfolio context tools.
- [ ] AC-002: Given the agent responds, the response includes: answer text, a list of cited sources (event IDs, dates, or data points), and a confidence score (0–1).
- [ ] AC-003: Given the agent reaches the cost_ceiling_usd or timeout_seconds limit from its YAML definition, the interface displays a partial answer with a "Cost limit reached" notice rather than an error.
- [ ] AC-004: Given a user asks a question about a company not in their portfolio, the system responds that the query is outside scope and suggests adding the company to their watchlist.
- [ ] AC-005: Given the Q&A conversation, each user question and agent response is stored in the episodic memory (Layer 1) workflow_run for audit purposes.

## Out of Scope
- Q&A about companies outside the user's portfolio/watchlist (unless scoped expansion is explicitly triggered)
- Autonomous actions from Q&A (read-only, no order placement)

## Data Models
```
QASession:
  session_id: UUID
  user_id: UUID
  tenant_id: UUID
  messages: list[QAMessage]
  workflow_run_id: UUID

QAMessage:
  role: enum(user, assistant)
  content: text
  sources: list[{type, id, description}] | null
  confidence: float | null
  cost_usd: float | null
```

## Process Sequence
1. User submits question via chat interface
2. New QASession or continuation of existing session
3. Q&A Analyst agent invoked with session context and user's portfolio scope
4. Agent uses up to 10 iterations, calling tools scoped to user portfolio
5. Agent produces answer with sources and confidence
6. Response rendered in chat UI with sources displayed
7. Session + messages persisted to episodic memory

## Subtasks
- [ ] ST-001: Implement Q&A session API (create session, send message, stream response) — complexity: M
- [ ] ST-002: Implement Q&A Analyst agent YAML (Opus 4.7, max_iterations=10, portfolio-scoped tools) — complexity: S
- [ ] ST-003: Implement frontend chat interface — complexity: M
- [ ] ST-004: Implement sources + confidence display in chat responses — complexity: S
- [ ] ST-005: Implement session persistence to episodic memory — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | Business Rules item 28; Integration Points (Q&A Analyst) | max_iterations=10, Opus 4.7 model |
| ui-design-digest.md | Business Rules item 34 | Portfolio + event archive scope, sources + confidence per response |
