"""WorkflowStructureValidator — enforces the evaluate_quality → narrative_writer tail invariant.

AC-004: evaluate_quality is always second-to-last; narrative_writer is always last.

Each workflow graph builder (PLAN-F-006 through PLAN-F-010) must call
WorkflowStructureValidator.validate() during graph construction. This runs
synchronously at startup so failures are caught before any request is served.
"""
from __future__ import annotations

_REQUIRED_TAIL = ("evaluate_quality", "narrative_writer")


class WorkflowStructureError(RuntimeError):
    """Raised when a workflow node sequence violates the structural invariant.

    AC-004: evaluate_quality must be second-to-last; narrative_writer last.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class WorkflowStructureValidator:
    """Validates that a workflow node sequence ends with the required tail.

    No LangGraph internals dependency — accepts a plain list[str] of node
    names in execution order. Callable at graph-construction time.

    Usage::

        validator = WorkflowStructureValidator()
        validator.validate(["relevance-analyst", "evaluate_quality", "narrative_writer"])
    """

    def validate(self, node_sequence: list[str]) -> None:
        """Assert the sequence ends with ["evaluate_quality", "narrative_writer"].

        The check is position-sensitive: no other nodes may appear after
        narrative_writer, and evaluate_quality must be directly before it.

        Args:
            node_sequence: Ordered list of node names in the workflow graph.

        Raises:
            WorkflowStructureError: If the tail invariant is violated.
        """
        tail_length = len(_REQUIRED_TAIL)

        if len(node_sequence) < tail_length:
            raise WorkflowStructureError(
                f"Workflow node sequence has fewer than {tail_length} nodes "
                f"({len(node_sequence)} given); cannot satisfy invariant "
                f"{list(_REQUIRED_TAIL)}."
            )

        actual_tail = tuple(node_sequence[-tail_length:])
        if actual_tail != _REQUIRED_TAIL:
            raise WorkflowStructureError(
                f"Workflow tail invariant violated. "
                f"Expected last {tail_length} nodes to be {list(_REQUIRED_TAIL)}, "
                f"but got {list(actual_tail)}. "
                f"Full sequence: {node_sequence}"
            )
