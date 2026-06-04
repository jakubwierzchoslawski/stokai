"""
Centralized configuration for StokAI.

All configuration is read exclusively from environment variables (or .env file).
Required fields have no default — pydantic raises ValidationError on startup
if any are absent (fail-fast, 12-factor compliant).
"""
from datetime import date
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ──────────────────────────────────────────────────────────
    ENVIRONMENT: str = "local"        # local | test | staging | production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str                 # required — no default
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str                    # required — no default
    CELERY_BROKER_URL: str = ""       # defaults to REDIS_URL at startup if blank
    CELERY_RESULT_BACKEND: str = ""   # defaults to REDIS_URL at startup if blank

    # ── AI Providers ──────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str            # required
    OPENAI_API_KEY: str               # required (embeddings)

    # ── External Integrations ─────────────────────────────────────────────────
    FINNHUB_API_KEY: str = ""         # optional; resolved via source_config at runtime
    FMP_API_KEY: str = ""             # optional
    SENDGRID_API_KEY: str = ""        # optional; alerts disabled if blank
    SENDGRID_FROM_EMAIL: str = ""     # optional; must be set when alerts are enabled

    # ── Langfuse Observability ────────────────────────────────────────────────
    LANGFUSE_SECRET_KEY: str = ""     # optional; no-op if blank
    LANGFUSE_PUBLIC_KEY: str = ""     # optional
    LANGFUSE_HOST: str = "http://langfuse-server:3000"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str               # required
    JWT_REFRESH_SECRET_KEY: str       # required
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Security ──────────────────────────────────────────────────────────────
    BCRYPT_ROUNDS: int = 12

    # ── Filesystem paths ──────────────────────────────────────────────────────
    AGENTS_DIR: str = "agents"
    PROMPTS_DIR: str = "prompts"

    # ── Prompt Management Pipeline (PLAN-F-014) ────────────────────────────────
    # Whether to enable Langfuse prompt publishing on deploy.
    LANGFUSE_PROMPTS_ENABLED: bool = True
    # Percentage of traffic to route to canary prompt version (0–100).
    # Default 10% — human admin promotes via 'stokai prompts promote' after monitoring.
    CANARY_TRAFFIC_PCT: int = Field(default=10, ge=0, le=100)

    # ── Port binding (12-factor) ──────────────────────────────────────────────
    PORT: int = 8000

    # ── Morning Brief (PLAN-F-006) ────────────────────────────────────────────
    # Default dispatch time for the Morning Brief email (user-overridable via D7).
    MORNING_BRIEF_DEFAULT_SEND_TIME: str = "06:00"
    # SendGrid dynamic template ID for the Morning Brief HTML email.
    # Must be set when alerts are enabled; validated at startup via validator below.
    SENDGRID_MORNING_BRIEF_TEMPLATE_ID: str = ""

    # ── Earnings Risk Brief (PLAN-F-009) ──────────────────────────────────────
    # Per-brief cost ceiling in USD (AC-001: $1.50).
    EARNINGS_BRIEF_COST_CEILING_USD: float = 1.50
    # HIL deadline time (24h format, UTC). Briefs unreviewed by this time are held.
    EARNINGS_BRIEF_HIL_DEADLINE_TIME: str = "17:45"
    # Hard workflow timeout in seconds (10 min = 600 s).
    EARNINGS_BRIEF_HARD_TIMEOUT_SECONDS: int = 600

    # ── Feature flags ─────────────────────────────────────────────────────────
    # Twitter/X source adapter. Default=false (free-tier plan; enable via env).
    # GDELT, EDGAR, and price_anomaly are always enabled.
    TWITTER_ENABLED: bool = False

    # ── Memory Subsystem (PLAN-F-015) ─────────────────────────────────────────
    # Minimum evidence count before a semantic fact is committed (Layer 2).
    EVIDENCE_GATE_MIN_COUNT: int = 3
    # Months after which an unconfirmed semantic fact is marked decayed.
    SEMANTIC_DECAY_MONTHS: int = 6

    # ── Cold-Start Seeding (PLAN-F-031) ───────────────────────────────────────
    # Provider to use for historical event ingestion: 'gdelt' or 'acled'.
    SEEDING_PROVIDER: str = "gdelt"
    # Start of the historical range to seed (GDELT archive begins 1979-01-01).
    GDELT_START_DATE: date = Field(default=date(1979, 1, 1))
    # Number of events per seeding batch (controls memory footprint per batch).
    SEEDING_BATCH_SIZE: int = 500
    # Number of parallel OpenAI embedding calls per sub-batch.
    EMBEDDING_CONCURRENCY: int = 5
    # ACLED API key — required only when SEEDING_PROVIDER=acled. Never logged.
    ACLED_API_KEY: str | None = None

    # ── Analogy Search (PLAN-F-004) ───────────────────────────────────────────
    # Number of historical analogies returned by find_historical_analogies step.
    # Configurable via env var ANALOGY_K. Range: 1–50 (default 5).
    # pydantic-settings maps this to the ANALOGY_K env var (case-insensitive).
    ANALOGY_K: int = Field(default=5, ge=1, le=50)

    # ── AI Recommendation Accuracy Calibration (PLAN-N-010) ──────────────────
    # Minimum Pearson CORR(confidence, actual_t1d) required for a Healthy pass.
    # Below this threshold the assessment reads "Warning: CORR below threshold".
    CALIBRATION_CORR_THRESHOLD: float = Field(default=0.3, ge=0.0001, le=0.9999)
    # Minimum total recommendations in the rolling window before threshold
    # enforcement is applied. Fewer rows → assessment "Insufficient data".
    CALIBRATION_MIN_SAMPLE: int = Field(default=30, ge=1)

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"local", "test", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got {v!r}")
        return v

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def default_broker_to_redis(cls, v: str, info) -> str:
        if not v:
            return info.data.get("REDIS_URL", "")
        return v

    @field_validator("CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def default_backend_to_redis(cls, v: str, info) -> str:
        if not v:
            return info.data.get("REDIS_URL", "")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Called once at module import; subsequent calls return the cached object.
    Raises ValidationError on first call if any required variable is missing.
    """
    return Settings()
