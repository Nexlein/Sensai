.PHONY: setup test lint format

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
