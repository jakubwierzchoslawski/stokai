"""
IMemoryService — abstract interface for the unified memory service.

Aggregates all four memory layers behind a single coherent facade.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from src.ai.memory.schemas.episodic_schemas import (
    AgentInvocation,
    AgentInvocationCreate,
    ToolCall,
    ToolCallCreate,
    WorkflowRun,
)
from src.ai.memory.schemas.semantic_schemas import SemanticFact, SemanticFactStaging, SemanticFactStagingCreate
from src.ai.memory.schemas.procedural_schemas import ProceduralPattern
from src.ai.memory.schemas.feedback_schemas import UserFeedback, UserFeedbackCreate


class WorkflowContext:
    """Minimal context object required to start a workflow run."""

    def __init__(
        self,
        workflow_type: str,
        tenant_id: UUID,
        langfuse_trace_id: str | None = None,
    ) -> None:
        self.workflow_type = workflow_type
        self.tenant_id = tenant_id
        self.langfuse_trace_id = langfuse_trace_id


class IMemoryService(ABC):
    """Abstract facade for all four memory layers."""

    @abstractmethod
    async def record_workflow_start(self, ctx: WorkflowContext) -> WorkflowRun:
        """Insert a new workflow_run row and return the entity."""
        ...

    @abstractmethod
    async def record_workflow_end(
        self,
        workflow_id: UUID,
        status: str,
        cost_usd: float,
        final_state: dict,
    ) -> None:
        """Update workflow completion columns (status, completed_at, cost_usd, final_state)."""
        ...

    @abstractmethod
    async def record_agent_invocation(
        self, inv: AgentInvocationCreate
    ) -> AgentInvocation:
        """Insert an agent_invocation row."""
        ...

    @abstractmethod
    async def record_tool_call(self, call: ToolCallCreate) -> ToolCall:
        """Insert a tool_call row."""
        ...

    @abstractmethod
    async def propose_semantic_fact(
        self, fact: SemanticFactStagingCreate
    ) -> SemanticFactStaging:
        """
        Submit a candidate semantic fact.

        Stages the fact, increments evidence, and commits to semantic_fact
        when evidence_count reaches EVIDENCE_GATE_MIN_COUNT.
        Returns the staging or committed schema along with a committed flag.
        """
        ...

    @abstractmethod
    async def query_semantic_memory(
        self, query_embedding: list[float], limit: int
    ) -> list[SemanticFact]:
        """Return the nearest committed semantic facts by cosine similarity."""
        ...

    @abstractmethod
    async def get_procedural_patterns(
        self, context_tags: list[str], agent_role: str
    ) -> list[ProceduralPattern]:
        """Return approved, active procedural patterns for the given tags and agent."""
        ...

    @abstractmethod
    async def record_user_feedback(self, feedback: UserFeedbackCreate) -> UserFeedback:
        """Append a user feedback row (any authenticated role)."""
        ...
