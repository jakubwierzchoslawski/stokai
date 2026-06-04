"""
cold_start — one-time resumable seeding pipeline for historical data.

Orchestrates GDELT/ACLED event ingestion, embedding generation, and HNSW index build
prior to system go-live. All state is persisted in seeding_checkpoint (PostgreSQL).
"""
