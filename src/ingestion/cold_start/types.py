"""
Shared Pydantic types for the cold-start seeding pipeline.

These types form the contract between data providers (HistoricalEventProvider
implementations) and the ingestion orchestrator. All fields are provider-agnostic;
provider-specific adapters normalize their output to these schemas.
"""
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class CheckpointState(str, Enum):
    """State machine for a single monthly seeding batch."""

    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"


class RawHistoricalEvent(BaseModel):
    """Provider-agnostic representation of a single historical event.

    Produced by HistoricalEventProvider.fetch_batches() and consumed by
    EventParser to produce a GeoEventCreate domain object.
    """

    external_id: str
    """Provider-assigned unique identifier (e.g., GDELT GlobalEventID or ACLED data_id)."""

    occurred_at: datetime
    """When the event occurred, in UTC."""

    title: str
    """Short descriptive title (e.g., actor pair or event_type)."""

    summary: str
    """Longer narrative description used for embedding generation."""

    lat: float | None
    """WGS-84 latitude. None if provider does not supply location."""

    lon: float | None
    """WGS-84 longitude. None if provider does not supply location."""

    geo_regions: list[str]
    """Country or region codes associated with the event."""

    cameo_code: str | None
    """CAMEO event code, e.g. '190'. None for providers that don't use CAMEO."""

    intensity_raw: float
    """Raw intensity value from the provider; normalized to [1, 5] by EventParser."""

    sentiment_raw: float
    """Raw sentiment value from the provider; normalized to [-1, 1] by EventParser."""

    source_provider: str
    """Canonical provider identifier, e.g. 'gdelt' or 'acled'."""

    raw_payload: dict
    """Original provider row preserved verbatim for audit and reprocessing."""


class SeedingConfig(BaseModel):
    """Runtime configuration for a single seeding invocation."""

    provider: str
    """Which HistoricalEventProvider to use: 'gdelt' or 'acled'."""

    start_date: date
    """First day of the historical range to seed (inclusive)."""

    end_date: date
    """Last day of the historical range to seed (inclusive)."""

    batch_size: int = 500
    """Maximum events per provider batch (controls memory footprint)."""

    embedding_concurrency: int = 5
    """Number of parallel OpenAI embedding calls per sub-batch."""

    dry_run: bool = False
    """If True, parse and validate but do not write any rows to the DB."""


class SeedingResult(BaseModel):
    """Outcome summary returned by SeedingOrchestrator.orchestrate()."""

    events_seeded: int
    """Number of new geo_event rows inserted in this run."""

    events_skipped: int
    """Number of events skipped because they already existed (idempotent)."""

    embeddings_created: int
    """Number of new event_embedding rows written."""

    exposures_created: int
    """Number of event_exposure rows written with price_change_t1d populated."""

    errors: list[str]
    """Human-readable descriptions of any non-fatal errors encountered."""
