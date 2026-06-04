"""
ai.workflows.on_demand.nodes.fetch_company_state — DeterministicNode.

Loads company fundamentals, portfolio position, and latest company_score
via repositories; populates state.company_state.

Raises CompanyNotFoundError if the company is not found in the tenant's scope.
"""
from __future__ import annotations

from src.ai.workflows.state import WorkflowState


class CompanyNotFoundError(Exception):
    """Raised when the requested company cannot be found for the given tenant."""

    def __init__(self, company_id: object, tenant_id: object) -> None:
        super().__init__(
            f"Company {company_id} not found for tenant {tenant_id}"
        )
        self.company_id = company_id
        self.tenant_id = tenant_id


async def fetch_company_state(
    state: WorkflowState,
    *,
    company_repo: object,
) -> WorkflowState:
    """Load company fundamentals from the repository and populate state.company_state.

    Args:
        state: Current workflow state (immutable input).
        company_repo: Repository implementing ICompanyRepository protocol.

    Returns:
        New WorkflowState with company_state populated.

    Raises:
        CompanyNotFoundError: If company not found for the given tenant.
    """
    company_data = await company_repo.get_company_state(
        state.company_id, state.tenant_id
    )

    if company_data is None:
        raise CompanyNotFoundError(
            company_id=state.company_id,
            tenant_id=state.tenant_id,
        )

    return state.model_copy(update={"company_state": company_data})
