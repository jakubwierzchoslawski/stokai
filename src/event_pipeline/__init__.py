"""Mode A Reactive Pipeline package.

Public surface area for Steps 4 and 5 (PLAN-F-003):
    TrackedCompany     — Pydantic model for a portfolio-tracked company.
    ExposureRecord     — Pydantic model for a computed exposure row.
    compute_exposure_map  — Step 4: compute per-company exposure magnitudes.
    persist_event_record  — Step 5: persist GeoEvent + EventExposure rows atomically.
    PipelineContext    — Mutable context threaded through all pipeline steps.
    GeoEventCreate     — Input value object for geo_event INSERT.
    GeoEvent           — Value object returned after geo_event INSERT.
"""
from src.event_pipeline.exposure_mapping import (
    ExposureRecord,
    TrackedCompany,
    compute_exposure_map,
    persist_event_record,
)
from src.event_pipeline.pipeline_state import GeoEvent, GeoEventCreate, PipelineContext

__all__ = [
    "TrackedCompany",
    "ExposureRecord",
    "compute_exposure_map",
    "persist_event_record",
    "PipelineContext",
    "GeoEventCreate",
    "GeoEvent",
]
