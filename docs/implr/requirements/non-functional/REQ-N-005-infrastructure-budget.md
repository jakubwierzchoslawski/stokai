---
req_id: REQ-N-005
slug: n-infrastructure-budget
title: MVP Infrastructure and AI Total Budget
type: non-functional
nfr_category: Reliability
status: approved
complexity: S
tdd_required: false
source_docs:
  - system-description-digest.md
  - architectural-considerations-digest.md
dependencies:
  - { id: "", reason: "n-mode-a-cost: Mode A costs contribute to total budget" }
  - { id: "", reason: "n-mode-b-cost: Mode B costs contribute to total budget" }
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [infrastructure, cost, budget]
  story_points:
  components: [infrastructure, cost-management]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — MVP Infrastructure and AI Total Budget

## Domain Context
Resolved contradiction C-002: AI + infrastructure combined must be less than $100/month total for MVP. Architecture and technology choices must be validated against this hard budget constraint.

## Summary
The combined total of all AI API costs and infrastructure costs for the MVP must remain below $100/month. The admin cost monitor must track actual spend against this threshold and alert when approaching the limit.

## Detailed Description
Contradiction C-002 is resolved: the total MVP cost target is AI + infrastructure combined < $100/month. This supersedes both the $430–520/month estimate and the $268/month estimate from the source documents.

Technology choices enabling this budget:
- Anthropic Haiku 4.5 for high-volume classification (lowest cost per call)
- Self-hosted Langfuse (eliminates enterprise SaaS licensing)
- Docker-based self-hosting option eliminates managed cloud costs where applicable
- Aggressive cache-or-fetch reduces external API calls to the minimum
- Twitter/X off by default (avoids paid tier costs)
- GDELT free tier for ongoing events (commercial license for historical seeding)

The admin cost monitor tracks: AI API costs (Anthropic per model, OpenAI embedding), infrastructure costs (hosting, Redis, PostgreSQL if managed), broken down by source/model/workflow.

## Desired Outcome
The system operates within a $100/month total budget for MVP, making it viable for individual operators and small teams without enterprise infrastructure spend.

## Acceptance Criteria
- [ ] AC-001: Given 30 days of production operation at expected MVP load, the total combined AI + infrastructure cost is documented as < $100.
- [ ] AC-002: Given the admin cost monitor, it displays a breakdown of AI costs by model (Haiku/Sonnet/Opus/OpenAI embedding) and infrastructure costs, with a visual indicator showing current month spend vs $100 threshold.
- [ ] AC-003: Given total spend reaches 80% of $100/month ($80), the admin receives an alert notification.

## Out of Scope
- Multi-tenant cost allocation (single MVP deployment)
- Enterprise pricing or team licensing costs

## NFR-Specific Fields

### Measurable Target
- Total AI + infrastructure spend: < $100/month for MVP deployment
- Alert threshold: $80/month (80% of budget)
- Hard limit: $100/month (system operational alert; no automatic shutdown)

### Verification Method
- Method: Monthly cost audit from admin cost monitor dashboard; invoice review
- Tool/Process: Admin cost monitor with per-source/model/workflow breakdown; Anthropic API usage dashboard; cloud hosting invoices
- Frequency: Weekly cost review; monthly audit
- Owner: DevOps / Product Owner

### Category Rationale
Reliability NFR because exceeding budget makes the MVP economically unsustainable. Budget compliance is a constraint on architecture decisions throughout development.

## Subtasks
- [ ] ST-001: Configure admin cost monitor to aggregate AI + infrastructure costs — complexity: S
- [ ] ST-002: Set up $80/month alert threshold notification — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Non-Functional Signals | MVP infrastructure cost target (C-002 resolved to <$100/month) |
| architectural-considerations-digest.md | Non-Functional Signals | AI cost projections; self-hosted Langfuse as cost driver |
