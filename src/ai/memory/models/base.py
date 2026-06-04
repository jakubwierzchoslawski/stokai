"""
Shared SQLAlchemy 2.0 DeclarativeBase for the memory subsystem ORM models.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class MemoryBase(DeclarativeBase):
    """Base class for all memory subsystem ORM models."""
    pass
