.PHONY: install dev run test lint format migrate revision docker clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

run:
	python -m bot

test:
	pytest -v --cov=bot --cov-report=term-missing

lint:
	ruff check src tests
	mypy src

format:
	ruff format src tests
	ruff check --fix src tests

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

docker:
	docker compose up -d --build

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
