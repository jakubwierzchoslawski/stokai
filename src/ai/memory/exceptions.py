"""
Domain exceptions for the memory subsystem.
"""
from __future__ import annotations


class EvidenceGateError(Exception):
    """
    Raised when attempting to commit a semantic fact whose evidence_count
    has not yet reached the minimum threshold (default: 3).
    """

    def __init__(self, staging_id, current_count: int, required: int = 3) -> None:
        super().__init__(
            f"Staging row {staging_id} has evidence_count={current_count}, "
            f"minimum required is {required}."
        )
        self.staging_id = staging_id
        self.current_count = current_count
        self.required = required
