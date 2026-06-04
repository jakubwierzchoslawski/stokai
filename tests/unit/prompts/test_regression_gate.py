"""Tests for scripts/regression_gate.py — TDD for PLAN-F-014 TASK-008."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import regression_gate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prompts_base(tmp_path: Path) -> Path:
    """Create all 15 canonical prompt stub files."""
    for subdir, names in [
        (
            "agents",
            [
                "exposure_analyst",
                "historical_context",
                "anomaly_detector",
                "recommendation",
                "narrative_writer",
                "morning_brief_analyst",
                "watchlist_analyst",
                "earnings_analyst",
                "qa_analyst",
            ],
        ),
        ("evaluators", ["recommendation_judge", "factuality_judge", "calibration_judge"]),
        ("classifiers", ["event_classifier", "ticker_extractor", "sentiment_analyzer"]),
    ]:
        d = tmp_path / "prompts" / subdir
        d.mkdir(parents=True)
        for name in names:
            (d / f"{name}.md").write_text(f"# {name}\n\n## System\nYou are {name}.\n")
    return tmp_path / "prompts"


# ---------------------------------------------------------------------------
# Tests: check_regression
# ---------------------------------------------------------------------------


class TestCheckRegression:
    def test_returns_no_regression_when_below_threshold(self) -> None:
        """check_regression returns no_regression for small regression pct."""
        result = {
            "sufficient_data": True,
            "regression_pct": 0.02,  # 2% — below 5% threshold
        }
        status, should_fail = regression_gate.check_regression(result)

        assert status == "no_regression"
        assert should_fail is False

    def test_returns_insufficient_data_when_no_result(self) -> None:
        """check_regression returns insufficient_data when result is None."""
        status, should_fail = regression_gate.check_regression(None)

        assert status == "insufficient_data"
        assert should_fail is False

    def test_returns_insufficient_data_when_not_sufficient(self) -> None:
        """check_regression returns insufficient_data when sufficient_data=False."""
        result = {"sufficient_data": False, "regression_pct": 0.10}
        status, should_fail = regression_gate.check_regression(result)

        assert status == "insufficient_data"
        assert should_fail is False

    def test_returns_regression_detected_when_above_threshold(self) -> None:
        """check_regression returns regression_detected and should_fail=True."""
        result = {
            "sufficient_data": True,
            "regression_pct": 0.08,  # 8% — above 5% threshold
        }
        status, should_fail = regression_gate.check_regression(result)

        assert status == "regression_detected"
        assert should_fail is True

    def test_returns_regression_at_exact_threshold_boundary(self) -> None:
        """Exactly 5% is NOT a regression (> vs >=)."""
        result = {"sufficient_data": True, "regression_pct": 0.05}
        status, should_fail = regression_gate.check_regression(result)

        # 0.05 > 0.05 is False → no regression
        assert status == "no_regression"
        assert should_fail is False


# ---------------------------------------------------------------------------
# Tests: run()
# ---------------------------------------------------------------------------


class TestRun:
    def test_exits_0_when_no_regression(
        self,
        prompts_base: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run() returns 0 when Tier2RunnerService reports no regression."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")

        regression_result = {"sufficient_data": True, "regression_pct": 0.01}

        with patch.object(
            regression_gate,
            "_try_run_regression",
            return_value=regression_result,
        ):
            exit_code = regression_gate.run(prompts_root=prompts_base)

        assert exit_code == 0

    def test_exits_1_when_regression_detected(
        self,
        prompts_base: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run() returns 1 when Tier2RunnerService detects >5% regression."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")

        regression_result = {"sufficient_data": True, "regression_pct": 0.12}

        with patch.object(
            regression_gate,
            "_try_run_regression",
            return_value=regression_result,
        ):
            exit_code = regression_gate.run(prompts_root=prompts_base)

        assert exit_code == 1

    def test_exits_0_when_insufficient_data(
        self,
        prompts_base: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run() returns 0 when Tier2RunnerService has insufficient data."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")

        with patch.object(
            regression_gate,
            "_try_run_regression",
            return_value=None,  # No regression service available
        ):
            exit_code = regression_gate.run(prompts_root=prompts_base)

        assert exit_code == 0

    def test_run_loads_all_15_prompts(
        self,
        prompts_base: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run() successfully loads all 15 canonical prompt files."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")

        with patch.object(
            regression_gate,
            "_try_run_regression",
            return_value=None,
        ):
            exit_code = regression_gate.run(prompts_root=prompts_base)

        # Should succeed (exit 0) when all 15 files are present
        assert exit_code == 0

    def test_run_exits_1_on_missing_prompt(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """run() exits 1 when a canonical prompt file is missing."""
        monkeypatch.setenv("PROMPT_SHA_FALLBACK", "true")
        # Create only partial set of files — omit several
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "exposure_analyst.md").write_text("# EA")
        # Do NOT create all 15 files

        with pytest.raises(SystemExit) as exc_info:
            regression_gate.run(prompts_root=tmp_path)

        assert exc_info.value.code == 1
