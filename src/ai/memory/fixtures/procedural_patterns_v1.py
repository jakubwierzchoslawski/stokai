"""
Hand-seeded v1 procedural patterns for all nine agent roles.

All patterns are pre-approved (authored_by='human', approved_at=NOW() at seed time).
These are inserted via the Alembic data migration 0037_seed_procedural_patterns_v1.py.
"""
from __future__ import annotations

PROCEDURAL_PATTERNS_V1: list[dict] = [
    {
        "agent_role": "relevance-analyst",
        "pattern_type": "reasoning",
        "context_tags": ["geopolitical", "relevance", "event-assessment"],
        "pattern_text": (
            "When assessing geopolitical event relevance, first identify the primary geographic "
            "region affected, then cross-reference with tracked company exposure data before "
            "making relevance determination. Weight sector-specific exposure above generic "
            "regional exposure scores."
        ),
    },
    {
        "agent_role": "anomaly-detector",
        "pattern_type": "reasoning",
        "context_tags": ["price-anomaly", "spike-detection", "statistical"],
        "pattern_text": (
            "When detecting price anomalies, apply a z-score threshold of >= 2.5 standard "
            "deviations from the 20-day rolling mean before flagging as anomalous. "
            "Always exclude known earnings or dividend dates from anomaly scoring to "
            "avoid false positives."
        ),
    },
    {
        "agent_role": "exposure-analyst",
        "pattern_type": "reasoning",
        "context_tags": ["portfolio-exposure", "sector", "geography"],
        "pattern_text": (
            "When computing portfolio exposure, aggregate at sector and geography dimensions "
            "independently. Flag concentrated positions (>15% in a single geography or sector) "
            "before synthesising the overall exposure score. Present exposure as a normalised "
            "0–1 score with explicit confidence bounds."
        ),
    },
    {
        "agent_role": "historical-context-agent",
        "pattern_type": "reasoning",
        "context_tags": ["historical", "precedent", "similarity"],
        "pattern_text": (
            "When retrieving historical context, prioritise precedents within the same sector "
            "and event type. Use semantic similarity (cosine distance) to the current event "
            "embedding as the primary ranking signal. Return the top 3 precedents with "
            "outcome summaries and confidence scores."
        ),
    },
    {
        "agent_role": "recommendation-synthesizer",
        "pattern_type": "reasoning",
        "context_tags": ["synthesis", "recommendation", "confidence"],
        "pattern_text": (
            "When synthesising a final recommendation, weight agent outputs by their individual "
            "confidence scores. Require a minimum aggregate confidence of 0.6 before producing "
            "a BUY or SELL signal. Default to HOLD when confidence is below threshold or "
            "when agent outputs conflict significantly (variance > 0.3)."
        ),
    },
    {
        "agent_role": "narrative-writer",
        "pattern_type": "reasoning",
        "context_tags": ["narrative", "report", "plain-language"],
        "pattern_text": (
            "When writing the event narrative, lead with the one-sentence impact summary, "
            "followed by a three-point supporting evidence section. Use active voice and "
            "avoid financial jargon when targeting end_user persona. "
            "Conclude with the recommended action and confidence level."
        ),
    },
    {
        "agent_role": "earnings-context-agent",
        "pattern_type": "reasoning",
        "context_tags": ["earnings", "guidance", "calendar"],
        "pattern_text": (
            "When analysing earnings context, always verify the earnings date is within "
            "the next 90 days before flagging as high-relevance. Compare EPS guidance to "
            "consensus estimates; a miss of >= 5% triggers an elevated-risk annotation. "
            "Include prior two quarters for trend context."
        ),
    },
    {
        "agent_role": "event-deep-dive-agent",
        "pattern_type": "reasoning",
        "context_tags": ["deep-dive", "event-analysis", "secondary-effects"],
        "pattern_text": (
            "When performing an event deep-dive, analyse first-order effects on directly "
            "named entities, then enumerate secondary supply-chain or competitor impacts. "
            "Score each impact pathway with an evidence strength rating (high/medium/low) "
            "based on the number of corroborating sources."
        ),
    },
    {
        "agent_role": "qa-analyst",
        "pattern_type": "reasoning",
        "context_tags": ["qa", "validation", "consistency"],
        "pattern_text": (
            "When performing QA validation, check that the recommendation direction is "
            "consistent with the confidence score direction, that all cited entities exist "
            "in the MARKET_REGISTRY, and that no PII or internal secret appears in the "
            "narrative output. Flag any inconsistency as a blocking issue before publish."
        ),
    },
]
