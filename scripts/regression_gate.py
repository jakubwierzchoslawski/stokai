#!/usr/bin/env python
"""scripts/regression_gate.py — Prompt regression gate for CI.

PLAN-F-014 TASK-008.

Loads all 15 canonical prompt files, optionally runs regression via
Tier2RunnerService (if available), and emits a JSON report to stdout.

Exit codes:
    0  — No regression detected OR insufficient data
    1  — Regression detected (>5% degradation in any metric)

Usage:
    python scripts/regression_gate.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path so `src` can be imported
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.prompts.prompt_loader import GitPromptLoader
from src.ai.prompts.langfuse_publisher import CANONICAL_ROLE_IDS

logger = logging.getLogger(__name__)

PROMPTS_ROOT = _PROJECT_ROOT / "prompts"
REGRESSION_THRESHOLD = 0.05  # 5%


# ---------------------------------------------------------------------------
# Tier2RunnerService adapter (optional dependency)
# ---------------------------------------------------------------------------


def _try_run_regression() -> dict[str, Any] | None:
    """Attempt to call Tier2RunnerService.run_regression() if available.

    Returns:
        Regression result dict, or None if the service is not available
        or returns insufficient data.
    """
    try:
        from src.ai.evaluation.tier2_runner import Tier2RunnerService  # type: ignore
        service = Tier2RunnerService()
        return service.run_regression()  # type: ignore
    except (ImportError, AttributeError):
        logger.debug("Tier2RunnerService not available — skipping regression run")
        return None
    except Exception:
        logger.exception("Tier2RunnerService.run_regression() failed")
        return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def load_all_prompts(loader: GitPromptLoader) -> dict[str, str]:
    """Load all 15 canonical prompts and return {role_id: sha} mapping.

    Args:
        loader: GitPromptLoader instance.

    Returns:
        Dict mapping role_id to version_sha for all successfully loaded prompts.

    Raises:
        SystemExit(1): If any canonical prompt file is missing.
    """
    loaded: dict[str, str] = {}
    missing: list[str] = []

    for role_id in CANONICAL_ROLE_IDS:
        try:
            pf = loader.load_prompt(role_id)
            loaded[role_id] = pf.sha
        except FileNotFoundError:
            missing.append(role_id)

    if missing:
        report = {
            "status": "error",
            "message": f"Missing prompt files: {missing}",
            "missing": missing,
        }
        print(json.dumps(report, indent=2))
        sys.exit(1)

    return loaded


def check_regression(regression_result: dict[str, Any] | None) -> tuple[str, bool]:
    """Evaluate the regression result from Tier2RunnerService.

    Args:
        regression_result: Dict returned by run_regression(), or None.

    Returns:
        Tuple of (status_string, should_fail).
        status is one of: "no_regression", "regression_detected", "insufficient_data"
        should_fail is True only when regression is detected (>5% degradation).
    """
    if regression_result is None:
        return "insufficient_data", False

    # Expect a dict like {"sufficient_data": bool, "regression_pct": float, ...}
    sufficient = regression_result.get("sufficient_data", False)
    if not sufficient:
        return "insufficient_data", False

    regression_pct = float(regression_result.get("regression_pct", 0.0))
    if regression_pct > REGRESSION_THRESHOLD:
        return "regression_detected", True

    return "no_regression", False


def run(prompts_root: Path = PROMPTS_ROOT) -> int:
    """Main entry point — returns exit code.

    Args:
        prompts_root: Root of the prompts directory tree.

    Returns:
        0 on no regression or insufficient data, 1 on regression detected.
    """
    loader = GitPromptLoader(prompts_root=prompts_root)
    sha_map = load_all_prompts(loader)

    regression_result = _try_run_regression()
    status, should_fail = check_regression(regression_result)

    report: dict[str, Any] = {
        "status": status,
        "prompts_checked": len(sha_map),
        "prompt_shas": sha_map,
        "regression_threshold_pct": REGRESSION_THRESHOLD * 100,
    }

    if regression_result is not None:
        report["regression_result"] = regression_result

    print(json.dumps(report, indent=2))

    if should_fail:
        logger.error("Prompt regression detected — failing CI gate")
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(run())
