.PHONY: install dev run test lint format check clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

run:
	uvicorn memory_layer.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -v --cov=memory_layer

lint:
	ruff check src/ tests/
	mypy src/

format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

check: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	rm -rf dist/ build/ *.egg-info .coverage htmlcov/
