"""
Alembic environment configuration for StokAI.

Reads DATABASE_URL from the environment and converts the asyncpg DSN to a
synchronous psycopg2 DSN for migration execution.

Usage:
    docker compose exec api alembic upgrade head
    docker compose exec api alembic revision --autogenerate -m "description"
"""
import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Alembic Config object (reads alembic.ini) ────────────────────────────────
config = context.config

# ── Logging ──────────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Resolve sync database URL from the environment ───────────────────────────
#
# The app uses postgresql+asyncpg:// for runtime, but Alembic migrations need a
# synchronous driver. We expect DATABASE_URL in the environment and convert it:
#   postgresql+asyncpg://user:pass@host:5432/db
#       → postgresql+psycopg2://user:pass@host:5432/db
#
_raw_url = os.environ.get("DATABASE_URL", "")
if _raw_url:
    _sync_url = _raw_url.replace("+asyncpg", "+psycopg2")
    config.set_main_option("sqlalchemy.url", _sync_url)

# ── Target metadata ──────────────────────────────────────────────────────────
#
# Import all ORM Base classes so autogenerate can detect model changes.
# Several models share a common Base (defined in user.py):
#   - user.py           defines Base  ← user, refresh_token, infrastructure_cost
#   - workflow_run.py    defines WorkflowBase
#   - earnings_event.py  defines EarningsEventBase
#   ...etc.
# Each Base is registered in its own declarative space; we collect them all.

from src.storage.models.user import Base as UserBase          # also covers refresh_token, infrastructure_cost
from src.storage.models.workflow_run import WorkflowBase
from src.storage.models.earnings_event import EarningsEventBase
from src.storage.models.earnings_brief_run import EarningsBriefRunBase
from src.storage.models.ai_recommendation import AiRecommendationBase
from src.storage.models.qa_session import QABase
from src.storage.models.brief import BriefBase
from src.storage.models.prompt_publication import PromptBase
from src.ai.memory.models.base import MemoryBase
from src.ai.evaluation.models.base import EvaluationBase
from src.ai.decision_log.models.ai_decision_model import Base as AiDecisionBase

# Bare DeclarativeBase used by some migrations (e.g. source_config)
from sqlalchemy.orm import DeclarativeBase

class _ExtraBase(DeclarativeBase):
    """Catch-all for tables whose ORM models aren't imported above."""

target_metadata = [
    UserBase.metadata,          # user, refresh_token, infrastructure_cost
    WorkflowBase.metadata,
    EarningsEventBase.metadata,
    EarningsBriefRunBase.metadata,
    AiRecommendationBase.metadata,
    QABase.metadata,
    BriefBase.metadata,
    PromptBase.metadata,
    MemoryBase.metadata,
    EvaluationBase.metadata,
    AiDecisionBase.metadata,
    _ExtraBase.metadata,
]

# ── Run migrations ───────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
