.PHONY: help install install-backend install-frontend test test-backend test-frontend run-backend run-frontend dev seed-db clean

PYTHON := backend/.venv/bin/python
UVICORN := backend/.venv/bin/uvicorn
PYTEST := backend/.venv/bin/pytest
NPM := npm

help: ## Show available Makefile targets
	@echo "Berthmark - Port-Call Risk Tracking & Assessment Tool"
	@echo ""
	@echo "Usage:"
	@echo "  make <target>"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install all backend and frontend dependencies

install-backend: ## Set up Python virtual environment and install backend dependencies
	@echo "==> Setting up backend virtual environment..."
	@if [ ! -d "backend/.venv" ]; then python3 -m venv backend/.venv; fi
	@backend/.venv/bin/pip install --upgrade pip
	@backend/.venv/bin/pip install -r backend/requirements.txt
	@echo "==> Initializing UN/LOCODE database..."
	@$(MAKE) seed-db

install-frontend: ## Install frontend node modules
	@echo "==> Installing frontend dependencies..."
	@$(NPM) install --prefix frontend

test: test-backend test-frontend ## Run all test suites (backend + frontend)

test-backend: ## Run backend tests with pytest
	@echo "==> Running backend pytest suite..."
	@PYTHONPATH=backend $(PYTEST) backend/tests/ -v

test-frontend: ## Run frontend tests with vitest
	@echo "==> Running frontend vitest suite..."
	@$(NPM) run test --prefix frontend

run-backend: ## Start FastAPI backend server on http://localhost:8000
	@echo "==> Starting FastAPI backend server..."
	@PYTHONPATH=backend $(UVICORN) app.main:app --reload --port 8000

run-frontend: ## Start React frontend development server on http://localhost:5173
	@echo "==> Starting React Vite frontend..."
	@$(NPM) run dev --prefix frontend

dev: ## Run both backend and frontend servers concurrently (Ctrl+C stops both)
	@echo "==> Launching Berthmark development environment..."
	@echo "  • Backend API:     http://localhost:8000/docs"
	@echo "  • Frontend WebApp: http://localhost:5173"
	@echo "Press Ctrl+C to stop both servers."
	@trap 'kill 0' INT TERM EXIT; \
	(PYTHONPATH=backend $(UVICORN) app.main:app --reload --port 8000) & \
	($(NPM) run dev --prefix frontend) & \
	wait

seed-db: ## Seed UN/LOCODE SQLite database from maritime_ports.json
	@echo "==> Seeding UN/LOCODE maritime database..."
	@PYTHONPATH=backend $(PYTHON) backend/scripts/import_unlocode.py --seed

clean: ## Remove temporary cache and build artifacts
	@echo "==> Cleaning cache and build artifacts..."
	@rm -rf backend/.pytest_cache frontend/node_modules/.vite
	@find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
