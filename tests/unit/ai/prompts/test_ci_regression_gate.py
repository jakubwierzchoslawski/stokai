"""Tests for src.ai.prompts.ci.regression_gate — TDD for PLAN-F-014 TASK-003 (AC-001).

Tests follow the plan spec:
- test_regression_gate_exits_0_when_report_passed
- test_regression_gate_exits_1_when_report_failed
- test_regression_gate_emits_summary_for_each_breached_metric
- test_ci_workflow_yaml_triggers_on_prompts_path_change
"""
from __future__ import annotations

import json
from pathlib import Path
from io import StringIO
from unittest.mock import patch

import pytest
import yaml

from src.ai.prompts.ci.regression_gate import RegressionReport, run_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_runner(role_id, candidate_sha, production_sha):
    return RegressionReport(
        passed=True,
        per_metric_delta={"factual_grounding": 0.01},
        breached_metrics=[],
    )


def _failing_runner(role_id, candidate_sha, production_sha):
    return RegressionReport(
        passed=False,
        per_metric_delta={"factual_grounding": -0.08},
        breached_metrics=["factual_grounding"],
    )


def _no_runner(role_id, candidate_sha, production_sha):
    return None


# ---------------------------------------------------------------------------
# Tests: run_gate exit codes
# ---------------------------------------------------------------------------


class TestRegressionGateExitCodes:
    def test_regression_gate_exits_0_when_report_passed(self, capsys) -> None:
        """run_gate returns 0 when ITier2Runner returns passed=True."""
        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_passing_runner,
        )
        assert exit_code == 0

    def test_regression_gate_exits_1_when_report_failed(self, capsys) -> None:
        """run_gate returns 1 when ITier2Runner returns passed=False."""
        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_failing_runner,
        )
        assert exit_code == 1

    def test_regression_gate_exits_0_when_no_runner_available(self, capsys) -> None:
        """run_gate returns 0 when ITier2Runner is not available (None returned)."""
        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_no_runner,
        )
        assert exit_code == 0


# ---------------------------------------------------------------------------
# Tests: summary output
# ---------------------------------------------------------------------------


class TestRegressionGateSummary:
    def test_regression_gate_emits_summary_for_each_breached_metric(
        self, capsys, tmp_path: Path
    ) -> None:
        """run_gate writes a summary containing the breached metric name."""
        summary_path = tmp_path / "step_summary.md"

        run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_failing_runner,
            step_summary_path=str(summary_path),
        )

        assert summary_path.exists()
        content = summary_path.read_text()
        assert "factual_grounding" in content

    def test_regression_gate_pass_summary_contains_pass_indicator(
        self, capsys, tmp_path: Path
    ) -> None:
        """run_gate writes 'PASS' summary when report passes."""
        summary_path = tmp_path / "step_summary.md"

        run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_passing_runner,
            step_summary_path=str(summary_path),
        )

        content = summary_path.read_text()
        assert "PASS" in content

    def test_regression_gate_fail_summary_contains_fail_indicator(
        self, capsys, tmp_path: Path
    ) -> None:
        """run_gate writes 'FAIL' summary when report fails."""
        summary_path = tmp_path / "step_summary.md"

        run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_failing_runner,
            step_summary_path=str(summary_path),
        )

        content = summary_path.read_text()
        assert "FAIL" in content

    def test_stdout_output_is_valid_json(self, capsys) -> None:
        """run_gate prints a valid JSON report to stdout."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_passing_runner,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["role_id"] == "relevance_analyst"
        assert data["status"] == "pass"

    def test_breached_metrics_appear_in_json_output(self, capsys) -> None:
        """Failing run_gate JSON output contains breached_metrics list."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha="a" * 40,
            production_sha="b" * 40,
            runner_override=_failing_runner,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "factual_grounding" in data["breached_metrics"]


# ---------------------------------------------------------------------------
# Tests: CI workflow YAML structure
# ---------------------------------------------------------------------------


class TestCiWorkflowYaml:
    @pytest.fixture(scope="class")
    def workflow(self) -> dict:
        workflow_path = (
            Path(__file__).resolve().parents[4]
            / ".github"
            / "workflows"
            / "prompt-regression.yml"
        )
        with open(workflow_path) as f:
            return yaml.safe_load(f)

    def test_ci_workflow_yaml_triggers_on_pull_request(self, workflow: dict) -> None:
        """Workflow triggers on pull_request events.

        Note: PyYAML parses the bare 'on:' key as Python True (boolean), so we look
        for either the string 'on' or the boolean True key.
        """
        # PyYAML parses 'on:' as True (the bare word 'on' is YAML boolean True)
        trigger_key = True if True in workflow else "on"
        triggers = workflow[trigger_key]
        assert "pull_request" in triggers

    def test_ci_workflow_yaml_triggers_on_prompts_path_change(self, workflow: dict) -> None:
        """Workflow paths filter includes 'prompts/**'."""
        trigger_key = True if True in workflow else "on"
        triggers = workflow[trigger_key]
        pr_config = triggers["pull_request"]
        paths = pr_config.get("paths", [])
        assert any("prompts" in p for p in paths), f"No prompts path filter in: {paths}"

    def test_ci_workflow_has_regression_gate_step(self, workflow: dict) -> None:
        """Workflow has a step that invokes regression_gate."""
        job = workflow["jobs"]["prompt-regression"]
        steps = job["steps"]
        gate_steps = [
            s for s in steps
            if "regression_gate" in str(s.get("run", ""))
            or "regression" in str(s.get("name", "")).lower()
        ]
        assert len(gate_steps) >= 1, "No regression gate step found in workflow"
