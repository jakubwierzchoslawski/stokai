"""API v1 routers."""
from fastapi import APIRouter

from src.api.v1.scoring.indicators import router as indicators_router
from src.api.v1.scoring.scoring_profiles import router as profiles_router
from src.api.v1.scoring.scores import router as scores_router
from src.api.v1.scoring.parameter_catalog import router as parameter_catalog_router
from src.api.v1.screener.router import router as screener_router
from src.api.v1.company_detail_router import router as company_detail_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(indicators_router)
api_v1_router.include_router(profiles_router)
api_v1_router.include_router(scores_router)
api_v1_router.include_router(parameter_catalog_router)
api_v1_router.include_router(screener_router)
api_v1_router.include_router(company_detail_router)

__all__ = ["api_v1_router"]
