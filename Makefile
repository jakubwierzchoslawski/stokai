# StokAI — Makefile convenience targets
# Decision D6: Docker Compose primary runtime.
# Usage: make <target>
# Prerequisites: Docker Engine installed, .env file present (cp .env.example .env)

.PHONY: up down logs shell deploy-prompts build ps help

## up: Start the full StokAI stack (builds images if needed, runs in background)
up:
	docker compose up -d --build

## down: Stop and remove containers and volumes
down:
	docker compose down -v

## logs: Tail logs from all services (Ctrl+C to stop)
logs:
	docker compose logs -f

## shell: Open a bash shell inside the stokai-app container
shell:
	docker compose exec stokai-app bash

## build: Build images without starting containers
build:
	docker compose build

## ps: Show status of all containers
ps:
	docker compose ps

## deploy-prompts: Publish Langfuse prompts from the agents/ directory
## This target is a placeholder; wired by PLAN-F-013.
deploy-prompts:
	@echo "deploy-prompts: placeholder — will be wired by PLAN-F-013"
	@echo "Expected: publish all prompt files under agents/ to Langfuse as versioned prompts."

## help: Show this help
help:
	@grep -E '^## ' Makefile | sed 's/## //'
