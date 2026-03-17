.PHONY: install dev test migrate migrate-create docker-up docker-down lint format

install:
	poetry install

dev:
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

test:
	poetry run pytest

migrate:
	poetry run alembic upgrade head

migrate-create:
	poetry run alembic revision --autogenerate -m "$(message)"

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

lint:
	poetry run ruff check src/ tests/

format:
	poetry run black src/ tests/
	poetry run isort src/ tests/
