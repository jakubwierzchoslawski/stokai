-- Bootstrap extensions for StokAI PostgreSQL (TimescaleDB + pgvector).
-- This script runs once when the postgres container is first initialized.

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
