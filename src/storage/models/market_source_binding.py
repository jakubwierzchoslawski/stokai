"""
storage.models.market_source_binding — SQLAlchemy ORM model for the
market_source_binding table.

Maps markets to data-source providers with a role (primary or fallback).
The composite primary key (market_id, interface_type, source_id) prevents
duplicate bindings. MarketRegistry reads this table (joined with source_config)
to build its runtime routing dict.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.storage.models.user import Base


class MarketSourceBinding(Base):
    """ORM model for the ``market_source_binding`` table.

    Columns
    -------
    market_id       UUID FK→market (not yet enforced if market table absent)
    interface_type  Provider interface tag (e.g. PriceProvider, NewsProvider)
    source_id       UUID FK→source_config.source_id
    role            'primary' or 'fallback' (CHECK constraint enforced in DB)

    Composite PK: (market_id, interface_type, source_id) — prevents duplicate
    bindings per market+interface+source triple.
    """

    __tablename__ = "market_source_binding"
    __table_args__ = (
        CheckConstraint("role IN ('primary', 'fallback')", name="ck_market_source_binding_role"),
        Index("ix_msb_market_interface", "market_id", "interface_type"),
        Index("ix_msb_source_id", "source_id"),
    )

    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )
    interface_type: Mapped[str] = mapped_column(
        Text(),
        primary_key=True,
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_config.source_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"MarketSourceBinding(market_id={self.market_id!r}, "
            f"interface_type={self.interface_type!r}, "
            f"source_id={self.source_id!r}, "
            f"role={self.role!r})"
        )
