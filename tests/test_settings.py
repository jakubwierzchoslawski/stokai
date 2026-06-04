"""
Tests for src/config/settings.py — Pydantic Settings with fail-fast validation.
TDD: these tests were written before the implementation.
"""
import os
import pytest
from pydantic import ValidationError


# Helper: minimal set of required env vars
REQUIRED_VARS = {
    "DATABASE_URL": "postgresql+asyncpg://stokai:secret@postgres:5432/stokai",
    "REDIS_URL": "redis://redis:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OPENAI_API_KEY": "sk-test",
    "JWT_SECRET_KEY": "supersecretjwtkey",
    "JWT_REFRESH_SECRET_KEY": "supersecretrefreshkey",
}


def _clear(monkeypatch):
    """Remove all required vars from env so Settings() fails without explicit set."""
    for key in REQUIRED_VARS:
        monkeypatch.delenv(key, raising=False)
    # Also delete optional vars that could bleed in from .env files
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)


def _set_all(monkeypatch):
    """Set all required vars in env."""
    for key, val in REQUIRED_VARS.items():
        monkeypatch.setenv(key, val)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear lru_cache before each test to prevent pollution."""
    from src.config.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── Required field validation tests ────────────────────────────────────────────

def test_settings_raises_when_database_url_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Disable .env file loading by pointing to nonexistent file
    monkeypatch.setenv("ENV_FILE", "nonexistent.env")
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "DATABASE_URL" in str(exc_info.value)


def test_settings_raises_when_redis_url_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("REDIS_URL", raising=False)
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "REDIS_URL" in str(exc_info.value)


def test_settings_raises_when_anthropic_api_key_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


def test_settings_raises_when_jwt_secret_key_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "JWT_SECRET_KEY" in str(exc_info.value)


def test_settings_raises_when_jwt_refresh_secret_key_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("JWT_REFRESH_SECRET_KEY", raising=False)
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "JWT_REFRESH_SECRET_KEY" in str(exc_info.value)


def test_settings_raises_when_openai_api_key_missing(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "OPENAI_API_KEY" in str(exc_info.value)


# ── Celery default validators ──────────────────────────────────────────────────

def test_celery_broker_defaults_to_redis_url(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    from src.config.settings import Settings
    s = Settings(_env_file="nonexistent.env")
    assert s.CELERY_BROKER_URL == REQUIRED_VARS["REDIS_URL"]


def test_celery_result_backend_defaults_to_redis_url(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    from src.config.settings import Settings
    s = Settings(_env_file="nonexistent.env")
    assert s.CELERY_RESULT_BACKEND == REQUIRED_VARS["REDIS_URL"]


# ── ENVIRONMENT validator ──────────────────────────────────────────────────────

def test_invalid_environment_value_raises(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "staging2")
    from src.config.settings import Settings
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file="nonexistent.env")
    assert "ENVIRONMENT" in str(exc_info.value)


# ── Happy-path full construction ───────────────────────────────────────────────

def test_valid_full_settings_object_is_constructed(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")
    from src.config.settings import Settings
    s = Settings(_env_file="nonexistent.env")
    assert s.DATABASE_URL == REQUIRED_VARS["DATABASE_URL"]
    assert s.REDIS_URL == REQUIRED_VARS["REDIS_URL"]
    assert s.ANTHROPIC_API_KEY == REQUIRED_VARS["ANTHROPIC_API_KEY"]
    assert s.OPENAI_API_KEY == REQUIRED_VARS["OPENAI_API_KEY"]
    assert s.JWT_SECRET_KEY == REQUIRED_VARS["JWT_SECRET_KEY"]
    assert s.JWT_REFRESH_SECRET_KEY == REQUIRED_VARS["JWT_REFRESH_SECRET_KEY"]
    assert s.ENVIRONMENT == "local"
    assert s.DATABASE_POOL_SIZE == 10
    assert s.DATABASE_MAX_OVERFLOW == 5
    assert s.PORT == 8000


# ── Singleton / lru_cache ──────────────────────────────────────────────────────

def test_get_settings_returns_singleton(monkeypatch):
    _set_all(monkeypatch)
    # Override env_file at process level won't help here since get_settings
    # uses the module-level SettingsConfigDict; monkeypatch env vars instead
    # and rely on cache_clear in autouse fixture.
    # We need to verify two calls return the same object id.
    from src.config.settings import get_settings
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
