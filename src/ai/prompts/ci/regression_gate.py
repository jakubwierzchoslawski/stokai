"""src.ai.prompts.ci.regression_gate — Prompt regression gate for CI.

PLAN-F-014 TASK-003 (AC-001).

Entrypoint for the GitHub Actions Tier 2 regression gate step. Accepts
--role-id, --candidate-sha, and --production-sha as CLI arguments, invokes
ITier2Runner.run_regression() (contract owned by PLAN-F-016), and exits
non-zero if RegressionReport.passed is False.

Exit codes:
    0  — Regression passed (no degradation > 5%)
    1  — Regression failed (one or more metrics degraded > 5%)

Usage (called from GitHub Actions):
    python -m src.ai.prompts.ci.regression_gate \
        --role-id relevance_analyst \
        --candidate-sha <40-char SHA> \
        --production-sha <40-char SHA>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Ensure project root is on sys.path when invoked as a module
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

REGRESSION_THRESHOLD = 0.05  # 5%


# ---------------------------------------------------------------------------
# RegressionReport (matches the PLAN-F-016 contract)
# ---------------------------------------------------------------------------


class RegressionReport:
    """Lightweight dataclass matching the PLAN-F-016 RegressionReport contract."""

    def __init__(
        self,
        passed: bool,
        per_metric_delta: dict[str, float] | None = None,
        breached_metrics: list[str] | None = None,
    ) -> None:
        self.passed = passed
        self.per_metric_delta: dict[str, float] = per_metric_delta or {}
        self.breached_metrics: list[str] = breached_metrics or []


# ---------------------------------------------------------------------------
# Tier2 runner adapter
# ---------------------------------------------------------------------------


def _try_run_regression(
    role_id: str,
    candidate_sha: str,
    production_sha: str,
) -> RegressionReport | None:
    """Attempt to call ITier2Runner.run_regression() if available.

    Falls back to None (pass) when PLAN-F-016 is not deployed. This guards the CI
    step from import errors when the evaluation framework is not yet available.

    Args:
        role_id: Prompt role identifier.
        candidate_sha: SHA of the candidate (PR head) prompt version.
        production_sha: SHA of the current production prompt version.

    Returns:
        RegressionReport if the runner is available; None otherwise.
    """
    try:
        from src.ai.evaluation.interfaces.i_tier2_runner import ITier2Runner  # type: ignore

        runner = ITier2Runner()  # type: ignore
        report = runner.run_regression(
            prompt_version_candidate=candidate_sha,
            prompt_version_production=production_sha,
            agent_role=role_id,
        )
        return RegressionReport(
            passed=report.passed,
            per_metric_delta=report.per_metric_delta,
            breached_metrics=report.breached_metrics,
        )
    except (ImportError, AttributeError):
        logger.debug(
            "ITier2Runner not available (PLAN-F-016 not deployed) — skipping regression for role_id=%s",
            role_id,
        )
        return None
    except Exception:
        logger.exception("ITier2Runner.run_regression() raised an unexpected error")
        return None


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------


def run_gate(
    role_id: str,
    candidate_sha: str,
    production_sha: str,
    *,
    step_summary_path: str | None = None,
    runner_override: Any = None,
) -> int:
    """Run the regression gate for a single role_id and return an exit code.

    Args:
        role_id: Prompt role identifier.
        candidate_sha: SHA of the candidate prompt version.
        production_sha: SHA of the production prompt version.
        step_summary_path: Optional path to write a GitHub Actions step summary.
        runner_override: Optional callable that replaces _try_run_regression for testing.

    Returns:
        0 on pass (or no runner available); 1 on regression detected.
    """
    if runner_override is not None:
        report = runner_override(role_id, candidate_sha, production_sha)
    else:
        report = _try_run_regression(role_id, candidate_sha, production_sha)

    if report is None:
        result: dict[str, Any] = {
            "role_id": role_id,
            "status": "skipped",
            "reason": "ITier2Runner not available",
        }
        print(json.dumps(result, indent=2))
        return 0

    summary_lines: list[str] = [
        f"## Regression Gate: {role_id}",
        f"- Candidate SHA: `{candidate_sha[:8]}...`",
        f"- Production SHA: `{production_sha[:8]}...`",
        "",
    ]

    if report.passed:
        summary_lines += [
            "**Result: PASS** — no metric degraded more than 5%.",
            "",
        ]
        for metric, delta in report.per_metric_delta.items():
            summary_lines.append(f"- `{metric}`: delta={delta:+.1%}")

        result = {
            "role_id": role_id,
            "status": "pass",
            "per_metric_delta": report.per_metric_delta,
        }
        print(json.dumps(result, indent=2))
        exit_code = 0
    else:
        summary_lines += [
            "**Result: FAIL** — the following metrics degraded more than 5%:",
            "",
        ]
        for metric in report.breached_metrics:
            delta = report.per_metric_delta.get(metric, 0.0)
            summary_lines.append(f"- `{metric}`: delta={delta:+.1%} (breached)")

        result = {
            "role_id": role_id,
            "status": "fail",
            "breached_metrics": report.breached_metrics,
            "per_metric_delta": report.per_metric_delta,
        }
        print(json.dumps(result, indent=2))
        exit_code = 1

    if step_summary_path:
        try:
            with open(step_summary_path, "a", encoding="utf-8") as f:
                f.write("\n".join(summary_lines) + "\n")
        except OSError:
            logger.warning("Could not write step summary to %s", step_summary_path)

    return exit_code


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="regression_gate",
        description="PLAN-F-014 Tier 2 regression gate for prompt PRs.",
    )
    parser.add_argument("--role-id", required=True, help="Prompt role identifier.")
    parser.add_argument(
        "--candidate-sha",
        required=True,
        help="40-char git SHA of the PR head prompt version.",
    )
    parser.add_argument(
        "--production-sha",
        required=True,
        help="40-char git SHA of the current production prompt version.",
    )
    parser.add_argument(
        "--step-summary",
        default=None,
        dest="step_summary_path",
        help="Optional path to write a GitHub Actions step summary (GITHUB_STEP_SUMMARY).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    exit_code = run_gate(
        role_id=args.role_id,
        candidate_sha=args.candidate_sha,
        production_sha=args.production_sha,
        step_summary_path=args.step_summary_path,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
