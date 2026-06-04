"""Conftest for screener integration tests.

Sets environment variables required by Settings before importing any
src.* modules that read config at module load time.
"""
import os

# Set required env vars before any src.* imports so Settings doesn't fail.
# These values are not real — they just satisfy Pydantic validation.
_TEST_ENV = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OPENAI_API_KEY": "sk-test",
    "JWT_SECRET_KEY": "test-secret-key-minimum-32-characters-long",
    "JWT_REFRESH_SECRET_KEY": "test-refresh-secret-key-minimum-32-chars-long",
}

for key, value in _TEST_ENV.items():
    os.environ.setdefault(key, value)
