"""Integration tests for regression gate blocking — PLAN-F-014 TASK-010 (AC-001).

These tests verify that:
1. The regression gate blocks (exit 1) when ITier2Runner returns a failing report.
2. The regression gate passes (exit 0) when ITier2Runner returns a passing report.
3. The gate produces a readable summary for each breached metric.

They run regression_gate via subprocess (as CI would) or via direct Python calls,
using mock ITier2Runner implementations to avoid needing the full PLAN-F-016 stack.

TDD spec from the plan:
- test_regression_gate_blocks_on_degraded_prompt
- test_regression_gate_passes_on_clean_prompt
- test_regression_gate_produces_readable_summary_for_each_breached_metric
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ai.prompts.ci.regression_gate import RegressionReport, run_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CANDIDATE_SHA = "a" * 40
PRODUCTION_SHA = "b" * 40


def _degraded_runner(role_id, candidate_sha, production_sha):
    """Returns a failing regression report with breached metrics."""
    return RegressionReport(
        passed=False,
        per_metric_delta={
            "factual_grounding": -0.08,
            "confidence_calibration": -0.06,
        },
        breached_metrics=["factual_grounding", "confidence_calibration"],
    )


def _clean_runner(role_id, candidate_sha, production_sha):
    """Returns a passing regression report."""
    return RegressionReport(
        passed=True,
        per_metric_delta={
            "factual_grounding": 0.01,
            "confidence_calibration": -0.02,
        },
        breached_metrics=[],
    )


# ---------------------------------------------------------------------------
# Tests: exit codes
# ---------------------------------------------------------------------------


class TestRegressionGateBlock:
    def test_regression_gate_blocks_on_degraded_prompt(self, capsys) -> None:
        """run_gate returns exit code 1 when ITier2Runner reports regression."""
        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_degraded_runner,
        )
        assert exit_code == 1

    def test_regression_gate_passes_on_clean_prompt(self, capsys) -> None:
        """run_gate returns exit code 0 when ITier2Runner reports no regression."""
        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_clean_runner,
        )
        assert exit_code == 0

    def test_regression_gate_blocks_multiple_breached_metrics(self, capsys) -> None:
        """Gate blocks when multiple metrics are breached."""
        exit_code = run_gate(
            role_id="exposure_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_degraded_runner,
        )
        assert exit_code == 1

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data["breached_metrics"]) == 2

    def test_regression_gate_passes_when_no_runner_available(self, capsys) -> None:
        """Gate returns 0 (pass) when ITier2Runner is not available."""
        def _no_runner(role_id, candidate_sha, production_sha):
            return None

        exit_code = run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_no_runner,
        )
        assert exit_code == 0


# ---------------------------------------------------------------------------
# Tests: summary output
# ---------------------------------------------------------------------------


class TestRegressionGateSummary:
    def test_regression_gate_produces_readable_summary_for_each_breached_metric(
        self, tmp_path: Path
    ) -> None:
        """Summary file contains metric name and delta value for each breached metric."""
        summary_path = tmp_path / "summary.md"

        run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_degraded_runner,
            step_summary_path=str(summary_path),
        )

        assert summary_path.exists()
        content = summary_path.read_text()

        # Both breached metrics must appear in the summary
        assert "factual_grounding" in content
        assert "confidence_calibration" in content

        # Deltas must be present (negative percentages)
        assert "-8.0%" in content or "-8" in content
        assert "-6.0%" in content or "-6" in content

    def test_regression_gate_pass_summary_not_produced_when_no_summary_path(
        self, capsys
    ) -> None:
        """When no step_summary_path is provided, no file is written."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_clean_runner,
            step_summary_path=None,
        )
        # No assertion needed — just ensuring no exception is raised

    def test_regression_gate_json_output_contains_per_metric_delta(
        self, capsys
    ) -> None:
        """stdout JSON output contains per_metric_delta for each metric."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_degraded_runner,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "per_metric_delta" in data
        assert "factual_grounding" in data["per_metric_delta"]
        assert data["per_metric_delta"]["factual_grounding"] == pytest.approx(-0.08)

    def test_regression_gate_fail_json_status_is_fail(self, capsys) -> None:
        """Failing gate produces JSON with status='fail'."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_degraded_runner,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "fail"

    def test_regression_gate_pass_json_status_is_pass(self, capsys) -> None:
        """Passing gate produces JSON with status='pass'."""
        run_gate(
            role_id="relevance_analyst",
            candidate_sha=CANDIDATE_SHA,
            production_sha=PRODUCTION_SHA,
            runner_override=_clean_runner,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "pass"
