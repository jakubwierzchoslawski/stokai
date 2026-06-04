---
req_id: REQ-F-014
slug: prompt-management-pipeline
title: Prompt Management Pipeline
type: functional
status: approved
complexity: L
tdd_required: true
source_docs:
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "evaluation-framework: Tier 2 golden dataset regression gates prompt promotion" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [backend, ai, prompts, devops]
  story_points:
  components: [prompt-management, ai-agents]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-F-??? — Prompt Management Pipeline

## Domain Context
Prompts are dual-homed: git is the source of truth (`prompts/*.md` with frontmatter), Langfuse is the runtime access layer. The promotion pipeline enforces quality gates. Rollback must be effective within seconds.

## Summary
The system must implement a prompt lifecycle from git source through Langfuse runtime access, with a structured promotion pipeline (Draft → PR → Review → Merge → Staging → Canary → Monitor → Promote), Tier 2 regression gate blocking promotion on >5% degradation, and rollback effective within seconds.

## Detailed Description
As specified in architectural-considerations-digest.md §Business Rules items 7–10, 23, 36 and §Architecture Signals, the prompt pipeline is:

1. **Draft**: Author writes `prompts/{agent_role}.md` with YAML frontmatter (version, agent, description)
2. **PR with Tier 2 regression run**: CI runs golden dataset regression; >5% degradation on any metric blocks merge
3. **Review**: Human review in PR
4. **Merge**: Merged to main; Langfuse staging label applied; prompt SHA recorded as Langfuse version label
5. **Staging label**: Langfuse serves the staging version to the staging environment
6. **Canary traffic**: Small percentage of production traffic routes to the new prompt version
7. **Tier 1 + 3 monitoring**: Online LLM-as-judge (Tier 1) and ex-post calibration (Tier 3) monitored for the canary cohort
8. **Promote**: Admin promotes to production in Langfuse; becomes the active version for all agents using that prompt

Rollback command: `stokai prompts rollback --agent <role_id> --to-version <sha>` — must take effect within seconds by updating the Langfuse active version without any code deploy.

Prompt SHA is used as the Langfuse version label, creating a direct traceability chain from git commit to runtime behaviour.

Every agent invocation records the prompt_version (SHA) used, enabling audit of which prompt version produced a given output.

## Desired Outcome
Prompt changes are safely tested before reaching production with zero possibility of a degraded prompt being promoted, and any production prompt can be reverted within seconds if issues emerge.

## Acceptance Criteria
- [ ] AC-001: Given a PR modifies a prompt file in `prompts/`, CI automatically runs the Tier 2 golden dataset regression; if degradation >5% on any metric, the PR is blocked from merge.
- [ ] AC-002: Given a prompt is merged and staged in Langfuse, agents in the staging environment use the staged prompt version (identified by git SHA) without any code changes.
- [ ] AC-003: Given `stokai prompts rollback --agent <role_id> --to-version <sha>` is executed, the active prompt version for that agent in Langfuse is updated and subsequent agent invocations use the rolled-back version within 60 seconds.
- [ ] AC-004: Given any agent invocation in production, the Langfuse trace for that invocation records the prompt_version (SHA) used, enabling reconstruction of which prompt produced which output.
- [ ] AC-005: Given the Tier 2 regression passes and the prompt reaches canary, Tier 1 and Tier 3 monitoring metrics are visible in the admin AI audit console for the canary cohort.

## Out of Scope
- Automatic canary promotion (human approval required for production promotion)
- A/B testing infrastructure beyond single canary cohort

## Open Questions
| # | Question | Source of Ambiguity | Raised | Resolved |
|---|----------|--------------------|--------|----------|
| 1 | What canary traffic percentage and duration are used before promotion is eligible? No document specifies these parameters. | root-synthesis §Ambiguities Detected: "Canary traffic percentage and duration for prompt promotion are not defined" | 2026-06-02 | ☐ |

## Data Models
```
Prompt file (git):
  ---
  version: git SHA (assigned by git)
  agent: role_id
  description: string
  ---
  {prompt text}

PromptVersion (Langfuse-backed):
  version_id: string (git SHA)
  agent_role: string
  content: text
  quality_metrics: JSONB
  active_from: timestamp
  rolled_back_at: timestamp | null
  environment: enum(staging, canary, production)
```

## Process Sequence
1. Author creates/edits `prompts/{role}.md` in a git branch
2. CI runs Tier 2 golden dataset regression on PR
3. If >5% degradation: PR blocked; author must revise
4. Human review and approval in PR
5. Merge to main; Langfuse staging label applied with git SHA
6. Staging environment validates prompt behaviour
7. Admin enables canary routing in Langfuse
8. Tier 1 + Tier 3 monitoring tracked for canary cohort
9. Admin promotes to production via Langfuse UI / `stokai prompts promote` command
10. Rollback at any time via `stokai prompts rollback` command

## Subtasks
- [ ] ST-001: Define `prompts/` directory structure and frontmatter schema — complexity: S
- [ ] ST-002: Implement CI step for Tier 2 regression on prompt PR — complexity: M
- [ ] ST-003: Implement Langfuse integration for staging/canary/production label management — complexity: M
- [ ] ST-004: Implement `stokai prompts rollback` CLI command with <60 s SLA — complexity: M
- [ ] ST-005: Implement prompt SHA recording in every agent invocation trace — complexity: S
- [ ] ST-006: Integration tests for rollback speed and regression gate block — complexity: M

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| architectural-considerations-digest.md | §Business Rules items 7-10, 23, 36; §Architecture Signals | Dual-homed git+Langfuse, full promotion pipeline, rollback command, SHA version label |
