# whereq.com — the common tasks, in one screen.
#
#   make            list the targets
#   make install    set up the backend venv and the frontend dependencies
#   make dev        run the backend and the frontend dev servers
#   make test       the backend test suite
#   make check      everything CI runs
#   make up         bring up the whole stack in Docker
#
# The backend targets run from backend/ — the app.* imports are absolute and
# Settings reads .env relative to the working directory.

COMPOSE := docker compose -f docker/docker-compose.yml
PY      := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip

.DEFAULT_GOAL := help
.PHONY: help install install-backend install-frontend dev dev-backend dev-frontend \
        test typecheck build check migrate migrate-down seed \
        up down logs ps rebuild clean distclean

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── setup ────────────────────────────────────────────────────────────────

install: install-backend install-frontend ## Install the backend and frontend dependencies

install-backend: ## Create the backend venv and install the requirements
	python3 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.lock

install-frontend: ## Install the frontend dependencies (a yarn workspace)
	yarn install --frozen-lockfile

# ── running ──────────────────────────────────────────────────────────────

dev: ## Run the backend and the frontend dev servers together
	@echo "backend  → http://localhost:8000"
	@echo "frontend → http://localhost:3743"
	@trap 'kill 0' EXIT; \
	( cd backend && ../backend/.venv/bin/uvicorn app.main:app --reload --port 8000 ) & \
	( yarn dev ) & \
	wait

dev-backend: ## Run only the backend
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend: ## Run only the frontend
	yarn dev

# ── checks ───────────────────────────────────────────────────────────────

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest -q

typecheck: ## Typecheck the frontend
	yarn typecheck

build: ## Build the frontend production bundle
	yarn build

check: test typecheck ## Run the checks that CI runs (plus the Docker gate separately)

# ── the database ─────────────────────────────────────────────────────────

migrate: ## Apply the migrations
	cd backend && .venv/bin/alembic upgrade head

migrate-down: ## Step back one migration
	cd backend && .venv/bin/alembic downgrade -1

seed: ## Insert the demo data
	cd backend && .venv/bin/python -m app.seed

# ── docker ───────────────────────────────────────────────────────────────

up: ## Build and start the whole stack
	@test -f docker/.env || (echo "docker/.env is missing — cp docker/.env.example docker/.env" && exit 1)
	$(COMPOSE) up -d --build

down: ## Stop the stack and remove its volumes
	$(COMPOSE) down -v

logs: ## Follow the stack's logs
	$(COMPOSE) logs -f

ps: ## Show the stack's status
	$(COMPOSE) ps

rebuild: ## Rebuild the images without cache
	$(COMPOSE) build --no-cache

# ── cleanup ──────────────────────────────────────────────────────────────

clean: ## Remove the build outputs and the caches
	rm -rf frontend/dist
	find backend -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf backend/.pytest_cache

distclean: clean ## Also remove the virtualenv and the node_modules
	rm -rf backend/.venv node_modules
