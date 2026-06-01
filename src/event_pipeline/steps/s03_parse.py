"""Step 3: PARSE — extract structured fields from raw_payload.

Architecture enforcement:
  Open/Closed — source-specific parsers are strategy classes selected by source type.
  P-01 Provider Abstraction — no direct knowledge of external API schemas outside adapters.

Single Responsibility: field extraction and normalisation into PipelineState.
"""
from __future__ import annotations

import logging
from typing import Protocol

from src.event_pipeline.pipeline_state import PipelineState, RawEventSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PayloadParser Protocol — Open/Closed extension point
# ---------------------------------------------------------------------------

class PayloadParser(Protocol):
    """Strategy protocol for source-specific payload parsing."""

    def parse(self, state: PipelineState) -> PipelineState:
        """Extract fields and return updated state."""
        ...


# ---------------------------------------------------------------------------
# Concrete parser strategies
# ---------------------------------------------------------------------------

class GdeltPayloadParser:
    """Extracts fields from a GDELT article-style raw_payload."""

    def parse(self, state: PipelineState) -> PipelineState:
        payload = state.payload.raw_payload
        title = payload.get("title", "")
        url = payload.get("url", payload.get("sourceurl", ""))

        # Geo coordinates — GDELT uses actor1geo_lat / actor1geo_long
        geo_lat: float | None = None
        geo_lon: float | None = None
        try:
            lat_val = payload.get("actor1geo_lat")
            lon_val = payload.get("actor1geo_long")
            if lat_val is not None:
                geo_lat = float(lat_val)
            if lon_val is not None:
                geo_lon = float(lon_val)
        except (ValueError, TypeError):
            pass

        description = title or url or "GDELT event"

        return state.model_copy(update={
            "event_description": description,
            "geo_lat": geo_lat,
            "geo_lon": geo_lon,
        })


class EdgarPayloadParser:
    """Extracts fields from an SEC EDGAR filing notification."""

    def parse(self, state: PipelineState) -> PipelineState:
        payload = state.payload.raw_payload
        title = payload.get("title", "")
        company = payload.get("companyName", "")
        filing_type = payload.get("category", payload.get("filing_type", ""))

        description = f"{company} — {filing_type}: {title}".strip(" —:")
        if not description:
            description = "SEC EDGAR filing"

        return state.model_copy(update={
            "event_description": description,
            "geo_lat": None,
            "geo_lon": None,
        })


class PriceAnomalyPayloadParser:
    """Extracts fields from a price anomaly event."""

    def parse(self, state: PipelineState) -> PipelineState:
        payload = state.payload.raw_payload
        symbol = payload.get("symbol", "UNKNOWN")
        pct_change = payload.get("pct_change", "")
        description = f"Price anomaly detected for {symbol}"
        if pct_change:
            description += f" ({pct_change}%)"

        tickers = [symbol] if symbol != "UNKNOWN" else []

        return state.model_copy(update={
            "event_description": description,
            "tickers": tickers,
            "geo_lat": None,
            "geo_lon": None,
        })


class TwitterPayloadParser:
    """Extracts fields from a Twitter/X signal payload (stub)."""

    def parse(self, state: PipelineState) -> PipelineState:
        payload = state.payload.raw_payload
        text = payload.get("text", payload.get("full_text", "Twitter event"))
        return state.model_copy(update={
            "event_description": text,
            "geo_lat": None,
            "geo_lon": None,
        })


_PARSER_REGISTRY: dict[RawEventSource, PayloadParser] = {
    RawEventSource.GDELT: GdeltPayloadParser(),
    RawEventSource.SEC_EDGAR: EdgarPayloadParser(),
    RawEventSource.PRICE_ANOMALY: PriceAnomalyPayloadParser(),
    RawEventSource.X_FILTERED_STREAM: TwitterPayloadParser(),
}


# ---------------------------------------------------------------------------
# ParseStep
# ---------------------------------------------------------------------------

class ParseStep:
    """Pipeline Step 3: PARSE.

    Selects the appropriate ``PayloadParser`` strategy for the event source
    and extracts structured fields into the pipeline state.
    """

    step_name: str = "s03_parse"

    async def execute(self, state: PipelineState) -> PipelineState:
        """Extract structured fields from the raw payload."""
        parser = _PARSER_REGISTRY.get(state.payload.source)
        if parser is None:
            logger.warning(
                "Step 3 (PARSE): no parser for source %r — using description fallback",
                state.payload.source,
            )
            return state.model_copy(update={
                "event_description": str(state.payload.raw_payload),
            })

        result = parser.parse(state)
        logger.info(
            "Step 3 (PARSE): raw_event_id=%s description=%r",
            state.raw_event_id,
            result.event_description,
        )
        return result
