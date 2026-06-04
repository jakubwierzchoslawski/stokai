---
plan_id: PLAN-F-014
slug: prompt-management-pipeline
title: Prompt Management Pipeline
linked_requirement: REQ-F-014
type: functional
status: ready
blocked_reason:
complexity: L
tdd_required: true
linked_nfrs:
  - { id: REQ-N-009, reason: "Tier 2 regression gate is enforced as a hard CI block before any prompt is eligible for promotion to canary or production" }
dependencies:
  - { id: PLAN-F-016, reason: "Tier 2 golden dataset regression gates prompt promotion; ITier2Runner and RegressionReport contracts must exist before the CI gate runner can call them" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-F-014 — Prompt Management Pipeline

## Linked Requirement
**REQ-F-014** — Prompt Management Pipeline
Status: approved | Jira:

## Objective

Build the complete prompt lifecycle infrastructure that makes prompts first-class versioned artifacts in StokAI. This plan delivers: (1) a canonical `prompts/` directory layout with a frontmatter schema for all 15 prompt files (9 agents, 3 evaluators, 3 classifiers); (2) a `PromptLoader` service that reads prompt files from disk, resolves the git SHA as the version identifier, and publishes them to Langfuse on demand; (3) a CI GitHub Actions workflow step that detects prompt changes in a PR, invokes the Tier 2 regression runner from PLAN-F-016, and hard-blocks merge if any metric degrades by more than 5%; (4) a `PromptLabelService` that manages Langfuse label transitions (`staging` → `canary` → `production`) without code deploys; (5) a `stokai prompts rollback` CLI command that re-labels a previous Langfuse version as `production` and takes effect within 60 seconds; (6) per-invocation `prompt_version` (git SHA) recording in every `agent_invocation` Langfuse trace and DB row; and (7) integration tests verifying the rollback SLA and CI gate block behaviour.

## Architecture Context

This plan operates at the intersection of three architecture sections.

**Section 8 (Prompt Management):** Establishes the hybrid model: git is the source of truth, Langfuse is the runtime access layer. Defines the `prompts/agents/`, `prompts/evaluators/`, and `prompts/classifiers/` layout. Defines the seven-stage promotion pipeline and the four Langfuse labels (`production`, `staging`, `canary`, `experimental`). Defines the rollback mechanism as a pure Langfuse re-label requiring no code deploy.

**Section 9 (Evaluation Framework — Tier 2):** Tier 2 golden dataset regression is the hard gate at the PR stage. This plan's CI step calls `ITier2Runner.run_regression()` (contract owned by PLAN-F-016) and uses `RegressionReport.passed` and `RegressionReport.breached_metrics` to decide whether to block the merge.

**Section 12.4 (Observability):** Every agent invocation span in Langfuse must carry `prompt_version` (git SHA). PLAN-F-011 established the `LangfuseInvocationLogger` decorator that resolves the SHA; this plan ensures all 15 prompt files carry the frontmatter `agent` field so the decorator can locate the correct file by `role_id`.

**Section 5 (Backend Module Map):** Prompt loading and label management live in the `ai` module (`src/ai/prompts/`). The CLI command lives in `src/cli/`. A new DB migration adds `prompt_publication` table for audit. No other module is responsible for reading or publishing prompts.

**Section 13 (Technology Decisions):** Python 3.12+, FastAPI, SQLAlchemy 2.0 async, Langfuse self-hosted. The `langfuse` Python SDK is used for all Langfuse interactions. CI uses GitHub Actions.

## Applied NFR Constraints

| NFR | Constraint | Impact on this plan |
|-----|-----------|---------------------|
| REQ-N-009 | >5% degradation on any single metric hard-blocks PR merge; no override without explicit acknowledgment | TASK-003 implements the CI step that calls `ITier2Runner.run_regression()` and fails the job if `RegressionReport.passed is False`; the CI job produces a regression report artefact visible in the PR |

## Component Design

### New Components

```
prompts/                          (git-tracked source of truth)
  agents/
    relevance_analyst.md
    anomaly_detector.md
    historical_context_agent.md
    recommendation_synthesizer.md
    exposure_analyst.md
    earnings_context_agent.md
    event_deep_dive_agent.md
    narrative_writer.md
    qa_analyst.md
  evaluators/
    recommendation_judge.md       (stub stubs owned by PLAN-F-016; this plan writes the files)
    factuality_judge.md
    calibration_judge.md
  classifiers/
    event_classifier.md
    tweet_classifier.md
    ticker_extractor.md

Package: src/ai/prompts/
  ├── __init__.py
  ├── interfaces/
  │   ├── __init__.py
  │   ├── i_prompt_loader.py        — IPromptLoader (abstract): load_prompt(), get_sha()
  │   └── i_prompt_label_service.py — IPromptLabelService (abstract): apply_label(), get_active_version()
  ├── models/
  │   ├── __init__.py
  │   └── prompt_publication.py     — ORM: PromptPublication (audit trail row)
  ├── schemas/
  │   ├── __init__.py
  │   ├── prompt_schemas.py         — Pydantic: PromptFile, PromptFrontmatter, PromptPublication
  │   └── rollback_schemas.py       — Pydantic: RollbackRequest, RollbackResult
  ├── repositories/
  │   ├── __init__.py
  │   └── prompt_publication_repository.py — IPromptPublicationRepository + impl
  ├── services/
  │   ├── __init__.py
  │   ├── prompt_loader.py          — PromptLoader: read file, parse frontmatter, compute git SHA, publish to Langfuse
  │   └── prompt_label_service.py   — PromptLabelService: apply_label(), rollback(), get_active_version()
  └── tasks/
      ├── __init__.py
      └── publish_prompts_task.py   — Celery task: publish_all_prompts_to_langfuse (run on deploy)

Package: src/cli/
  ├── __init__.py
  └── prompts_cli.py               — Click CLI: `stokai prompts rollback`, `stokai prompts promote`, `stokai prompts status`

CI:
  .github/workflows/prompt-regression.yml — GitHub Actions: detect prompts/ changes, run Tier 2 gate

Alembic migration:
  alembic/versions/XXXX_prompt_publication_table.py
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `src/ai/observability/langfuse_logger.py` | Verify `prompt_version` resolution uses `PromptLoader.get_sha(role_id)` for the correct file path | Ensures all 15 prompt files are locatable by `role_id` via the loader |
| `src/config/settings.py` | Add `PROMPTS_DIR`, `LANGFUSE_PROMPTS_ENABLED`, `CANARY_TRAFFIC_PCT` settings | Prompt pipeline configuration via environment variables |

### Interfaces and Contracts

```python
# src/ai/prompts/interfaces/i_prompt_loader.py

class IPromptLoader(ABC):
    @abstractmethod
    def load_prompt(self, role_id: str) -> PromptFile:
        """Read prompt file from disk; parse frontmatter; compute git SHA."""
        ...

    @abstractmethod
    def get_sha(self, role_id: str) -> str:
        """Return the git SHA for the file containing this role's prompt."""
        ...

    @abstractmethod
    async def publish_to_langfuse(self, role_id: str) -> PromptPublication:
        """Push current file content to Langfuse with git SHA as version label."""
        ...

    @abstractmethod
    async def publish_all(self) -> list[PromptPublication]:
        """Publish every prompt file in the prompts/ layout to Langfuse."""
        ...


# src/ai/prompts/interfaces/i_prompt_label_service.py

class IPromptLabelService(ABC):
    @abstractmethod
    async def apply_label(
        self,
        role_id: str,
        version_sha: str,
        label: PromptLabel,  # Literal["production", "staging", "canary", "experimental"]
    ) -> None:
        """Apply a Langfuse label to a specific prompt version."""
        ...

    @abstractmethod
    async def get_active_version(self, role_id: str, label: PromptLabel) -> str | None:
        """Return the version SHA currently carrying the given label, or None."""
        ...

    @abstractmethod
    async def rollback(self, role_id: str, to_version: str) -> RollbackResult:
        """
        Re-label to_version as 'production'; strip 'production' from any other version.
        Must complete within 60 seconds (REQ-N-009 / AC-003).
        Returns RollbackResult with effective_at timestamp and previous_version.
        """
        ...


# src/ai/prompts/repositories/prompt_publication_repository.py

class IPromptPublicationRepository(ABC):
    @abstractmethod
    async def insert(self, pub: PromptPublicationCreate) -> PromptPublication: ...
    @abstractmethod
    async def get_by_role_and_sha(self, role_id: str, sha: str) -> PromptPublication | None: ...
    @abstractmethod
    async def list_by_role(self, role_id: str, limit: int = 50) -> list[PromptPublication]: ...
```

**PromptLabel enum and PromptFile schema:**

```python
# src/ai/prompts/schemas/prompt_schemas.py

class PromptLabel(str, Enum):
    production   = "production"
    staging      = "staging"
    canary       = "canary"
    experimental = "experimental"

class PromptFrontmatter(BaseModel):
    version: str | None = None   # populated after git SHA resolution; absent in file
    agent: str                   # role_id (e.g. "relevance_analyst")
    description: str

class PromptFile(BaseModel):
    role_id: str
    file_path: str
    frontmatter: PromptFrontmatter
    body: str
    sha: str                     # git SHA of the file at HEAD

class PromptPublication(BaseModel):
    publication_id: UUID
    role_id: str
    sha: str
    langfuse_version: str        # equals sha
    published_at: datetime
    published_by: str            # "ci" | "cli" | "admin"

class RollbackResult(BaseModel):
    role_id: str
    previous_version: str
    rolled_back_to: str
    effective_at: datetime       # must be within 60 s of request (AC-003)
```

**Prompt frontmatter schema (in the .md files):**

```yaml
---
version:                  # intentionally blank — git SHA is assigned at publish time
agent: <role_id>          # e.g. relevance_analyst
description: <one-liner>
---
{prompt body text}
```

**Regression report (from PLAN-F-016 — read-only contract for this plan):**

```python
# From src/ai/evaluation/interfaces/i_tier2_runner.py  (PLAN-F-016 owns this)
class RegressionReport(BaseModel):
    passed: bool
    per_metric_delta: dict[str, float]  # metric -> pct change; negative = degradation
    breached_metrics: list[str]         # metrics with delta < -0.05
```

## Implementation Tasks

### TASK-001: Prompt directory layout and frontmatter schema · S/no-TDD · prompts/agents/relevance_analyst.md, prompts/agents/anomaly_detector.md, prompts/agents/historical_context_agent.md, prompts/agents/recommendation_synthesizer.md, prompts/agents/exposure_analyst.md, prompts/agents/earnings_context_agent.md, prompts/agents/event_deep_dive_agent.md, prompts/agents/narrative_writer.md, prompts/agents/qa_analyst.md, prompts/evaluators/recommendation_judge.md, prompts/evaluators/factuality_judge.md, prompts/evaluators/calibration_judge.md, prompts/classifiers/event_classifier.md, prompts/classifiers/tweet_classifier.md, prompts/classifiers/ticker_extractor.md

Create the `prompts/` directory tree. Write all 15 prompt files with correct YAML frontmatter (`version:` blank, `agent: <role_id>`, `description: <one-liner>`). Body text is a meaningful placeholder for each role — must not be empty strings, as they must be parseable by `PromptLoader` in subsequent tasks. Evaluator and classifier files are stubs that will be enriched by PLAN-F-016 and REQ-F-002 respectively; this task only establishes valid structure.

Frontmatter must be parseable by the `PromptFrontmatter` Pydantic model defined in TASK-002.

**AC covered**: AC-002 (prompt files exist in git and can be loaded by `role_id`)

---

### TASK-002: PromptFile schema, IPromptLoader interface, and PromptLoader service · M/TDD · src/ai/prompts/__init__.py, src/ai/prompts/interfaces/__init__.py, src/ai/prompts/interfaces/i_prompt_loader.py, src/ai/prompts/schemas/__init__.py, src/ai/prompts/schemas/prompt_schemas.py, src/ai/prompts/services/__init__.py, src/ai/prompts/services/prompt_loader.py

Implement `PromptLoader`, which:
- Reads a prompt `.md` file from the `prompts/` directory tree using `role_id` as a lookup key (agents, evaluators, classifiers).
- Parses the YAML frontmatter block using `python-frontmatter` (or equivalent); validates against `PromptFrontmatter`.
- Computes the git SHA of the file at `HEAD` using `subprocess.run(["git", "hash-object", file_path], ...)` — deterministic, portable, no git dependency beyond the CLI.
- Returns a populated `PromptFile` Pydantic model.
- `publish_to_langfuse()` calls the Langfuse Python SDK to create/update a prompt, using `sha` as the version string and setting the initial label to `staging`.
- `publish_all()` iterates all 15 known files and calls `publish_to_langfuse()` for each; returns the list of `PromptPublication` objects.
- Handles `FileNotFoundError` (unknown role) and Langfuse SDK errors as typed domain exceptions: `PromptNotFoundError`, `LangfusePublishError`.

**Tests to write first (TDD)**:
- `test_load_prompt_parses_frontmatter_and_body`: given a temp `.md` file with valid frontmatter, `load_prompt()` returns a `PromptFile` with correct fields.
- `test_load_prompt_raises_not_found_for_unknown_role`: `load_prompt("unknown_role")` raises `PromptNotFoundError`.
- `test_get_sha_returns_40_char_hex_string`: `get_sha(role_id)` returns a string matching `^[0-9a-f]{40}$`.
- `test_publish_to_langfuse_calls_sdk_with_sha_as_version`: mock the Langfuse SDK; assert the SDK `create_prompt` was called with `version=sha` and `labels=["staging"]`.
- `test_publish_all_publishes_all_15_roles`: mock the SDK; assert exactly 15 publications for the canonical role list.

**AC covered**: AC-002, AC-004

---

### TASK-003: CI GitHub Actions step — Tier 2 regression gate on prompt PR · M/TDD · .github/workflows/prompt-regression.yml, src/ai/prompts/ci/regression_gate.py

Write the GitHub Actions workflow `.github/workflows/prompt-regression.yml` that:
- Triggers on `pull_request` when any file under `prompts/**` is changed.
- Detects which prompt files changed (using `git diff --name-only`), extracts `role_id` values from the frontmatter of each changed file.
- For each changed `role_id`, calls `ITier2Runner.run_regression(prompt_version_candidate=head_sha, prompt_version_production=production_sha, agent_role=role_id)`.
- If `RegressionReport.passed is False`, exits with code 1 and emits a structured summary to the GitHub Actions step summary listing each `breached_metric` and its delta.
- If all regression reports pass, exits with code 0 and posts a pass summary.

Write `src/ai/prompts/ci/regression_gate.py` — a Python script that is the entrypoint for the CI step. It accepts `--role-id`, `--candidate-sha`, `--production-sha` as CLI arguments, instantiates `Tier2RunnerService` (from PLAN-F-016) via a thin DI shim, and exits non-zero on failure. This module is the only code in this plan that must be runnable outside of the FastAPI process.

The workflow enforces REQ-N-009: no override path is provided; the only way forward is to revise the prompt and pass the gate.

**Tests to write first (TDD)**:
- `test_regression_gate_exits_0_when_report_passed`: mock `ITier2Runner` returning `RegressionReport(passed=True, ...)`; assert `sys.exit` is called with 0.
- `test_regression_gate_exits_1_when_report_failed`: mock `ITier2Runner` returning `RegressionReport(passed=False, breached_metrics=["factual_grounding"])` ; assert `sys.exit` is called with 1.
- `test_regression_gate_emits_summary_for_each_breached_metric`: assert the written summary string contains `"factual_grounding"` when that metric is breached.
- `test_ci_workflow_yaml_triggers_on_prompts_path_change`: parse the YAML file and assert the `paths` filter includes `"prompts/**"`.

**AC covered**: AC-001

---

### TASK-004: IPromptLabelService interface and PromptLabelService · M/TDD · src/ai/prompts/interfaces/i_prompt_label_service.py, src/ai/prompts/schemas/rollback_schemas.py, src/ai/prompts/services/prompt_label_service.py

Implement `PromptLabelService`, which wraps the Langfuse Python SDK label management API:
- `apply_label(role_id, version_sha, label)`: calls `langfuse_client.update_prompt(name=role_id, version=version_sha, labels=[label])`. Raises `LangfuseLabelError` on SDK failure.
- `get_active_version(role_id, label)`: queries Langfuse for the prompt named `role_id` and returns the `version` (SHA) carrying the given label, or `None` if none is active.
- `rollback(role_id, to_version)`: orchestrates atomically: (1) records `previous_version = get_active_version(role_id, "production")`; (2) calls `apply_label(role_id, to_version, "production")`; (3) records `effective_at = utcnow()`; (4) returns `RollbackResult`. The complete round-trip to the Langfuse API must complete within 10 seconds; the caller (CLI) is responsible for verifying agent re-reads within the 60-second SLA.

`PromptLabel` enum covers all four labels: `production`, `staging`, `canary`, `experimental`.

**Tests to write first (TDD)**:
- `test_apply_label_calls_sdk_update_with_correct_args`: mock the Langfuse SDK; assert `update_prompt` called with `name=role_id`, `version=sha`, `labels=[label.value]`.
- `test_get_active_version_returns_sha_when_label_found`: mock SDK list response; assert returns the correct SHA.
- `test_get_active_version_returns_none_when_no_match`: mock SDK returning no version with target label.
- `test_rollback_returns_result_with_previous_and_new_version`: mock SDK; assert `RollbackResult.rolled_back_to == to_version` and `previous_version` matches pre-rollback active version.
- `test_rollback_effective_at_is_within_10_seconds`: assert `RollbackResult.effective_at - request_time < timedelta(seconds=10)`.

**AC covered**: AC-002, AC-003

---

### TASK-005: prompt_publication DB table, ORM model, repository · M/TDD · alembic/versions/XXXX_prompt_publication_table.py, src/ai/prompts/models/__init__.py, src/ai/prompts/models/prompt_publication.py, src/ai/prompts/repositories/__init__.py, src/ai/prompts/repositories/prompt_publication_repository.py

Create the `prompt_publication` table for audit — every publish and rollback is recorded:

```sql
prompt_publication (
    publication_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id         VARCHAR     NOT NULL,
    sha             VARCHAR(40) NOT NULL,
    langfuse_version VARCHAR    NOT NULL,  -- equals sha
    label_applied   VARCHAR     NOT NULL,  -- staging | canary | production | experimental
    action          VARCHAR     NOT NULL,  -- "publish" | "label" | "rollback"
    published_by    VARCHAR     NOT NULL,  -- "ci" | "cli" | "admin"
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

Index on `(role_id, published_at DESC)`.

Implement `PromptPublicationRepository` with:
- `insert(pub: PromptPublicationCreate) -> PromptPublication`
- `get_by_role_and_sha(role_id, sha) -> PromptPublication | None`
- `list_by_role(role_id, limit=50) -> list[PromptPublication]`
- `list_recent(limit=100) -> list[PromptPublication]`

**Tests to write first (TDD)**:
- `test_insert_publication_persists_row`: insert a `PromptPublicationCreate`; query back and assert all fields match.
- `test_get_by_role_and_sha_returns_none_for_unknown`: assert `None` when no matching row exists.
- `test_list_by_role_returns_ordered_by_published_at_desc`: insert three rows; assert ordering.
- `test_list_recent_respects_limit`: insert 110 rows; assert `list_recent(limit=100)` returns exactly 100.

**AC covered**: AC-004 (audit trail persisted in DB)

---

### TASK-006: stokai prompts CLI — rollback, promote, status commands · M/TDD · src/cli/__init__.py, src/cli/prompts_cli.py

Implement a `click` CLI group `stokai prompts` with three commands:

**`stokai prompts rollback --agent <role_id> --to-version <sha>`**
- Resolves `IPromptLabelService` from DI.
- Calls `PromptLabelService.rollback(role_id, sha)`.
- Inserts a `prompt_publication` audit row (`action="rollback"`, `published_by="cli"`).
- Prints the rollback result in human-readable form with `effective_at` timestamp.
- Exits 0 on success; prints error message and exits 1 on any failure (e.g. version not found in Langfuse).

**`stokai prompts promote --agent <role_id> --from-label canary --to-label production`**
- Calls `get_active_version(role_id, "canary")` to obtain the SHA.
- Calls `apply_label(role_id, sha, "production")`.
- Records audit row.

**`stokai prompts status --agent <role_id>`**
- Prints the SHA currently labelled `production`, `staging`, and `canary` for the agent.

The CLI is invoked via `python -m src.cli.prompts_cli` or through the `stokai` entry point defined in `pyproject.toml`. No FastAPI dependency in this module — it uses the same SQLAlchemy async session factory and Langfuse client instantiated via a lightweight bootstrap function `_get_services()`.

**Tests to write first (TDD)**:
- `test_rollback_command_calls_label_service_rollback`: use `click.testing.CliRunner`; mock `IPromptLabelService`; assert `rollback()` called with correct `role_id` and `sha`.
- `test_rollback_command_exits_0_on_success`: assert runner `exit_code == 0`.
- `test_rollback_command_exits_1_on_label_service_error`: mock `rollback()` to raise `LangfuseLabelError`; assert `exit_code == 1`.
- `test_promote_command_applies_production_label`: mock; assert `apply_label` called with `label=PromptLabel.production`.
- `test_status_command_prints_all_three_labels`: mock `get_active_version` for each label; assert output contains `production`, `staging`, `canary`.

**AC covered**: AC-003

---

### TASK-007: publish_all_prompts_to_langfuse Celery task and deploy hook · S/no-TDD · src/ai/prompts/tasks/__init__.py, src/ai/prompts/tasks/publish_prompts_task.py, src/config/celery_app.py

Implement the `publish_all_prompts_to_langfuse` Celery task that calls `PromptLoader.publish_all()` and inserts `prompt_publication` audit rows for each result. This task is triggered by the CI pipeline (via `celery call`) after a merge to main — it is the mechanism that applies the `staging` label to the newly merged prompt SHA.

Register the task in `celery_app.py`. No cron beat schedule — this task is triggered explicitly on deploy; it is not a recurring job.

**AC covered**: AC-002 (staging label applied on merge)

---

### TASK-008: prompt_version SHA recording in every agent invocation · M/TDD · src/ai/observability/langfuse_logger.py, src/ai/prompts/services/prompt_loader.py

Extend the `LangfuseInvocationLogger` decorator (established in PLAN-F-011) to resolve `prompt_version` via `IPromptLoader.get_sha(agent_role)` at invocation time and attach it to:
1. The Langfuse span as metadata field `prompt_version`.
2. The `agent_invocation` DB row column `prompt_version` (column already exists in the schema per Architecture §10).

If `get_sha()` raises `PromptNotFoundError` (e.g. role has no prompt file, such as purely deterministic nodes), log a warning and set `prompt_version = "unknown"` — do not fail the invocation.

This task closes the traceability chain: every `agent_invocation` row and every Langfuse span carries the exact git SHA of the prompt that produced the output.

**Tests to write first (TDD)**:
- `test_invocation_logger_attaches_sha_to_langfuse_span`: mock `IPromptLoader.get_sha()` returning a fixed SHA; assert the Langfuse span `metadata["prompt_version"]` equals that SHA.
- `test_invocation_logger_writes_sha_to_db_row`: mock DB session; assert `agent_invocation.prompt_version` equals the resolved SHA.
- `test_invocation_logger_uses_unknown_when_no_prompt_file`: mock `get_sha()` to raise `PromptNotFoundError`; assert `prompt_version == "unknown"` and no exception propagates.
- `test_invocation_logger_does_not_swallow_other_errors`: mock `get_sha()` to raise `RuntimeError`; assert the `RuntimeError` propagates.

**AC covered**: AC-004

---

### TASK-009: Canary monitoring wiring — Tier 1 + Tier 3 metrics visible for canary cohort · M/TDD · src/ai/prompts/services/prompt_label_service.py, src/api/evaluation/evaluation_router.py

When a prompt version is labelled `canary`, all agents serving canary traffic must record the SHA in their Langfuse spans. The Langfuse SDK natively associates traces with the prompt version via the version label. This task adds:

1. A `canary_cohort` metadata tag on every Langfuse trace where the serving label was `canary` — set by `LangfuseInvocationLogger` when `get_active_version(role_id, "canary") == current_sha`.
2. An admin API endpoint `GET /api/v1/admin/prompts/{role_id}/canary-metrics` that queries Langfuse for evaluation scores (Tier 1 — per PLAN-F-016 contract) and calibration results (Tier 3) filtered to `prompt_version = canary_sha`. Returns a `CanaryMetricsSummary` Pydantic response.

The endpoint is gated to `admin` role (Architecture §12.1).

**Tests to write first (TDD)**:
- `test_canary_tag_added_to_span_when_sha_matches_canary_label`: mock `get_active_version` returning the same SHA as the invocation; assert Langfuse span has `metadata["canary_cohort"] = True`.
- `test_canary_tag_absent_when_sha_is_not_canary`: assert `"canary_cohort"` absent or `False` in non-canary invocation.
- `test_canary_metrics_endpoint_returns_200_for_admin`: mock evaluation query; assert 200 and response shape.
- `test_canary_metrics_endpoint_returns_403_for_end_user`: assert 403 for non-admin token.

**AC covered**: AC-005

---

### TASK-010: Integration tests — rollback SLA and regression gate block · L/TDD · tests/integration/prompts/test_rollback_sla.py, tests/integration/prompts/test_regression_gate_block.py

Write integration tests that verify the two hardest constraints:

**Rollback SLA (AC-003):**
- `test_rollback_completes_within_60_seconds`: against a real (self-hosted, test) Langfuse instance; publish a prompt version; apply `production` label; call `PromptLabelService.rollback()`; measure wall-clock time; assert total time < 60 seconds; verify `get_active_version(role_id, "production")` returns `to_version`.
- `test_subsequent_agent_invocation_uses_rolled_back_version`: after rollback, create a mock agent invocation; assert the resolved `prompt_version` SHA matches the rolled-back version.

**Regression gate block (AC-001):**
- `test_regression_gate_blocks_on_degraded_prompt`: mock `ITier2Runner.run_regression()` to return a failing `RegressionReport`; run `regression_gate.py` via `subprocess` or `CliRunner`; assert exit code 1.
- `test_regression_gate_passes_on_clean_prompt`: mock returning a passing `RegressionReport`; assert exit code 0.
- `test_regression_gate_produces_readable_summary_for_each_breached_metric`: assert the summary output contains metric name and delta value for each breached metric.

**Tests to write first (TDD)**:
All five tests above — write assertions before the production implementations of TASK-004 and TASK-003 are fully wired, using a test double for Langfuse where a live instance is unavailable.

**AC covered**: AC-001, AC-002, AC-003, AC-004

## Acceptance Criteria Coverage

- AC-001: Given a PR modifies a prompt file in `prompts/`, CI automatically runs the Tier 2 golden dataset regression; if degradation >5% on any metric, the PR is blocked from merge. → TASK-003, TASK-010
- AC-002: Given a prompt is merged and staged in Langfuse, agents in the staging environment use the staged prompt version (identified by git SHA) without any code changes. → TASK-002, TASK-004, TASK-007, TASK-010
- AC-003: Given `stokai prompts rollback --agent <role_id> --to-version <sha>` is executed, the active prompt version for that agent in Langfuse is updated and subsequent agent invocations use the rolled-back version within 60 seconds. → TASK-004, TASK-006, TASK-010
- AC-004: Given any agent invocation in production, the Langfuse trace for that invocation records the prompt_version (SHA) used, enabling reconstruction of which prompt produced which output. → TASK-002, TASK-005, TASK-008, TASK-010
- AC-005: Given the Tier 2 regression passes and the prompt reaches canary, Tier 1 and Tier 3 monitoring metrics are visible in the admin AI audit console for the canary cohort. → TASK-009

## Open Questions Inherited

| # | Question | Resolution |
|---|----------|-----------|
| 1 | What canary traffic percentage and duration are used before promotion is eligible? | Planning decision: default `CANARY_TRAFFIC_PCT=10` percent (configurable via env var `CANARY_TRAFFIC_PCT`); minimum canary duration before promotion eligibility is not enforced programmatically in this plan — promotion remains a human-admin action via `stokai prompts promote` or the Langfuse UI. Duration guidance is documented in the Admin AI Audit Console section (PLAN-F-029 scope). The env var is introduced in `settings.py` in TASK-007 for future enforcement use. |

## Risks and Notes

- The Langfuse Python SDK label API shape must be verified against the self-hosted version. The `update_prompt` method's `labels` parameter behaviour (additive vs. replace) must be confirmed — `PromptLabelService` must strip the old `production` label before applying the new one if the SDK is additive, to avoid multiple versions carrying the same label.
- TASK-003 calls `ITier2Runner.run_regression()`, which is owned by PLAN-F-016. If PLAN-F-016 is not yet executed, the CI step will fail at import time. The CI workflow YAML should guard this with a `needs:` dependency on a future "evaluation-framework-deployed" check or use a contract-test stub for the regression runner in CI.
- `get_sha()` using `git hash-object` computes the blob SHA, not the commit SHA. This is the correct choice for Langfuse versioning because it is deterministic from the file content alone and does not change when unrelated files in the same commit change. The ARCHITECTURE §8 phrase "git SHA as version" should be interpreted as the file blob SHA — the traceability chain is from file content to Langfuse version, not from commit to version.
- The `publish_all_prompts_to_langfuse` Celery task (TASK-007) must be idempotent: publishing the same SHA twice must not create duplicate Langfuse prompt versions. Use the Langfuse SDK's upsert behaviour or check `get_by_role_and_sha` in the repository before publishing.
