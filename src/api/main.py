"""
api.main — FastAPI application factory for StokAI.

Wires together all routers, middleware, and exception handlers.
The application is created once at module level and imported by uvicorn.
"""
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from src.admin.router import admin_router
from src.admin.system.router import system_ops_router
from src.api.auth.router import auth_router
from src.api.evaluation.evaluation_router import evaluation_router
from src.api.middleware.disclaimer_middleware import DisclaimerMiddleware
from src.api.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from src.api.routes.memos import router as memos_router
from src.api.routers.hil_router import hil_router
from src.api.routers.portfolio_router import portfolio_router
from src.api.routers.watchlist_router import watchlist_router
from src.api.routers.onboarding_router import onboarding_router
from src.alerts.api.alerts_router import alerts_router
from src.alerts.api.alert_rules_router import alert_rules_router
from src.alerts.api.anti_fatigue_router import anti_fatigue_router
from src.api.routers.qa_router import qa_router
from src.compliance.compliance_router import compliance_router
from src.config.settings import get_settings
from src.api.v1 import api_v1_router
from src.api.v1.events import router as events_v1_router
from src.api.progressive_disclosure.router import router as disclosure_router
from src.api.admin.audit.audit_router import audit_router

_settings = get_settings()

app = FastAPI(
    title="StokAI API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Disclaimer injection middleware (PLAN-N-012) ───────────────────────────────
# Must be added before routers so it wraps all responses.
app.add_middleware(
    DisclaimerMiddleware,
    threshold=_settings.DISCLAIMER_SAMPLE_SIZE_THRESHOLD,
    disclaimer_text=_settings.DISCLAIMER_TEXT,
    path_prefixes=_settings.DISCLAIMER_MIDDLEWARE_PATH_PREFIXES,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(hil_router)  # PLAN-F-013: HIL admin queue (/api/v1/admin/hil)
app.include_router(portfolio_router, prefix="/api/v1")  # PLAN-F-024: Portfolio management
app.include_router(watchlist_router, prefix="/api/v1")  # PLAN-F-024: Watchlist management
app.include_router(onboarding_router, prefix="/api/v1")  # PLAN-F-024: Onboarding
app.include_router(admin_router, prefix="/api/v1")  # PLAN-F-028: admin data-source management
app.include_router(system_ops_router, prefix="/api/v1/admin")  # PLAN-F-030: System Operations
app.include_router(memos_router)  # PLAN-F-010: GET /api/v1/events/{event_id}/memo
app.include_router(evaluation_router, prefix="/api/v1")  # PLAN-F-016: evaluation framework
app.include_router(alerts_router, prefix="/api/v1")       # PLAN-F-025: Alerts Center
app.include_router(alert_rules_router, prefix="/api/v1")  # PLAN-F-025: Alert Rules CRUD
app.include_router(anti_fatigue_router, prefix="/api/v1") # PLAN-F-025: Anti-fatigue settings
app.include_router(qa_router, prefix="/api/v1")           # PLAN-F-027: Q&A Chat Interface
app.include_router(compliance_router, prefix="/api/v1")   # PLAN-N-012: Compliance track record
app.include_router(api_v1_router)                                  # PLAN-F-026/023: briefs, company-detail, screener, scoring
app.include_router(events_v1_router, prefix="/api/v1")             # PLAN-F-019/021: GET /api/v1/events
app.include_router(disclosure_router, prefix="/api/v1")            # PLAN-F-020: progressive disclosure
app.include_router(audit_router, prefix="/api/v1/admin")           # PLAN-F-029: AI audit console


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}
