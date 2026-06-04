"""
Shared SQLAlchemy 2.0 DeclarativeBase for evaluation framework ORM models.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class EvaluationBase(DeclarativeBase):
    """Base class for all evaluation framework ORM models."""
    pass
