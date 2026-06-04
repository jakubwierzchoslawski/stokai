"""
storage.repositories — repository pattern implementations for all DB entities.

Each repository class is injected via constructor (DIP). No business logic here.

Public protocols:
    EventEmbeddingRepository — protocol for event_embedding table (PLAN-F-004).
    TenantIdMissingError — raised by TenantScopedRepository when tenant_id is None.
    BriefRepository / IBriefRepository — brief table (PLAN-F-010).
    WorkflowRunRepository — workflow_run table (PLAN-F-010).
    CompanyExposureRepository / ICompanyRepository — tracked company data (PLAN-F-003).
    GeoEventRepository / IGeoEventRepository — geo_event table (PLAN-F-003).
    EventExposureRepository / IEventExposureRepository — event_exposure table (PLAN-F-003).
"""
from src.storage.repositories.base import TenantIdMissingError
from src.storage.repositories.brief_repository import BriefRepository, IBriefRepository
from src.storage.repositories.company_exposure_repository import (
    CompanyExposureRepository,
    ICompanyRepository,
)
from src.storage.repositories.event_embedding import EventEmbeddingRepository
from src.storage.repositories.event_exposure_repository import (
    EventExposure,
    EventExposureRepository,
    IEventExposureRepository,
)
from src.storage.repositories.geo_event_repository import (
    GeoEventRepository,
    IGeoEventRepository,
)
from src.storage.repositories.workflow_run_repository import WorkflowRunRepository

__all__ = [
    "EventEmbeddingRepository",
    "TenantIdMissingError",
    "BriefRepository",
    "IBriefRepository",
    "WorkflowRunRepository",
    # PLAN-F-003: exposure mapping pipeline
    "CompanyExposureRepository",
    "ICompanyRepository",
    "GeoEventRepository",
    "IGeoEventRepository",
    "EventExposureRepository",
    "IEventExposureRepository",
    "EventExposure",
]
