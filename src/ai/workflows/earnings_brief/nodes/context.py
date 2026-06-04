"""
ai.workflows.earnings_brief.nodes.context — NodeContext dataclass.

Holds constructor-injected repository dependencies for DeterministicNodes.

PLAN-F-009 TASK-004
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeContext:
    """Injectable context holding repository dependencies for DeterministicNodes.

    All repositories are optional to allow partial stub injection in tests.
    """
    company_repo: Any = None        # ICompanyRepository
    earnings_repo: Any = None       # IEarningsEventRepository (earnings_event table)
    macro_repo: Any = None          # IMacroIndicatorRepository (FRED cache)
    position_repo: Any = None       # IPositionRepository
    company_score_repo: Any = None  # ICompanyScoreRepository
