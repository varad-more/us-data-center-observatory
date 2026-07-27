.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/python -m pip
WEB := apps/web

export HELIOS_DATABASE_URL ?= postgresql+psycopg://helios:helios@localhost:5432/helios
export HELIOS_TEST_DATABASE_URL ?= postgresql+psycopg://helios:helios@localhost:5432/helios_test

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------- setup --

.PHONY: install
install: ## Create the virtualenv and install backend + frontend dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -e ".[dev,documents]"
	cd $(WEB) && npm install --no-audit --no-fund

.PHONY: hooks
hooks: ## Install pre-commit hooks
	$(VENV)/bin/pre-commit install

# ---------------------------------------------------------------- database --

# One container, no Compose file. The evidence store uses the filesystem
# backend locally, so there is no object store to run alongside it; S3 is a
# production concern configured through HELIOS_EVIDENCE_BACKEND.
PG_CONTAINER := helios-postgres
PG_IMAGE := postgis/postgis:16-3.4

.PHONY: db-up
db-up: ## Start PostgreSQL + PostGIS
	@docker start $(PG_CONTAINER) 2>/dev/null || \
	docker run -d --name $(PG_CONTAINER) \
		-e POSTGRES_USER=helios -e POSTGRES_PASSWORD=helios -e POSTGRES_DB=helios \
		-p 5432:5432 $(PG_IMAGE)
	@echo "Waiting for PostgreSQL..."
	@until docker exec $(PG_CONTAINER) pg_isready -U helios -q 2>/dev/null; do sleep 1; done
	@docker exec $(PG_CONTAINER) psql -U helios -d helios -c \
		"CREATE DATABASE helios_test;" 2>/dev/null || true
	@echo "PostgreSQL ready on :5432 (databases: helios, helios_test)"

.PHONY: db-down
db-down: ## Stop and remove the PostgreSQL container and its data
	-docker rm -f $(PG_CONTAINER)

.PHONY: migrate
migrate: ## Apply database migrations
	$(VENV)/bin/alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back the most recent migration
	$(VENV)/bin/alembic downgrade -1

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="description"
	$(VENV)/bin/alembic revision --autogenerate -m "$(m)"

.PHONY: db-check
db-check: ## Fail if the models have drifted from the migrations
	$(VENV)/bin/alembic check

# --------------------------------------------------------------- ingestion --

.PHONY: bootstrap
bootstrap: ## Build the observatory from recorded fixtures (offline, reproducible)
	$(VENV)/bin/helios bootstrap

.PHONY: bootstrap-live
bootstrap-live: ## Build the observatory from live public records (hits county servers)
	$(VENV)/bin/helios bootstrap --live

.PHONY: export-api
export-api: ## Regenerate the static API snapshot the published site serves
	$(PY) scripts/export_static_api.py
	$(PY) scripts/verify_static_export.py

.PHONY: registry
registry: ## Print the source registry, including inaccessible sources
	$(VENV)/bin/helios registry-show

.PHONY: status
status: ## Summarise what is currently in the database
	$(VENV)/bin/helios status

# ---------------------------------------------------------------- run apps --

.PHONY: api
api: ## Run the API with autoreload
	$(VENV)/bin/uvicorn helios_api.main:app --reload --port 8000

.PHONY: web
web: ## Run the web interface in development mode
	cd $(WEB) && npm run dev

# ------------------------------------------------------------------ checks --

.PHONY: format
format: ## Format Python and TypeScript
	$(VENV)/bin/black packages apps/api apps/worker tests scripts
	$(VENV)/bin/ruff check --fix packages apps/api apps/worker tests scripts

.PHONY: lint
lint: ## Lint Python and TypeScript
	$(VENV)/bin/ruff check packages apps/api apps/worker tests scripts
	$(VENV)/bin/black --check packages apps/api apps/worker tests scripts
	cd $(WEB) && npm run lint

.PHONY: typecheck
typecheck: ## Type-check Python and TypeScript
	$(VENV)/bin/mypy packages apps/api apps/worker
	cd $(WEB) && npm run typecheck

.PHONY: test
test: ## Run the full backend test suite
	$(VENV)/bin/pytest

.PHONY: test-unit
test-unit: ## Run only fast unit tests (no database required)
	$(VENV)/bin/pytest -m "unit or contract"

.PHONY: test-cov
test-cov: ## Run tests with a coverage report
	$(VENV)/bin/pytest --cov --cov-report=term-missing --cov-report=xml

.PHONY: test-web
test-web: ## Run frontend tests
	cd $(WEB) && npm test

.PHONY: check
check: lint typecheck test test-web ## Run every check CI runs

.PHONY: build-web
build-web: ## Build the static site into apps/web/out
	cd $(WEB) && npm run build

.PHONY: clean
clean: ## Remove caches and build artefacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	rm -rf $(WEB)/.next $(WEB)/out
