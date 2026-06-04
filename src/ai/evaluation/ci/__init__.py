"""src.ai.evaluation.ci — CI tooling for the evaluation framework.

PLAN-N-009 TASK-003.

Provides perf_gate.py, a thin timing harness that wraps
Tier2RunnerService.run_regression() with a wall-clock timer for use in
GitHub Actions prompt-regression CI workflows.
"""
