.PHONY: all setup test lint format run

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

lint:
	uv run ruff check src/

format:
	uv run ruff format src/
	npx prettier --write "**/*.yml" "**/*.md"
