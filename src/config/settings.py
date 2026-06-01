"""Application settings loaded exclusively from environment variables (12-factor, P-06).

VaultProvider abstraction: MVP uses .env via pydantic-settings. Future: Azure Key Vault
via the same interface — zero code changes required (VAULT decision, OCP).
"""
from __future__ import annotations

import os
from typing import Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# VaultProvider abstraction (Open/Closed Principle — extensible without change)
# ---------------------------------------------------------------------------

class VaultProvider(Protocol):
    """Protocol for secret retrieval backends (P-06, VAULT decision)."""

    def get_secret(self, key: str) -> str | None:
        """Return the secret value for *key*, or None if not found."""
        ...


class EnvVaultProvider:
    """Concrete VaultProvider backed by os.environ / .env (MVP implementation)."""

    def get_secret(self, key: str) -> str | None:
        return os.environ.get(key)


# ---------------------------------------------------------------------------
# Application settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Pydantic BaseSettings subclass — all values loaded from env / .env.

    Required at startup (fail-fast if missing):
      - JWT_SECRET_KEY

    Optional with safe defaults:
      - JWT_ALGORITHM, ACCESS_TOKEN_TTL_MINUTES, REFRESH_TOKEN_TTL_DAYS,
        BCRYPT_ROUNDS, DATABASE_URL
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 7

    # Password hashing — cost factor >= 10 (DEV-STANDARDS §8, REQ-N-007)
    BCRYPT_ROUNDS: int = 12

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://stokai:stokai@localhost:5432/stokai"

    # Provider registry (legacy fields kept for backward compatibility)
    PROVIDER_REGISTRY_PG_CHANNEL: str = "provider_registry_updates"
    PROVIDER_CACHE_TTL_SECONDS: int = 300

    # Checkpointing (REQ-N-004, PLAN-N-004)
    # Number of days to retain terminal checkpoint records before archiving.
    CHECKPOINT_RETENTION_DAYS: int = 30
    # Maximum hours a workflow can remain in HIL-pending (paused) state.
    CHECKPOINT_HIL_MAX_PAUSE_HOURS: int = 72

    # ---------------------------------------------------------------------------
    # Mode A Pipeline — PLAN-F-001
    # ---------------------------------------------------------------------------
    # Deduplication window in seconds (Redis SETEX TTL).
    DEDUP_TTL_SECONDS: int = 3600

    # Celery queue names
    PIPELINE_QUEUE: str = "event_pipeline"
    DEEP_DIVE_QUEUE: str = "event_deep_dive"

    # Path to the classify-event agent YAML config (relative to project root).
    CLASSIFY_MODEL_YAML: str = "agents/classify_event.yaml"

    # Twitter/X toggle — defaults OFF (C-002).
    # Set to true only when a live adapter is available.
    TWITTER_ENABLED: bool = False

    # Confidence routing thresholds (C-003).
    AUTO_SEND_THRESHOLD: float = 0.7
    HIL_THRESHOLD: float = 0.4

    # GDELT API endpoint (GDELT_API_URL overrides built-in default).
    GDELT_API_URL: str = (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        "?query=conflict&mode=artlist&maxrecords=250&format=json"
    )

    # EDGAR ATOM feed URL.
    EDGAR_FEED_URL: str = (
        "https://www.sec.gov/cgi-bin/browse-edgar"
        "?action=getcurrent&type=10-K&dateb=&owner=include&count=40&output=atom"
    )

    # EDGAR polling interval in seconds (default 5 minutes — AC-003 < 20 min SLA).
    EDGAR_POLL_INTERVAL_SECONDS: int = 300

    # Alert copy disclaimer (appended to all auto-generated alert text).
    ALERT_DISCLAIMER: str = (
        "For informational purposes only. "
        "Not investment advice. Past analogues do not guarantee future outcomes."
    )


def get_settings() -> Settings:
    """Return a cached Settings instance (single read per process)."""
    return _settings_singleton


# Module-level singleton — instantiated once; env vars read at import time.
_settings_singleton = Settings()


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward compatibility with existing callers)
# ---------------------------------------------------------------------------

def get_provider_registry_pg_channel() -> str:
    """Return the PostgreSQL LISTEN/NOTIFY channel name for provider registry updates."""
    return _settings_singleton.PROVIDER_REGISTRY_PG_CHANNEL


def get_provider_cache_ttl_seconds() -> int:
    """Return the Redis TTL (seconds) for non-historical provider data."""
    return _settings_singleton.PROVIDER_CACHE_TTL_SECONDS
