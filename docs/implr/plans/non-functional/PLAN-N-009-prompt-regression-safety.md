---
plan_id: PLAN-N-009
slug: prompt-regression-safety
title: Prompt Regression Safety Gate
linked_requirement: REQ-N-009
type: non-functional
status: ready
blocked_reason:
complexity: M
tdd_required: true
linked_nfrs:
dependencies:
  - { id: PLAN-F-014, reason: "Rollback CLI (PromptLabelService.rollback) and RollbackResult contract are owned by PLAN-F-014; this plan's rollback verification tests depend on that contract" }
  - { id: PLAN-F-016, reason: "GoldenDatasetRunner.run_suite() and RegressionReport contract are owned by PLAN-F-016; this plan's CI gate and performance tests call those interfaces" }
executed_at:
reviewed_at:
review_id:
created_at: 2026-06-02T00:00:00Z
updated_at: 2026-06-02T00:00:00Z
---

# PLAN-N-009 — Prompt Regression Safety Gate

## Linked Requirement
**REQ-N-009** — Prompt Regression Safety Gate
Status: approved | Jira:

## Objective

This plan hardens the prompt promotion pipeline by adding three observable enforcement layers on top of the functional capabilities delivered by PLAN-F-014 and PLAN-F-016. First, it specifies and tests the per-metric 5%-threshold gate logic that lives inside `Tier2RunnerService.run_regression()` — verifying that a breach on any single metric blocks the PR regardless of improvements on other metrics. Second, it defines and tests a performance contract ensuring the full golden dataset CI run completes in under 5 minutes for a dataset of at least 20 test cases, so prompt authors receive fast feedback. Third, it adds an integration test suite that verifies the end-to-end rollback SLA: an agent invocation executed 60 seconds after `stokai prompts rollback` must resolve the rolled-back prompt version from Langfuse, confirmed by the `prompt_version` field in the resulting Langfuse trace. No new production modules are introduced — the plan delivers test coverage, a CI timing harness, and configuration that enforces the measurable targets in REQ-N-009.

## Architecture Context

This plan spans three architecture sections in a verification-only capacity.

**Section 8 (Prompt Management):** The 5% hard gate is stated in Architecture §8 as "no override without explicit acknowledgment". This plan's TASK-001 contains the unit tests that confirm the gate logic implemented in PLAN-F-016 TASK-007 enforces the per-metric (not aggregate) rule. All rollback mechanics (re-labelling Langfuse, `RollbackResult.effective_at`) are owned by PLAN-F-014 TASK-004 and TASK-006; this plan wraps them in a timing-bound integration test.

**Section 9 (Evaluation Framework — Tier 2):** PLAN-F-016 TASK-007 owns `Tier2RunnerService` and `RegressionReport`. PLAN-F-016 TASK-012 owns the integration flow test. This plan adds a targeted performance test (TASK-003) that measures wall-clock execution time of `run_regression()` against a 20-case dataset and asserts it completes within 300 seconds — complementing functional correctness with a latency contract the dev-executor can run in CI.

**Section 12.4 (Langfuse Observability):** Agent invocations fetch the active Langfuse prompt version at startup (not cached beyond request lifetime). The rollback verification test (TASK-004) relies on this stateless fetch behaviour: triggering an agent invocation 60 seconds after rollback is sufficient to confirm the new version is live, because no in-process cache exists to serve the old version.

**Section 14 (CI/CD — GitHub Actions):** PLAN-F-014 TASK-003 defines the `prompt-regression.yml` workflow. This plan adds a companion CI job configuration (`prompt-regression-perf-check` step) that instruments the `run_regression()` call with a wall-clock timer and fails the workflow step if the elapsed time exceeds 300 seconds.

## Component Design

### New Components

```
tests/unit/evaluation/
  test_regression_gate_per_metric.py   — per-metric threshold unit tests (TASK-001)

tests/unit/prompts/
  test_rollback_sla_contract.py        — rollback SLA contract unit tests (TASK-002)

tests/integration/evaluation/
  test_regression_perf.py              — CI timing / performance integration test (TASK-003)

tests/integration/prompts/
  test_rollback_e2e.py                 — 60-second rollback end-to-end integration test (TASK-004)

src/ai/evaluation/ci/
  __init__.py
  perf_gate.py                         — CI timing harness called by GitHub Actions (TASK-003)

.github/workflows/prompt-regression.yml   — modified: add perf-check step (TASK-003)
```

### Modified Components

| File | Change | Reason |
|------|--------|--------|
| `.github/workflows/prompt-regression.yml` | Add `prompt-regression-perf-check` job step that invokes `perf_gate.py` and fails if elapsed > 300 s | Enforce AC-004 CI run-time contract |
| `src/ai/evaluation/services/tier2_runner_service.py` | Add `assert len(active_items) >= 20` guard with descriptive `InsufficientDatasetError`; confirm per-metric delta formula matches REQ-N-009 (`delta < -0.05` not aggregate) | Ensures the gate is per-metric as required by AC-002 |

### Interfaces and Contracts

The following contracts from dependency plans are consumed read-only. They are listed here for executor clarity; no changes to these interfaces are made by this plan.

```python
# From PLAN-F-016 — src/ai/evaluation/interfaces/i_tier2_runner.py
class ITier2Runner(ABC):
    async def run_regression(
        self,
        prompt_version_candidate: str,
        prompt_version_production: str,
        agent_role: str,
    ) -> RegressionReport: ...

class RegressionReport(BaseModel):
    passed: bool                          # True iff no metric has delta < -0.05
    per_metric_delta: dict[str, float]    # metric -> pct change; negative = degradation
    breached_metrics: list[str]           # metrics with delta < -0.05

# From PLAN-F-014 — src/ai/prompts/interfaces/i_prompt_label_service.py
class IPromptLabelService(ABC):
    async def rollback(self, role_id: str, to_version: str) -> RollbackResult: ...
    async def get_active_version(self, role_id: str, label: PromptLabel) -> str | None: ...

class RollbackResult(BaseModel):
    role_id: str
    previous_version: str
    rolled_back_to: str
    effective_at: datetime                # must be within 60 s of request (AC-003)
```

**Performance gate script contract:**

```python
# src/ai/evaluation/ci/perf_gate.py
#
# CLI: python -m src.ai.evaluation.ci.perf_gate
#      --role-id <role_id>
#      --candidate-sha <sha>
#      --production-sha <sha>
#      --max-seconds 300          # configurable threshold; default 300
#
# Exits 0 if run_regression completes within --max-seconds.
# Exits 2 if the time limit is exceeded (distinct from exit 1 = regression failure).
# Writes timing JSON to stdout: {"elapsed_seconds": float, "within_limit": bool}
```

## Implementation Tasks

### TASK-001: Per-metric gate unit tests — verify 5% threshold is not aggregate · M/TDD · tests/unit/evaluation/test_regression_gate_per_metric.py

Write unit tests that verify `Tier2RunnerService.run_regression()` (from PLAN-F-016) enforces the per-metric threshold correctly. These tests mock `IGoldenDatasetRepository` and the agent invocation layer; they call the real `Tier2RunnerService` business logic.

The critical invariant: a single metric breaching -5% must produce `passed=False` even if all other metrics improve substantially. No aggregation or weighted averaging is permitted.

**Tests to write first (TDD)**:
- `test_single_metric_breach_blocks_regardless_of_improvements`: candidate scores: `coherence +10%`, `factual_accuracy +5%`, `action_signal_correctness -6%`, `recommendation_quality +3%`, `confidence_calibration +8%`. Assert `passed=False` and `breached_metrics == ["action_signal_correctness"]`.
- `test_two_metrics_below_threshold_both_appear_in_breached`: candidate scores: `coherence -7%`, `factual_accuracy -6%`, `action_signal_correctness +2%`. Assert `passed=False` and both `"coherence"` and `"factual_accuracy"` are in `breached_metrics`.
- `test_exactly_at_threshold_does_not_breach`: `action_signal_correctness -5.0%` (delta == -0.05). Assert `passed=True` — the gate fires on `< -0.05`, not `<= -0.05`.
- `test_just_over_threshold_breaches`: `action_signal_correctness -5.1%` (delta == -0.051). Assert `passed=False`.
- `test_all_metrics_improving_passes`: all deltas positive. Assert `passed=True`, `breached_metrics == []`.
- `test_mixed_result_ac002_scenario`: exactly the AC-002 scenario — 2% and 4% degradation on two metrics, 6% degradation on a third. Assert `passed=False`; only the 6%-breaching metric appears in `breached_metrics`.

**AC covered**: AC-001, AC-002

---

### TASK-002: Rollback SLA contract unit tests — RollbackResult.effective_at within 60 s · M/TDD · tests/unit/prompts/test_rollback_sla_contract.py

Write unit tests that verify `PromptLabelService.rollback()` (from PLAN-F-014) returns a `RollbackResult` whose `effective_at` is within the 60-second SLA window. These tests mock the Langfuse SDK client and assert on the `RollbackResult` schema contract; they do not require a live Langfuse instance.

The distinction from PLAN-F-014 TASK-010 is scope: those tests verify the `PromptLabelService` implementation details. These tests verify the SLA observable to a caller — the contract that REQ-N-009 AC-003 mandates.

**Tests to write first (TDD)**:
- `test_rollback_result_effective_at_is_populated`: after calling `rollback(role_id, to_version)`, assert `result.effective_at` is not `None`.
- `test_rollback_result_effective_at_is_within_60_seconds`: measure `utcnow()` before calling `rollback()`; assert `result.effective_at - before < timedelta(seconds=60)`.
- `test_rollback_result_rolled_back_to_equals_requested_version`: assert `result.rolled_back_to == to_version` — confirms Langfuse was updated to the correct target SHA.
- `test_rollback_result_previous_version_is_captured`: seed a mock `get_active_version` returning `"sha-old"`; assert `result.previous_version == "sha-old"`.
- `test_rollback_returns_result_not_raises_on_no_prior_production_label`: mock `get_active_version` returning `None` (no prior production label); assert `rollback()` does not raise and `result.previous_version` is `None` or empty string.

**AC covered**: AC-003

---

### TASK-003: CI performance gate — regression run must complete in under 5 minutes · M/TDD · src/ai/evaluation/ci/__init__.py, src/ai/evaluation/ci/perf_gate.py, .github/workflows/prompt-regression.yml, tests/integration/evaluation/test_regression_perf.py

Build a thin CI timing harness `perf_gate.py` that wraps `Tier2RunnerService.run_regression()` with a wall-clock timer. The script is the entrypoint for a `prompt-regression-perf-check` step added to the existing `prompt-regression.yml` GitHub Actions workflow.

`perf_gate.py` design:
- Accepts `--role-id`, `--candidate-sha`, `--production-sha`, and `--max-seconds` (default 300) as CLI arguments.
- Records `start = time.monotonic()` before calling `run_regression()`.
- On completion: `elapsed = time.monotonic() - start`; writes JSON `{"elapsed_seconds": elapsed, "within_limit": elapsed <= max_seconds}` to stdout.
- Exits 0 when regression passes and elapsed is within limit.
- Exits 1 when regression fails (metric breach) — same as the existing gate.
- Exits 2 when regression passes but elapsed exceeds the time limit — distinct exit code allows CI to surface a timing-only failure without blocking on correctness.

Modify `.github/workflows/prompt-regression.yml` to add the `prompt-regression-perf-check` step after the existing regression check step, running `perf_gate.py` with `--max-seconds 300`. The step uploads the timing JSON as a CI artifact.

Write integration tests in `test_regression_perf.py` using a mock dataset of exactly 20 items with stub agent invocations (no real Anthropic calls). Assert:
- The test completes in under 300 seconds.
- The timing JSON written to stdout is valid JSON with `"elapsed_seconds"` and `"within_limit"` keys.

**Tests to write first (TDD)**:
- `test_perf_gate_exits_0_on_passing_regression_within_time_limit`: mock `ITier2Runner` returning `RegressionReport(passed=True, ...)`; stub timer returning elapsed=180; assert exit code 0.
- `test_perf_gate_exits_1_on_failing_regression_regardless_of_timing`: mock runner returning `passed=False`; assert exit code 1 (metric breach takes priority over timing).
- `test_perf_gate_exits_2_on_passing_regression_but_exceeded_time`: mock runner returning `passed=True`; stub timer returning elapsed=310; assert exit code 2.
- `test_perf_gate_writes_timing_json_to_stdout`: capture stdout; assert output is valid JSON containing `"elapsed_seconds"` and `"within_limit"` keys.
- `test_regression_run_completes_within_300s_with_20_item_dataset`: integration test against `Tier2RunnerService` with 20 mock golden dataset items and stub agent invocations; measure real wall-clock time; assert elapsed < 300.
- `test_ci_workflow_yaml_includes_perf_check_step`: parse `prompt-regression.yml`; assert a step named `prompt-regression-perf-check` exists and references `perf_gate.py`.

**AC covered**: AC-004

---

### TASK-004: Rollback end-to-end integration test — agent invocation after 60 s uses rolled-back version · M/TDD · tests/integration/prompts/test_rollback_e2e.py

Write an integration test that verifies the complete rollback propagation path as described in AC-003. The test uses a self-hosted (test) Langfuse instance (or a Langfuse SDK stub that behaves identically for label resolution) and a real `PromptLabelService`.

Test scenario:
1. Publish two prompt versions for a test agent role: `sha-v1` (initial production) and `sha-v2` (promoted to production).
2. Verify that an agent invocation immediately before rollback resolves `prompt_version == "sha-v2"` in its Langfuse span metadata.
3. Execute `PromptLabelService.rollback(role_id=test_role, to_version="sha-v1")`.
4. Wait 60 seconds (configurable via `ROLLBACK_VERIFY_DELAY_S` env var; default 60; override to 5 in non-integration CI runs against stubs).
5. Trigger a new agent invocation for the same role (using `IPromptLoader.load_prompt()` to simulate the per-request fetch).
6. Assert that the resolved `prompt_version` in the post-rollback invocation equals `"sha-v1"`.
7. Assert the total elapsed time from step 3 to step 6 is under 60 seconds.

The test must remain passing when `ROLLBACK_VERIFY_DELAY_S=5` is set and a Langfuse stub is used — enabling CI runs without a live Langfuse instance. The full 60-second timing assertion is validated only when `INTEGRATION_LANGFUSE=1` is set in the environment.

**Tests to write first (TDD)**:
- `test_rollback_propagates_to_agent_invocation_within_60_seconds`: full scenario as above; assert `post_rollback_version == "sha-v1"` and `elapsed < 60`.
- `test_get_active_version_returns_rolled_back_sha_immediately_after_rollback`: assert `get_active_version(role_id, "production") == "sha-v1"` immediately after `rollback()` returns — no delay needed for the Langfuse label query itself.
- `test_invocation_before_rollback_uses_current_production_version`: assert pre-rollback invocation resolves `"sha-v2"`, not the target `"sha-v1"`.
- `test_rollback_of_nonexistent_sha_raises_descriptive_error`: attempt to roll back to a SHA that was never published to Langfuse; assert a `LangfuseLabelError` or `PromptVersionNotFoundError` is raised with a message identifying the unknown version.

**AC covered**: AC-003

---

### TASK-005: Assertion helper and CI documentation · S/no-TDD · tests/integration/prompts/conftest.py, tests/integration/evaluation/conftest.py

Add pytest `conftest.py` fixtures used by TASK-003 and TASK-004 integration tests:

- `langfuse_stub_client`: a fixture providing a lightweight in-memory Langfuse stub that implements `create_prompt`, `update_prompt`, and `get_prompt` with label resolution — allows integration tests to run without a live Langfuse container. This stub is gated by `INTEGRATION_LANGFUSE=0` (default); when `INTEGRATION_LANGFUSE=1`, real client is used.
- `golden_dataset_20_items`: a fixture seeding exactly 20 active `GoldenDatasetItem` rows in the test DB for use by `test_regression_perf.py` (TASK-003).
- `two_prompt_versions`: a fixture for TASK-004 that publishes `sha-v1` and `sha-v2` to the Langfuse stub, labels `sha-v2` as `production`, and tears down after the test.

**AC covered**: enables AC-003, AC-004

## Acceptance Criteria Coverage

- AC-001: Given a PR modifies a prompt and the Tier 2 golden dataset regression detects a >5% degradation on any metric, the CI check fails and the PR is blocked from merging. → TASK-001, TASK-003
- AC-002: Given a prompt regression that degrades 3 metrics by 2%, 4%, and 6% respectively, the CI check fails (the 6% degradation breaches the threshold) even though 2 metrics are within tolerance. → TASK-001
- AC-003: Given `stokai prompts rollback --agent <role> --to-version <sha>` is executed, an agent invocation 60 seconds later uses the specified rolled-back prompt version, confirmed by the `prompt_version` field in the Langfuse trace. → TASK-002, TASK-004
- AC-004: Given the golden dataset contains at least 20 test cases across varied event types, the CI regression run completes in under 5 minutes to avoid blocking the development workflow. → TASK-003, TASK-005

## Acceptance Notes

- AC-003 full timing verification (60-second wait against a live Langfuse instance) is gated behind `INTEGRATION_LANGFUSE=1`. Standard CI runs use the Langfuse stub with `ROLLBACK_VERIFY_DELAY_S=5`. The slow test must be run manually or in a dedicated integration environment before each prompt release.
- AC-004 measures wall-clock time of the regression run including any agent stub invocations. Real Anthropic API calls must not be made during this test; all agent calls must be mocked. Execution time should be validated on CI hardware to confirm the 300-second budget holds under normal load.

## Risks and Notes

- The per-metric gate logic (`delta < -0.05`, not `<= -0.05`) is implemented in PLAN-F-016's `RegressionReport` derived field. TASK-001 unit tests confirm the exact boundary. If PLAN-F-016 changes the comparison operator, TASK-001's `test_exactly_at_threshold_does_not_breach` test will catch the regression immediately.
- The `perf_gate.py` exit code 2 (timing exceeded, metric gate passed) must be treated as a warning in CI, not a hard block, for the first two sprints while baseline timing data is collected. The GitHub Actions step should use `continue-on-error: true` for exit code 2 until a timing baseline is established. This distinction is intentional and must be documented in the CI workflow YAML.
- `ROLLBACK_VERIFY_DELAY_S` must not be set to 0 in any environment — a zero delay bypasses the propagation window and makes the test vacuously pass. The minimum meaningful value is 1 second when using a stub (latency is synchronous), and 60 seconds against a real Langfuse instance.
- The Langfuse stub in `conftest.py` (TASK-005) must faithfully replicate the label-resolution semantics of the real Langfuse SDK: only one version may carry the `production` label at a time; applying `production` to a new version must strip the label from the prior version. Any deviation will cause TASK-004 integration tests to pass falsely against the stub but fail against the real Langfuse instance.
- This plan does not implement an automated rollback trigger — REQ-N-009 explicitly states automated rollback without human command is out of scope. The `stokai prompts rollback` command remains the only rollback path.
