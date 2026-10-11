.PHONY: help setup backend-sync frontend-install frontend-env backend frontend test-backend test-frontend test

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
	@echo "  make frontend       Start Vite at http://127.0.0.1:8081"
	@echo "  make test           Run backend and frontend tests"

setup: backend-sync frontend-install frontend-env

backend-sync:
	cd backend && $(PYTHON) -m uv sync

frontend-install:
	cd frontend && $(NPM) install

frontend-env:
	$(PYTHON) -c "from pathlib import Path; src = Path('frontend/.env.local.example'); dst = Path('frontend/.env.local'); dst.write_bytes(src.read_bytes()) if not dst.exists() else None"

backend: backend-sync
	cd backend && $(BACKEND_PYTHON) -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

frontend: frontend-env
	cd frontend && $(NPM) run dev -- --host 127.0.0.1 --port 8081

test: test-backend test-frontend

test-backend: backend-sync
	cd backend && $(BACKEND_PYTHON) -m pytest -q

test-frontend:
	cd frontend && $(NPM) test
