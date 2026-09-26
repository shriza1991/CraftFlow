.PHONY: help install run test lint format check docker-up docker-down docker-build migrate

PYTHON ?= python
VENV_PYTHON ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
	VENV_PYTHON = .venv\Scripts\python
endif

help:
	@echo "Ages Art AI Business Automation - Available Commands:"
	@echo "  make install       Install dependencies"
	@echo "  make run           Run FastAPI development server"
	@echo "  make test          Run pytest suite"
	@echo "  make lint          Run ruff linter check"
	@echo "  make format        Format code with ruff"
	@echo "  make check         Run lint, compile, and tests"
	@echo "  make docker-up     Start docker compose services"
	@echo "  make docker-down   Stop docker compose services"
	@echo "  make docker-build  Build docker compose images"
	@echo "  make migrate       Run database migrations"

install:
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"

run:
	$(VENV_PYTHON) -m uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0 --port 8000

test:
	$(VENV_PYTHON) -m pytest -v backend/tests

lint:
	$(VENV_PYTHON) -m ruff check backend

format:
	$(VENV_PYTHON) -m ruff format backend

check: lint test
	$(VENV_PYTHON) -m compileall backend

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build

migrate:
	$(VENV_PYTHON) -m alembic upgrade head
