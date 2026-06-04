"""Mode A Reactive Pipeline package.

Public surface area for Steps 4 and 5 (PLAN-F-003):
    TrackedCompany     — Pydantic model for a portfolio-tracked company.
    ExposureRecord     — Pydantic model for a computed exposure row.
    compute_exposure_map  — Step 4: compute per-company exposure magnitudes.
    persist_event_record  — Step 5: persist GeoEvent + EventExposure rows atomically.
    PipelineContext    — Mutable context threaded through all pipeline steps.
    GeoEventCreate     — Input value object for geo_event INSERT.
    GeoEvent           — Value object returned after geo_event INSERT.

NOTE: Imports are lazy (inside __getattr__) to avoid circular imports with
storage.repositories modules that themselves import from event_pipeline submodules.
"""
from __future__ import annotations

__all__ = [
    "TrackedCompany",
    "ExposureRecord",
    "compute_exposure_map",
    "persist_event_record",
    "PipelineContext",
    "GeoEventCreate",
    "GeoEvent",
]


def __getattr__(name: str):  # type: ignore[return]
    if name in ("TrackedCompany", "ExposureRecord", "compute_exposure_map", "persist_event_record"):
        from src.event_pipeline.exposure_mapping import (  # noqa: PLC0415
            ExposureRecord,
            TrackedCompany,
            compute_exposure_map,
            persist_event_record,
        )
        mapping = {
            "TrackedCompany": TrackedCompany,
            "ExposureRecord": ExposureRecord,
            "compute_exposure_map": compute_exposure_map,
            "persist_event_record": persist_event_record,
        }
        return mapping[name]
    if name in ("GeoEvent", "GeoEventCreate", "PipelineContext"):
        from src.event_pipeline.pipeline_state import (  # noqa: PLC0415
            GeoEvent,
            GeoEventCreate,
            PipelineContext,
        )
        mapping = {
            "GeoEvent": GeoEvent,
            "GeoEventCreate": GeoEventCreate,
            "PipelineContext": PipelineContext,
        }
        return mapping[name]
    raise AttributeError(f"module 'src.event_pipeline' has no attribute {name!r}")
