"""
SemanticHygieneService — weekly decay pass for Layer 2 semantic memory.

run_decay_pass(): lists facts unconfirmed for >= SEMANTIC_DECAY_MONTHS,
marks them decayed, and returns a DecayPassResult summary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.ai.memory.interfaces.i_semantic_repository import ISemanticRepository

SEMANTIC_DECAY_MONTHS: int = 6


@dataclass
class DecayPassResult:
    """Summary of a single decay-pass run."""

    facts_decayed: int
    run_at: datetime


class SemanticHygieneService:
    """Drives the weekly semantic fact decay lifecycle."""

    def __init__(self, semantic_repo: ISemanticRepository) -> None:
        self._semantic = semantic_repo

    async def run_decay_pass(self) -> DecayPassResult:
        """
        Identify and mark decayed all facts that have not been confirmed
        for at least SEMANTIC_DECAY_MONTHS months.

        Returns a DecayPassResult with the count of newly decayed facts.
        """
        old_facts = await self._semantic.list_unconfirmed_older_than(
            months=SEMANTIC_DECAY_MONTHS
        )
        if not old_facts:
            return DecayPassResult(facts_decayed=0, run_at=datetime.now(tz=timezone.utc))

        fact_ids = [f.fact_id for f in old_facts]
        count = await self._semantic.mark_decayed(fact_ids)
        return DecayPassResult(facts_decayed=count, run_at=datetime.now(tz=timezone.utc))
