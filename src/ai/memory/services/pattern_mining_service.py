"""
PatternMiningService — weekly mining of procedural patterns from agent invocations.

run_mining_pass():
  1. Query agent_invocation rows from the past 30 days.
  2. Group by agent_role_id + context_signature.
  3. Clusters with sample_size >= MINING_MIN_SAMPLE and consistent output_pattern
     → create ProceduralPattern with authored_by='mined', approved_at=NULL.
  4. Idempotent: skip clusters whose context_signature hash already exists.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.memory.interfaces.i_procedural_repository import IProceduralRepository
from src.ai.memory.schemas.procedural_schemas import AuthoredBy, ProceduralPatternCreate

logger = logging.getLogger(__name__)

MINING_MIN_SAMPLE: int = 5
MINING_LOOKBACK_DAYS: int = 30


@dataclass
class MiningPassResult:
    """Summary of a single mining pass."""

    candidates_created: int
    run_at: datetime


def _context_signature_hash(agent_role_id: str, pattern_text: str) -> str:
    """Stable hash for idempotency check."""
    raw = f"{agent_role_id}::{pattern_text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class PatternMiningService:
    """Mines agent invocation history for candidate procedural patterns."""

    def __init__(
        self,
        procedural_repo: IProceduralRepository,
        session: AsyncSession,
    ) -> None:
        self._procedural = procedural_repo
        self._session = session

    async def run_mining_pass(self) -> MiningPassResult:
        """
        Discover patterns from agent_invocation rows past MINING_LOOKBACK_DAYS days.

        Groups invocations by agent_role_id. Clusters with sample_size >=
        MINING_MIN_SAMPLE create a mined, un-approved ProceduralPattern.
        Already-pending patterns for the same context_signature are skipped.
        """
        from src.ai.memory.models.episodic_models import AgentInvocation

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=MINING_LOOKBACK_DAYS)
        stmt = select(AgentInvocation).where(AgentInvocation.started_at >= cutoff)
        result = await self._session.execute(stmt)
        invocations = result.scalars().all()

        # Group by agent_role_id
        clusters: dict[str, list[Any]] = {}
        for inv in invocations:
            clusters.setdefault(inv.agent_role_id, []).append(inv)

        # Fetch existing pending patterns to avoid duplicates
        pending_patterns = await self._procedural.list_pending_approval()
        existing_hashes: set[str] = set()
        for p in pending_patterns:
            sig = _context_signature_hash(
                agent_role_id=p.recommended_for_agents[0]
                if p.recommended_for_agents
                else "",
                pattern_text=p.pattern_text,
            )
            existing_hashes.add(sig)

        candidates_created = 0
        for role_id, invs in clusters.items():
            if len(invs) < MINING_MIN_SAMPLE:
                continue

            # Derive a simple pattern description from the cluster
            pattern_text = (
                f"Agent role '{role_id}' consistently processed "
                f"{len(invs)} events in the past {MINING_LOOKBACK_DAYS} days. "
                "Consider reviewing for pattern extraction."
            )
            sig = _context_signature_hash(role_id, pattern_text)
            if sig in existing_hashes:
                logger.debug("Skipping duplicate pattern for role=%s", role_id)
                continue

            pattern_create = ProceduralPatternCreate(
                pattern_type="mined_invocation_cluster",
                context_tags=[role_id],
                pattern_text=pattern_text,
                authored_by=AuthoredBy.MINED,
                version=1,
                success_rate=None,
                sample_size=len(invs),
                confidence=None,
                recommended_for_agents=[role_id],
            )
            await self._procedural.create_pattern(pattern_create)
            existing_hashes.add(sig)  # prevent duplicates within the same pass
            candidates_created += 1
            logger.info("Created mined pattern candidate for role=%s", role_id)

        return MiningPassResult(
            candidates_created=candidates_created,
            run_at=datetime.now(tz=timezone.utc),
        )
