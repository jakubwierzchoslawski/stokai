"""Tool Library — typed tool implementations (ARCHITECTURE.md §8).

Tools expose typed Pydantic I/O interfaces and are the exclusive means by
which agents interact with data (P-04 Agent-Tool Boundary).

Registered tools:
    GetEventExposureScoreTool — read-only scored event exposure query

Each tool:
    - Accepts a Pydantic input model
    - Returns a Pydantic output model
    - Is scoped to tenant_id (no cross-tenant access)
    - Returns at most 50 rows (REQ-N-005)
    - Never mutates score_records (read-only)
"""
from src.workflows.tools.score_tool import GetEventExposureScoreTool

__all__ = [
    "GetEventExposureScoreTool",
]
