"""
ai.workflows.earnings_brief.nodes.fetch_company_state — DeterministicNode.

Loads company fundamentals, portfolio position, and latest company_score entries.

PLAN-F-009 TASK-004
"""
from __future__ import annotations

import logging
from typing import Any

from src.ai.workflows.earnings_brief.state import EarningsBriefState

logger = logging.getLogger(__name__)


class CompanyNotFoundError(Exception):
    """Raised when company does not exist for the tenant."""

    def __init__(self, company_id: Any, tenant_id: Any) -> None:
        super().__init__(
            f"Company {company_id} not found for tenant {tenant_id}"
        )
        self.company_id = company_id
        self.tenant_id = tenant_id


async def fetch_company_state(
    state: EarningsBriefState,
    ctx: Any,  # NodeContext
) -> EarningsBriefState:
    """DeterministicNode: fetch company fundamentals, position, and scores.

    Populates state.company_state with:
      - company: company ORM data dict
      - position: current portfolio position dict (if any)
      - scores: latest company_score entries list

    Args:
        state: Current EarningsBriefState.
        ctx: NodeContext with injected repositories.

    Returns:
        Updated EarningsBriefState with company_state populated.

    Raises:
        CompanyNotFoundError: If company does not exist for the tenant.
    """
    logger.debug(
        "fetch_company_state: company_id=%s tenant_id=%s",
        state.company_id,
        state.tenant_id,
    )

    company_data: dict[str, Any] = {}

    # Fetch company fundamentals
    if ctx.company_repo is not None:
        company = await ctx.company_repo.get(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
        )
        if company is None:
            raise CompanyNotFoundError(state.company_id, state.tenant_id)
        company_data["company"] = (
            company.model_dump() if hasattr(company, "model_dump") else dict(company)
        )
    else:
        company_data["company"] = {"company_id": str(state.company_id), "stub": True}

    # Fetch portfolio position
    if ctx.position_repo is not None:
        position = await ctx.position_repo.get_for_company(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
        )
        company_data["position"] = (
            position.model_dump() if position and hasattr(position, "model_dump")
            else (dict(position) if position else None)
        )
    else:
        company_data["position"] = None

    # Fetch company scores
    if ctx.company_score_repo is not None:
        scores = await ctx.company_score_repo.list_latest(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
        )
        company_data["scores"] = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s)
            for s in scores
        ]
    else:
        company_data["scores"] = []

    return state.model_copy(update={"company_state": company_data})
