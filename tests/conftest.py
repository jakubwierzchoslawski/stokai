"""Root conftest.py — sets test environment variables before any src.* imports.

This runs before any test collection so that src.config.settings.get_settings()
does not fail on missing required fields when running unit and integration tests
without a real .env file.
"""
import os

# Set required env vars with test-safe placeholder values.
# These never touch real infrastructure — DB, Redis, and external APIs
# are either not called in unit tests or overridden via dependency injection.
_TEST_ENV = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test-placeholder",
    "OPENAI_API_KEY": "sk-test-placeholder",
    "JWT_SECRET_KEY": "test-secret-key-minimum-32-characters-long!",
    "JWT_REFRESH_SECRET_KEY": "test-refresh-key-minimum-32-characters-ok!",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)
