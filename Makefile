.PHONY: up down migrate test lint format eval-seed eval-run

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

eval-seed:
	docker compose run --rm worker python -m eval.seed

eval-run:
	curl -s -X POST http://localhost:8000/eval/run | python -m json.tool

test:
	pytest

lint:
	ruff check .
	black --check .
	isort --check-only .
	mypy api core db models worker embedding ingestion retrieval llm verifier eval

format:
	ruff check --fix .
	isort .
	black .
