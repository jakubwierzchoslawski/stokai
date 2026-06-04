.PHONY: up down logs test test-integration scan-azure shell-api migrate ps help

## Show this help message
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

## Start all services in detached mode
up:
	docker compose up -d --build

## Stop all services
down:
	docker compose down

## Follow service logs
logs:
	docker compose logs -f

## Run all tests (unit only, excludes integration)
test:
	pytest tests/ -v --ignore=tests/integration

## Run integration tests only
test-integration:
	pytest tests/integration/ -v -m integration

## Scan src/ for forbidden Azure SDK imports
scan-azure:
	pytest tests/test_azure_import_scan.py -v

## Open an interactive shell in the api container
shell-api:
	docker compose exec api bash

## Run database migrations via Alembic
migrate:
	docker compose exec api alembic upgrade head

## Show service status
ps:
	docker compose ps
