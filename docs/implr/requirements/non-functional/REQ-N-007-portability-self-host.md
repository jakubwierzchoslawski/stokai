---
req_id: REQ-N-007
slug: n-portability-self-host
title: Portability and Self-Hostability
type: non-functional
nfr_category: Reliability
status: approved
complexity: M
tdd_required: true
source_docs:
  - system-description-digest.md
dependencies: []
superseded_by:
jira:
  id:
  issue_type: Story
  epic_link:
  priority: High
  labels: [infrastructure, portability, docker, devops]
  story_points:
  components: [infrastructure, devops]
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# REQ-N-??? — Portability and Self-Hostability

## Domain Context
No hard Azure lock-in. Replacing managed Azure services with containerized equivalents must require only environment variable changes and `docker compose up`. 12-factor app compliance ensures clean separation of config from code.

## Summary
The entire system must be deployable via `docker compose up` with only environment variable changes to switch from cloud-managed services to self-hosted containers. No Azure-specific SDKs may be called directly from business logic. 12-factor app compliance required.

## Detailed Description
As specified in system-description-digest.md non-functional signals and architecture signals:

**Docker Compose parity:** Every service (API, Celery workers, PostgreSQL + TimescaleDB + pgvector, Redis, Langfuse, Clickhouse) has a container definition. `docker compose up` on a fresh machine with an `.env` file starts the full stack.

**No Azure SDK lock-in:** Business logic layers must not import Azure-specific SDKs (azure-core, azure-identity, etc.). Cloud services are accessed via provider adapter interfaces only. Switching from Azure DB for PostgreSQL to a self-hosted PostgreSQL container requires only environment variable change.

**12-factor app compliance:**
- Configuration in environment variables (never hardcoded)
- Dependencies explicitly declared
- Dev/prod parity through the same Docker images
- Stateless processes; state in backing services
- Logs as event streams (stdout)
- Port binding via env var

**Secrets:** All credentials in environment variables or mounted secrets; no plaintext in source code or Docker images.

## Desired Outcome
An operator can clone the repository, copy `.env.example`, fill in API keys, run `docker compose up`, and have a fully functional StokAI deployment without any cloud account or Azure-specific configuration.

## Acceptance Criteria
- [ ] AC-001: Given a fresh machine with Docker and a populated `.env` file, `docker compose up` starts all services and the application is accessible and functional within 10 minutes.
- [ ] AC-002: Given a codebase scan for Azure-specific SDK imports (azure-*, @azure/*) in business logic modules (src/, not infrastructure adapters), zero results are found.
- [ ] AC-003: Given the configuration is checked, all service URLs, credentials, and feature flags are read from environment variables; no values are hardcoded in source files.
- [ ] AC-004: Given the `.env` file's database URL is changed from an Azure PostgreSQL URL to a localhost Docker container URL, no code changes are required and the application connects to the self-hosted database.

## Out of Scope
- Kubernetes deployment manifests (Docker Compose is sufficient for MVP self-hosting)
- Cloud-specific CI/CD integration testing

## NFR-Specific Fields

### Measurable Target
- `docker compose up` deployment time: ≤10 minutes from clone to functional stack on a reference machine
- 0 Azure SDK imports in business logic modules (src/ directories)
- 100% of configuration values read from environment variables (verified by static analysis)

### Verification Method
- Method: Docker Compose deployment test on a clean VM; static analysis scan for Azure SDK imports
- Tool/Process: CI job running `docker compose up` on a clean environment; grep/ruff for azure-* imports outside adapter modules
- Frequency: Per release
- Owner: DevOps / QA

### Category Rationale
Reliability NFR because portability reduces vendor lock-in risk and enables low-cost self-hosting. If Azure services become unavailable or unaffordable, the system must continue operating via self-hosted alternatives.

## Subtasks
- [ ] ST-001: Create Docker Compose file with all services (API, Celery, PostgreSQL, Redis, Langfuse, Clickhouse) — complexity: M
- [ ] ST-002: Audit and refactor any direct Azure SDK calls to use provider adapters — complexity: M
- [ ] ST-003: Implement 12-factor environment variable configuration — complexity: S
- [ ] ST-004: Create CI job for docker compose up smoke test — complexity: S

## Source Document References
| Document | Relevant Section | Contribution |
|----------|-----------------|-------------|
| system-description-digest.md | Non-Functional Signals; Architecture Signals | No Azure lock-in, docker compose up parity, 12-factor compliance |
