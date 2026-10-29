.PHONY: help setup backend-sync frontend-install backend run frontend test-backend test-frontend test e2e

PYTHON ?= python
NPM ?= npm

ifeq ($(OS),Windows_NT)
BACKEND_PYTHON := .venv/Scripts/python.exe
else
BACKEND_PYTHON := .venv/bin/python
endif

help:
	@echo "Run from the repository root:"
	@echo "  make setup          Install backend and frontend dependencies"
	@echo "  make backend        Start FastAPI at http://127.0.0.1:8001"
	@echo "  make run            Alias for make backend"
	@echo "  make frontend       Start Vite at http://127.0.0.1:8081"
	@echo "  make test           Run backend and frontend tests"
	@echo "  make e2e            Build the Compose stack and run the browser test"

setup: backend-sync frontend-install

backend-sync:
	cd backend && $(PYTHON) -m uv sync

frontend-install:
	cd frontend && $(NPM) install

backend: backend-sync
	cd backend && $(BACKEND_PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

run: backend

frontend:
	cd frontend && $(NPM) run dev -- --host 127.0.0.1 --port 8081

test: test-backend test-frontend

test-backend: backend-sync
	cd backend && $(BACKEND_PYTHON) -m pytest -q

test-frontend:
	cd frontend && $(NPM) test

e2e:
	docker compose --profile e2e up --build --abort-on-container-exit --exit-code-from e2e
