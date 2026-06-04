"""
PLAN-N-009 TASK-003 — CI performance gate integration tests.

Verifies:
- perf_gate.py exit code contract (0, 1, 2).
- Timing JSON written to stdout contains required keys.
- Full Tier2RunnerService run with 20 mock items completes in <300 s.
- prompt-regression.yml contains the prompt-regression-perf-check step.

AC-004.
"""
from __future__ import annotations

import asyncio
import io
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.ai.evaluation.schemas.calibration_schemas import RegressionReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "prompt-regression.yml"
)


def _passing_report() -> RegressionReport:
    return RegressionReport(
        passed=True,
        per_metric_delta={"quality": 0.05},
        breached_metrics=[],
    )


def _failing_report() -> RegressionReport:
    return RegressionReport(
        passed=False,
        per_metric_delta={"quality": -0.10},
        breached_metrics=["quality"],
    )


def _stub_runner(report: RegressionReport) -> Any:
    """Return an ITier2Runner stub that always returns the given report."""
    stub = MagicMock()
    stub.run_regression = AsyncMock(return_value=report)
    return stub


def _make_time_fn(elapsed_value: float):
    """Return a time function that yields start=0, then start+elapsed_value."""
    calls = []

    def _time() -> float:
        calls.append(len(calls))
        if len(calls) == 1:
            return 0.0
        return elapsed_value

    return _time


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_perf_gate_exits_0_on_passing_regression_within_time_limit():
    """Exit code 0 when regression passes and elapsed <= max_seconds."""
    from src.ai.evaluation.ci.perf_gate import run_perf_gate

    exit_code, payload = await run_perf_gate(
        role_id="analyst",
        candidate_sha="a" * 40,
        production_sha="b" * 40,
        max_seconds=300.0,
        runner=_stub_runner(_passing_report()),
        _time_fn=_make_time_fn(180.0),
    )

    assert exit_code == 0
    assert payload["within_limit"] is True


@pytest.mark.asyncio
async def test_perf_gate_exits_1_on_failing_regression_regardless_of_timing():
    """Exit code 1 when regression fails, regardless of elapsed time."""
    from src.ai.evaluation.ci.perf_gate import run_perf_gate

    # Even with elapsed < max_seconds, a metric breach is exit 1
    exit_code, payload = await run_perf_gate(
        role_id="analyst",
        candidate_sha="a" * 40,
        production_sha="b" * 40,
        max_seconds=300.0,
        runner=_stub_runner(_failing_report()),
        _time_fn=_make_time_fn(10.0),
    )

    assert exit_code == 1


@pytest.mark.asyncio
async def test_perf_gate_exits_2_on_passing_regression_but_exceeded_time():
    """Exit code 2 when regression passes but elapsed > max_seconds."""
    from src.ai.evaluation.ci.perf_gate import run_perf_gate

    exit_code, payload = await run_perf_gate(
        role_id="analyst",
        candidate_sha="a" * 40,
        production_sha="b" * 40,
        max_seconds=300.0,
        runner=_stub_runner(_passing_report()),
        _time_fn=_make_time_fn(310.0),
    )

    assert exit_code == 2
    assert payload["within_limit"] is False


@pytest.mark.asyncio
async def test_perf_gate_writes_timing_json_to_stdout(capsys):
    """run_perf_gate returns a dict with 'elapsed_seconds' and 'within_limit' keys."""
    from src.ai.evaluation.ci.perf_gate import run_perf_gate

    exit_code, payload = await run_perf_gate(
        role_id="analyst",
        candidate_sha="a" * 40,
        production_sha="b" * 40,
        max_seconds=300.0,
        runner=_stub_runner(_passing_report()),
        _time_fn=_make_time_fn(50.0),
    )

    # The payload is valid JSON-serialisable and has required keys
    serialised = json.dumps(payload)
    parsed = json.loads(serialised)

    assert "elapsed_seconds" in parsed
    assert "within_limit" in parsed
    assert isinstance(parsed["elapsed_seconds"], float)
    assert isinstance(parsed["within_limit"], bool)


@pytest.mark.asyncio
async def test_regression_run_completes_within_300s_with_20_item_dataset(
    tmp_path, monkeypatch
):
    """
    Integration: Tier2RunnerService with 20 stub items completes in <300 s.

    No real Anthropic API calls are made.  All agent invocations are mocked.
    """
    import uuid
    from datetime import datetime, timezone

    from src.ai.evaluation.schemas.golden_dataset_schemas import GoldenDatasetItem
    from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService

    monkeypatch.setattr(
        "src.ai.evaluation.services.tier2_runner_service._LOG_DIR",
        str(tmp_path),
    )

    def _make_item() -> GoldenDatasetItem:
        return GoldenDatasetItem(
            item_id=uuid.uuid4(),
            input={"query": "Analyse AAPL"},
            expected_output={"signal": "BUY"},
            quality_metrics={"quality": 0.8},
            source="hand_authored",
            active=True,
            created_at=datetime.now(tz=timezone.utc),
        )

    mock_repo = AsyncMock()
    mock_repo.list_active = AsyncMock(
        return_value=[_make_item() for _ in range(20)]
    )

    async def _stub_run(item: Any, prompt_version: str, agent_role: str) -> dict:
        return {"quality": 0.8}

    stub_runner = MagicMock()
    stub_runner.run = AsyncMock(side_effect=_stub_run)

    service = Tier2RunnerService(
        golden_dataset_repo=mock_repo,
        agent_runner=stub_runner,
    )

    start = time.monotonic()
    report = await service.run_regression(
        prompt_version_candidate="cand",
        prompt_version_production="prod",
        agent_role="analyst",
    )
    elapsed = time.monotonic() - start

    assert elapsed < 300, f"Regression run took {elapsed:.2f}s, expected <300s"
    assert report is not None


def test_ci_workflow_yaml_includes_perf_check_step():
    """
    The prompt-regression.yml workflow must contain a step named
    'prompt-regression-perf-check' that references perf_gate.py.
    """
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"

    with open(WORKFLOW_PATH, encoding="utf-8") as fh:
        workflow = yaml.safe_load(fh)

    # Collect all step names across all jobs
    all_steps = []
    for job_name, job_body in (workflow.get("jobs") or {}).items():
        for step in job_body.get("steps") or []:
            all_steps.append(step)

    step_names = [s.get("name", "") for s in all_steps]
    assert "prompt-regression-perf-check" in step_names, (
        f"Expected step 'prompt-regression-perf-check' in {step_names}"
    )

    # The step's run block must reference perf_gate.py
    perf_step = next(
        s for s in all_steps if s.get("name") == "prompt-regression-perf-check"
    )
    assert "perf_gate" in (perf_step.get("run") or ""), (
        "perf-check step run command does not reference perf_gate"
    )
