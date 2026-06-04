"""
storage.models.portfolio — SQLAlchemy ORM models for Portfolio, Position, WatchlistItem.

Mirrors the schema created by migration 0052_portfolio_watchlist.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class PortfolioBase(DeclarativeBase):
    """Declarative base shared by Portfolio, Position, WatchlistItem models."""


class Portfolio(PortfolioBase):
    """ORM model for the `portfolio` table."""

    __tablename__ = "portfolio"
    __table_args__ = (Index("ix_portfolio_tenant_user", "tenant_id", "user_id"),)

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=datetime.utcnow,
    )

    positions: Mapped[list[Position]] = relationship(
        "Position",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"Portfolio(portfolio_id={self.portfolio_id!r}, name={self.name!r})"


class Position(PortfolioBase):
    """ORM model for the `position` table."""

    __tablename__ = "position"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "company_id", name="uq_position_portfolio_company"),
        Index("ix_position_portfolio_id", "portfolio_id"),
        CheckConstraint(
            "source IN ('manual', 'csv', 'broker')",
            name="ck_position_source",
        ),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("portfolio.portfolio_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    shares: Mapped[float] = mapped_column(sa.Float, nullable=False)
    cost_basis: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=datetime.utcnow,
    )
    source: Mapped[str] = mapped_column(sa.String(20), nullable=False)

    portfolio: Mapped[Portfolio] = relationship(
        "Portfolio",
        back_populates="positions",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"Position(position_id={self.position_id!r}, ticker={self.ticker!r})"


class WatchlistItem(PortfolioBase):
    """ORM model for the `watchlist_item` table."""

    __tablename__ = "watchlist_item"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "company_id", name="uq_watchlist_tenant_user_company"
        ),
        Index("ix_watchlist_tenant_user", "tenant_id", "user_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("user.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        default=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"WatchlistItem(item_id={self.item_id!r}, ticker={self.ticker!r})"
