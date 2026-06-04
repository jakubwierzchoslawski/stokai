"""
ImprovementLoopService — weekly aggregation of user feedback to generate
improvement proposals requiring human approval.

run_improvement_loop():
  1. Fetch all feedback from the past 7 days.
  2. Aggregate by feedback_type + workflow context (from report/recommendation).
  3. Patterns with >= REJECTION_THRESHOLD rejections (reject/reject_with_feedback)
     or >= THUMBS_DOWN_THRESHOLD thumbs_down on the same workflow type
     → create ImprovementProposal(status='pending').
  4. Proposals are NOT applied automatically.
  5. Idempotent: deduplicate by source_feedback_ids hash.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from src.ai.memory.interfaces.i_feedback_repository import IFeedbackRepository
from src.ai.memory.interfaces.i_improvement_repository import IImprovementRepository
from src.ai.memory.schemas.feedback_schemas import (
    FeedbackType,
    ImprovementProposalCreate,
    ProposalStatus,
)

logger = logging.getLogger(__name__)

REJECTION_THRESHOLD: int = 3
THUMBS_DOWN_THRESHOLD: int = 5
LOOKBACK_DAYS: int = 7


@dataclass
class ImprovementLoopResult:
    """Summary of a single improvement loop run."""

    proposals_created: int
    run_at: datetime


def _source_hash(feedback_ids: list[UUID]) -> str:
    """Stable hash for idempotency check."""
    sorted_ids = sorted(str(fid) for fid in feedback_ids)
    return hashlib.sha256(json.dumps(sorted_ids).encode()).hexdigest()[:16]


class ImprovementLoopService:
    """Generates improvement proposals from aggregated user feedback."""

    def __init__(
        self,
        feedback_repo: IFeedbackRepository,
        improvement_repo: IImprovementRepository,
    ) -> None:
        self._feedback = feedback_repo
        self._improvement = improvement_repo

    async def run_improvement_loop(self) -> ImprovementLoopResult:
        """
        Aggregate past week's feedback and create pending improvement proposals.

        Returns an ImprovementLoopResult with the count of new proposals.
        """
        since = datetime.now(tz=timezone.utc) - timedelta(days=LOOKBACK_DAYS)
        feedback_list = await self._feedback.list_since(since=since)

        # Group by (feedback_type, workflow_type_proxy)
        # workflow_type_proxy = report_id-based grouping (best we have without workflow ref)
        rejection_buckets: dict[str, list] = defaultdict(list)
        thumbs_down_buckets: dict[str, list] = defaultdict(list)

        for fb in feedback_list:
            # Use feedback_type as the primary grouping key
            bucket_key = str(fb.report_id or "global")
            ft = fb.feedback_type

            if ft in (FeedbackType.REJECT.value, FeedbackType.REJECT_WITH_FEEDBACK.value):
                rejection_buckets[bucket_key].append(fb)
            elif ft == FeedbackType.THUMBS_DOWN.value:
                thumbs_down_buckets[bucket_key].append(fb)

        # Fetch existing pending proposals for idempotency
        existing_proposals = await self._improvement.list_pending()
        existing_hashes: set[str] = set()
        for p in existing_proposals:
            existing_hashes.add(_source_hash(p.source_feedback_ids))

        proposals_created = 0

        # Check rejection threshold
        for bucket_key, fbs in rejection_buckets.items():
            if len(fbs) < REJECTION_THRESHOLD:
                continue
            feedback_ids = [fb.feedback_id for fb in fbs]
            sig = _source_hash(feedback_ids)
            if sig in existing_hashes:
                logger.debug("Skipping duplicate rejection proposal for bucket=%s", bucket_key)
                continue

            proposal = ImprovementProposalCreate(
                proposal_type="threshold_adjustment",
                description=(
                    f"High rejection rate detected: {len(fbs)} rejections "
                    f"for report group '{bucket_key}' in the past {LOOKBACK_DAYS} days."
                ),
                proposed_changes={
                    "workflow_type": bucket_key,
                    "rejection_count": len(fbs),
                    "feedback_ids": [str(fid) for fid in feedback_ids],
                    "suggested_action": "Review agent prompt or confidence threshold.",
                },
                source_feedback_ids=feedback_ids,
            )
            await self._improvement.create_proposal(proposal)
            existing_hashes.add(sig)
            proposals_created += 1

        # Check thumbs-down threshold
        for bucket_key, fbs in thumbs_down_buckets.items():
            if len(fbs) < THUMBS_DOWN_THRESHOLD:
                continue
            feedback_ids = [fb.feedback_id for fb in fbs]
            sig = _source_hash(feedback_ids)
            if sig in existing_hashes:
                continue

            proposal = ImprovementProposalCreate(
                proposal_type="prompt_adjustment",
                description=(
                    f"High thumbs-down rate: {len(fbs)} negative signals "
                    f"for report group '{bucket_key}' in the past {LOOKBACK_DAYS} days."
                ),
                proposed_changes={
                    "workflow_type": bucket_key,
                    "thumbs_down_count": len(fbs),
                    "feedback_ids": [str(fid) for fid in feedback_ids],
                    "suggested_action": "Review report narrative or scoring logic.",
                },
                source_feedback_ids=feedback_ids,
            )
            await self._improvement.create_proposal(proposal)
            existing_hashes.add(sig)
            proposals_created += 1

        return ImprovementLoopResult(
            proposals_created=proposals_created,
            run_at=datetime.now(tz=timezone.utc),
        )
