.PHONY: up down migrate test lint format

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

test:
	pytest

lint:
	ruff check .
	black --check .
	isort --check-only .
	mypy api core db models worker embedding ingestion retrieval llm verifier

format:
	ruff check --fix .
	isort .
	black .
