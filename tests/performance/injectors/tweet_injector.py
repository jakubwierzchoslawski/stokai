"""TweetEventInjector — builds X_FILTERED_STREAM payloads for performance tests.

PLAN-N-001 TASK-001.

Each call to build_payload(index) produces a distinct payload (unique text and
tweet ID) to prevent pipeline deduplication from collapsing the 100-event run.

The detected_at timestamp is set at payload construction time so the latency
clock starts at injection, not at executor entry.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from src.event_pipeline.pipeline_state import RawEventPayload, RawEventSource

# Stable test tenant ID used across all performance injectors.
_PERF_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# Fixed set of realistic-sounding tweet bodies to rotate through.
_TWEET_TEMPLATES = [
    "BREAKING: Major geopolitical development affecting {sector} sector. Event #{idx}",
    "URGENT: Central bank policy announcement impacts markets. Run #{idx}",
    "NEWS: Trade agreement collapse between key partners. Index={idx}",
    "ALERT: Significant military movement reported near energy corridor. #{idx}",
    "DEVELOPING: Currency crisis spreading in emerging markets. Sequence={idx}",
]


class TweetEventInjector:
    """Builds X_FILTERED_STREAM ``RawEventPayload`` instances for latency tests.

    Implements the ``EventInjector`` Protocol.

    Each ``build_payload(index)`` call embeds the index in both the tweet text
    and tweet_id to guarantee a unique fingerprint, preventing the pipeline
    deduplication step (Step 2) from collapsing the test run.

    SRP: single responsibility — builds tweet payloads only.
    """

    source_type: str = "X_FILTERED_STREAM"

    def build_payload(self, index: int) -> RawEventPayload:
        """Build a distinct X_FILTERED_STREAM payload for the given run index.

        Parameters
        ----------
        index:
            Zero-based run counter.  Embedded in tweet text and tweet_id to
            guarantee uniqueness across 100+ sequential injections.

        Returns
        -------
        RawEventPayload:
            Fully-populated payload with detected_at set to now().
        """
        template = _TWEET_TEMPLATES[index % len(_TWEET_TEMPLATES)]
        sector_names = ["energy", "finance", "technology", "healthcare", "materials"]
        sector = sector_names[index % len(sector_names)]
        tweet_text = template.format(sector=sector, idx=index)

        raw_payload = {
            "tweet_id": f"perf-tweet-{index:06d}-{uuid.uuid4().hex[:8]}",
            "text": tweet_text,
            "user": {
                "id": f"user-{(index % 20):04d}",
                "screen_name": f"perf_user_{index % 20}",
                "followers_count": 10000 + (index * 17),
            },
            "timestamp": datetime.utcnow().isoformat(),
            "lang": "en",
            "retweet_count": index % 50,
            "run_index": index,
        }

        return RawEventPayload(
            source=RawEventSource.X_FILTERED_STREAM,
            raw_payload=raw_payload,
            detected_at=datetime.utcnow(),
            tenant_id=_PERF_TENANT_ID,
        )
