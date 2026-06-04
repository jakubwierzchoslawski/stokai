"""
HistoricalEventProvider — abstract base class for cold-start data ingestion.

All historical event providers (GDELT, ACLED, etc.) implement this interface.
This is the only module that defines the protocol for external API access.
Architecture Principle 1: switching providers is a config change, not a code change.
"""
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import date

from src.ingestion.cold_start.types import RawHistoricalEvent


class HistoricalEventProvider(ABC):
    """Protocol for fetching historical event data from external providers.

    Implementations must be stateless with respect to the date range —
    a new instance per seeding run is expected.
    """

    @abstractmethod
    def fetch_batches(
        self,
        start_date: date,
        end_date: date,
        batch_size: int = 500,
    ) -> Iterator[list[RawHistoricalEvent]]:
        """Yield successive batches of raw historical events in ascending date order.

        Each yielded list contains at most batch_size events. The caller is
        responsible for checkpointing progress; providers must not maintain state
        between yields.

        Args:
            start_date: First day of the requested date range (inclusive).
            end_date: Last day of the requested date range (inclusive).
            batch_size: Maximum events per yielded batch.

        Yields:
            Successive lists of RawHistoricalEvent, each up to batch_size items.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return the canonical provider identifier.

        Returns:
            A lowercase string, e.g. 'gdelt' or 'acled'.
        """
        ...
