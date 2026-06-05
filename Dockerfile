# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Compiles wheels and installs dependencies into /app/dist.
# No application source or secrets are present in this stage.
FROM python:3.12-slim AS builder

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency manifests only — not source — for layer caching
COPY pyproject.toml ./
# Copy lock file if present (Poetry or pip-tools); harmless if absent
COPY poetry.lock* requirements*.txt* ./

# Install all dependencies into an isolated prefix
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/app/dist .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Minimal image with only runtime artifacts; no build toolchain.
FROM python:3.12-slim AS runtime

# Install libpq at runtime (needed by asyncpg/psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /app/dist /usr/local

WORKDIR /app

# Copy application source
COPY src/ ./src/
RUN mkdir -p agents prompts
COPY agents/ ./agents/
COPY prompts/ ./prompts/

# Create a non-root user for runtime security
RUN groupadd --gid 1001 stokai && \
    useradd --uid 1001 --gid stokai --shell /bin/bash --create-home stokai

# 12-factor: port binding via env var
ENV PORT=8000
EXPOSE $PORT

# Switch to non-root user
USER stokai

# Default command — overridden in docker-compose.yml for worker/beat
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
