"""API v1 routers."""
from fastapi import APIRouter

from src.api.v1.scoring.indicators import router as indicators_router
from src.api.v1.scoring.scoring_profiles import router as profiles_router
from src.api.v1.scoring.scores import router as scores_router
from src.api.v1.scoring.parameter_catalog import router as parameter_catalog_router
from src.api.v1.scoring.geo_modifier import router as geo_modifier_router  # PLAN-F-018
from src.api.v1.screener.router import router as screener_router
from src.api.v1.company_detail_router import router as company_detail_router
from src.api.v1.watchlist_scan_router import router as watchlist_scan_router  # PLAN-F-008
from src.api.v1.earnings_brief_router import router as earnings_brief_router        # PLAN-F-009
from src.api.v1.earnings_brief_router import list_router as earnings_brief_list_router  # PLAN-F-009
from src.api.briefs.briefs_router import router as briefs_router          # PLAN-F-026
from src.api.briefs.feedback_router import router as briefs_feedback_router  # PLAN-F-026

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(indicators_router)
api_v1_router.include_router(profiles_router)
api_v1_router.include_router(scores_router)
api_v1_router.include_router(parameter_catalog_router)
api_v1_router.include_router(geo_modifier_router, prefix="/scoring")  # PLAN-F-018 TASK-007
api_v1_router.include_router(screener_router)
api_v1_router.include_router(company_detail_router)
api_v1_router.include_router(watchlist_scan_router)           # PLAN-F-008 TASK-008
api_v1_router.include_router(earnings_brief_router)           # PLAN-F-009 TASK-007
api_v1_router.include_router(earnings_brief_list_router)      # PLAN-F-009 TASK-007
api_v1_router.include_router(briefs_router)                   # PLAN-F-026 TASK-004
api_v1_router.include_router(briefs_feedback_router)          # PLAN-F-026 TASK-004

__all__ = ["api_v1_router"]
