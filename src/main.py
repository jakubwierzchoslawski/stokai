"""
StokAI FastAPI application entry point.

Start with:
  uvicorn src.main:app --host 0.0.0.0 --port 8000
Or via docker compose (see docker-compose.yml).
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.ai.startup import initialise_ai_module
from src.config.settings import get_settings

HEARTBEAT_KEY = "stokai:health:last_beat"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown hooks."""
    # Validate settings on startup (fail-fast)
    settings = get_settings()

    # Initialise AI module — loads and validates all agent definitions.
    # Fails fast if any YAML is invalid, any prompt file is missing,
    # or any registered workflow violates the structural invariant.
    agents_dir = Path(settings.AGENTS_DIR)
    # system_prompt_file in each YAML is a path relative to the project root
    # e.g. "prompts/agents/relevance_analyst.md" resolved from "."
    registry = initialise_ai_module(
        agents_dir=agents_dir,
        prompts_base_dir=Path("."),
        workflow_node_sequences=None,  # populated when workflow graphs are registered (PLAN-F-006+)
    )
    app.state.agent_registry = registry

    yield


app = FastAPI(
    title="StokAI",
    description="AI-powered financial intelligence platform",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["ops"], include_in_schema=True)
async def health_check() -> JSONResponse:
    """Health check endpoint — no authentication required.

    Returns HTTP 200 with service status and worker liveness.
    Used by docker compose healthchecks and CI smoke tests.
    """
    settings = get_settings()
    worker_alive = False

    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        worker_alive = bool(await client.exists(HEARTBEAT_KEY))
        await client.aclose()
    except Exception:
        # Redis unreachable — worker_alive stays False; API itself is healthy
        pass

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "environment": settings.ENVIRONMENT,
            "worker_alive": worker_alive,
        },
    )
