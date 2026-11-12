.PHONY: up down logs install lint test migrate api worker

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker

install:
	uv sync

lint:
	uv run ruff format --check src tests migrations
	uv run ruff check src tests migrations
	uv run mypy src tests

test:
	uv run pytest

migrate:
	uv run alembic upgrade head

api:
	uv run uvicorn radar.main:create_app --factory --reload --port 8000

worker:
	uv run python -m radar.jobs.worker
