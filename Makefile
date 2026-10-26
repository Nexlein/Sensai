.PHONY: all setup test test-verbose coverage test-live lint format run

all: format lint test

run:
	uv run sensai $(filter-out $@,$(MAKECMDGOALS))

%:
	@:

setup:
	@echo "Installing dependencies..."
	uv sync --all-extras --dev
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install
	@echo "Project successfully initialized!"

test:
	uv run pytest

test-verbose:
	uv run pytest -v -rs

coverage:
	uv run pytest --cov=sensai --cov-report=term-missing --cov-report=html

test-live:
	uv run pytest -m live -v -rA

lint:
	uv run ruff check src/

format:
	uv run ruff format src/
	npx prettier --write "**/*.yml" "**/*.md"
