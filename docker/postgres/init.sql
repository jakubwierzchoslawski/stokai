-- StokAI — PostgreSQL initialisation script
-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Creates required extensions: TimescaleDB and pgvector (architecture §5).
-- timescale/timescaledb-ha:pg16 image includes both extensions.

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
