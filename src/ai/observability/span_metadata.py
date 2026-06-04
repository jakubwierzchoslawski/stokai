"""
SpanMetadata — standard field set attached to every Langfuse trace and span.

This frozen dataclass is the single source of truth for the 14 observability
fields defined in Architecture §12.4.  None-valued optional fields are skipped
when serialising to the Langfuse SDK to avoid polluting the Langfuse UI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class SpanMetadata:
    """Standard metadata attached to every workflow trace and agent span."""

    # Required context fields
    workflow_id: UUID
    workflow_type: str
    tenant_id: UUID
    user_id: UUID

    # Optional agent-level fields
    agent_role_id: str | None = None
    prompt_version: str | None = None       # git blob SHA
    model_used: str | None = None
    confidence: float | None = None
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    tools_called: list[str] | None = None
    state_snapshot_ref: str | None = None   # opaque checkpoint reference

    def to_langfuse_metadata(self) -> dict[str, Any]:
        """Return a dict suitable for passing to the Langfuse SDK.

        None-valued fields are omitted so they do not appear as null entries
        in the Langfuse UI.  UUIDs are serialised to strings.
        """
        raw = asdict(self)
        result: dict[str, Any] = {}
        for key, value in raw.items():
            if value is None:
                continue
            if isinstance(value, UUID):
                result[key] = str(value)
            else:
                result[key] = value
        return result
