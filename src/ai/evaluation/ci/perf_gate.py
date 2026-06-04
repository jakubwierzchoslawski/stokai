"""
src.ai.evaluation.ci.perf_gate — CI timing harness for the Tier-2 regression gate.

PLAN-N-009 TASK-003.

CLI contract
------------
python -m src.ai.evaluation.ci.perf_gate \\
    --role-id <role_id> \\
    --candidate-sha <sha> \\
    --production-sha <sha> \\
    [--max-seconds 300]

Exit codes
----------
0  Regression passed AND elapsed <= max_seconds.
1  Regression failed (metric breach).  Timing is not evaluated.
2  Regression passed BUT elapsed > max_seconds.

Stdout (always)
---------------
JSON: {"elapsed_seconds": <float>, "within_limit": <bool>}
Written even when exit code is 1 (elapsed up to that point is reported).

Design notes
------------
- Uses time.monotonic() for wall-clock measurement (unaffected by NTP drift).
- Tier2RunnerService is instantiated with a NullGoldenDatasetRepository and the
  default AgentRunner stub unless injected via the `runner` parameter of
  run_perf_gate().  Production callers should wire real dependencies via the
  DI container before calling run_perf_gate().
- The module is importable without side effects; all execution happens inside
  run_perf_gate() / main().
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from src.ai.evaluation.interfaces.i_tier2_runner import ITier2Runner
from src.ai.evaluation.schemas.calibration_schemas import RegressionReport


# ---------------------------------------------------------------------------
# Core timing harness (injectable for tests)
# ---------------------------------------------------------------------------


async def run_perf_gate(
    *,
    role_id: str,
    candidate_sha: str,
    production_sha: str,
    max_seconds: float = 300.0,
    runner: ITier2Runner | None = None,
    _time_fn: Any = None,
) -> tuple[int, dict[str, Any]]:
    """
    Run the regression gate with a wall-clock timer.

    Parameters
    ----------
    role_id:
        Agent role identifier passed to run_regression().
    candidate_sha:
        Candidate prompt version SHA.
    production_sha:
        Production prompt version SHA.
    max_seconds:
        Wall-clock time limit in seconds.  Default 300.
    runner:
        ITier2Runner implementation.  When None, a default Tier2RunnerService
        backed by an empty in-memory dataset is used (useful for unit tests
        that inject a stub via this parameter).
    _time_fn:
        Optional callable substituting time.monotonic for deterministic tests.
        Must return float seconds.  Injected by unit tests; production code
        leaves this as None (resolved to time.monotonic internally).

    Returns
    -------
    (exit_code, timing_payload)
        exit_code: 0, 1, or 2 as per the CLI contract.
        timing_payload: {"elapsed_seconds": float, "within_limit": bool}
    """
    if runner is None:
        # Lazy import to avoid circular dependency at module level
        from src.ai.evaluation.services.tier2_runner_service import Tier2RunnerService
        from unittest.mock import AsyncMock

        null_repo = AsyncMock()
        null_repo.list_active = AsyncMock(return_value=[])
        runner = Tier2RunnerService(golden_dataset_repo=null_repo)

    _monotonic = _time_fn if _time_fn is not None else time.monotonic

    start = _monotonic()
    try:
        report: RegressionReport = await runner.run_regression(
            prompt_version_candidate=candidate_sha,
            prompt_version_production=production_sha,
            agent_role=role_id,
        )
    finally:
        elapsed = _monotonic() - start

    within_limit = elapsed <= max_seconds
    timing_payload: dict[str, Any] = {
        "elapsed_seconds": elapsed,
        "within_limit": within_limit,
    }

    if not report.passed:
        exit_code = 1
    elif not within_limit:
        exit_code = 2
    else:
        exit_code = 0

    return exit_code, timing_payload


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CI timing harness for the Tier-2 prompt regression gate.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--role-id", required=True, help="Agent role identifier.")
    parser.add_argument("--candidate-sha", required=True, help="Candidate prompt SHA.")
    parser.add_argument("--production-sha", required=True, help="Production prompt SHA.")
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=300.0,
        help="Wall-clock time limit.  Exit 2 when exceeded.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns exit code (0, 1, or 2)."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    exit_code, timing_payload = asyncio.run(
        run_perf_gate(
            role_id=args.role_id,
            candidate_sha=args.candidate_sha,
            production_sha=args.production_sha,
            max_seconds=args.max_seconds,
        )
    )

    print(json.dumps(timing_payload))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
