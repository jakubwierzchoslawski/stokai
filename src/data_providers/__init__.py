"""
data_providers — external API adapters for historical event ingestion.

All classes that call external APIs or download remote files live in this module.
The HistoricalEventProvider protocol ensures adapters are interchangeable.
"""
from src.data_providers.historical_event_provider import HistoricalEventProvider
from src.ingestion.cold_start.types import (
    CheckpointState,
    RawHistoricalEvent,
    SeedingConfig,
    SeedingResult,
)

__all__ = [
    "HistoricalEventProvider",
    "RawHistoricalEvent",
    "SeedingConfig",
    "SeedingResult",
    "CheckpointState",
]
