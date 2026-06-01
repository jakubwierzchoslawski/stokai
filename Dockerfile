# StokAI — Multi-stage Dockerfile
# Decision D6: Docker Compose is the primary MVP runtime target.
# Architecture P-06: No secrets baked in; all config injected via env vars.
# Architecture P-10: No Azure-specific code or imports.
#
# Usage:
#   docker build -t stokai-app:latest .
#   docker run --env-file .env -p 8000:8000 stokai-app:latest
#
# stokai-worker and stokai-scheduler reuse this image with command: overrides
# in docker-compose.yml.

# ---------------------------------------------------------------------------
# Stage 1: builder — install Python dependencies into /install prefix
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first — enables Docker layer caching across app-only changes.
# pyproject.toml is used as the requirements source via pip install --no-deps.
COPY pyproject.toml ./

# Install all runtime dependencies into a prefix directory.
# Using --prefix=/install keeps them separate from the system Python.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install \
        fastapi \
        "uvicorn[standard]" \
        "sqlalchemy[asyncio]" \
        asyncpg \
        "pydantic>=2.7.0" \
        pydantic-settings \
        "redis[asyncio]" \
        alembic \
        python-dotenv \
        "python-jose[cryptography]" \
        "passlib[bcrypt]" \
        python-multipart \
        langgraph \
        langgraph-checkpoint-postgres \
        langchain-core \
        "celery[redis]"

# ---------------------------------------------------------------------------
# Stage 2: runtime — copy install prefix and application source only
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime system dependencies only (libpq for asyncpg, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY src/ ./src/
COPY agents/ ./agents/
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Runtime environment settings — no secrets baked in (P-06)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the FastAPI application port
EXPOSE 8000

# Default command: run the FastAPI application
# stokai-worker and stokai-scheduler override this via compose command:
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
