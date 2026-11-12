.PHONY: up down logs install lint test migrate api worker web web-check openapi

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker

install:
	uv sync
	cd web && pnpm install

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

web:
	cd web && pnpm dev

web-check:
	cd web && pnpm format:check && pnpm lint && pnpm test && pnpm build

# Regenerate the web client's types after changing an API schema.
openapi:
	uv run python scripts/export_openapi.py web/openapi.json
	cd web && pnpm gen:api
