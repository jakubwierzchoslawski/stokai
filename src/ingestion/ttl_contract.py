"""TTL contract — single authoritative reference for all cache TTL values.

All numeric TTL values in the caching subsystem must be imported from this
module. Never duplicate these literals elsewhere; reference this file.

MACRO_TTL_S is the MVP fallback using a fixed 24-hour window.
Calendar-based computation (e.g. next macro data release date) is deferred
to a future implementation milestone.
"""

# ---------------------------------------------------------------------------
# Time-bounded data types (seconds)
# ---------------------------------------------------------------------------

PRICE_BAR_DELAYED_TTL_S: int = 900          # 15 minutes — free-tier / delayed feed
PRICE_BAR_REALTIME_TTL_S: int = 5           # ≤5 seconds — real-time feed
FUNDAMENTALS_TTL_S: int = 86_400            # 24 hours — refreshed daily
NEWS_EVENT_TTL_S: int = 3_600              # 1 hour — headline freshness window
MACRO_TTL_S: int = 86_400                  # 24 hours — MVP fallback; calendar-based TTL is
                                            # future work (see PLAN-N-011 deferred items)

# ---------------------------------------------------------------------------
# Immutable data types — no Redis TTL (permanent hot-cache residence)
# ---------------------------------------------------------------------------

HISTORICAL_PRICE_BAR_TTL_S: None = None    # Past close prices — fetched once per lifetime
EVENT_EMBEDDING_TTL_S: None = None         # Vector embeddings — immutable after creation

# ---------------------------------------------------------------------------
# Event-driven invalidation — no time-based TTL
# ---------------------------------------------------------------------------

COMPANY_SCORE_TTL_S: None = None           # Invalidated explicitly on score recompute

# ---------------------------------------------------------------------------
# Semantic fact decay — NOT a Redis TTL (applies to PostgreSQL column)
# ---------------------------------------------------------------------------

SEMANTIC_FACT_DECAY_MONTHS: int = 6        # Facts unconfirmed > 6 months are marked decayed
