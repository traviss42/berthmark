.PHONY: help install install-backend install-frontend test test-backend test-frontend test-apis run-backend run-frontend dev build import-unlocode seed-db clean

SHELL := /bin/bash
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
	@echo "==> Importing UN/LOCODE maritime database..."
	@$(MAKE) import-unlocode

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

test-apis: ## Test live connectivity to all external APIs (UN/LOCODE, Open-Meteo, AISStream)
	@echo "==> Testing live external APIs connectivity..."
	@PYTHONPATH=backend $(PYTHON) backend/scripts/test_apis.py

run-backend: ## Start FastAPI backend server on http://localhost:8000
	@echo "==> Starting FastAPI backend server..."
	@PYTHONPATH=backend $(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

run-frontend: ## Start React frontend development server on http://localhost:5173
	@echo "==> Starting React Vite frontend..."
	@$(NPM) run dev --prefix frontend

dev: ## Run both backend and frontend servers concurrently (Ctrl+C stops both)
	@echo "==> Launching Berthmark development environment..."
	@echo "  • Backend API:     http://localhost:8000/docs"
	@echo "  • Frontend WebApp: http://localhost:5173"
	@echo "Press Ctrl+C to stop both servers."
	@bash -c '\
		PYTHONPATH=backend $(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000 & \
		BACKEND_PID=$$!; \
		$(NPM) run dev --prefix frontend & \
		FRONTEND_PID=$$!; \
		trap "kill $$BACKEND_PID $$FRONTEND_PID 2>/dev/null || true; exit 0" INT TERM; \
		wait $$BACKEND_PID $$FRONTEND_PID'

import-unlocode: ## Import UN/LOCODE maritime ports (Function=1 with valid coordinates) into SQLite
	@echo "==> Importing UN/LOCODE maritime ports database..."
	@PYTHONPATH=backend $(PYTHON) backend/scripts/import_unlocode.py

seed-db: import-unlocode ## Alias for import-unlocode


build: ## Build frontend production assets
	@echo "==> Building frontend production bundle..."
	@$(NPM) run build --prefix frontend

clean: ## Remove temporary cache and build artifacts
	@echo "==> Cleaning cache and build artifacts..."
	@rm -rf backend/.pytest_cache frontend/node_modules/.vite frontend/dist
	@find backend -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
