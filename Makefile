.PHONY: all setup test test-verbose test-report test-classic coverage test-live lint typecheck format run

# Same version as the VSCodium/VS Code basedpyright extension; settings in pyproject.toml.
BASEDPYRIGHT = basedpyright@1.40.2

all: format lint typecheck test

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

test-report:
	uv run pytest --test-report reports/tests.md

test-classic:
	uv run pytest --classic

test-verbose:
	uv run pytest -v -rs

coverage:
	uv run pytest --classic --cov=sensai --cov-report=term-missing --cov-report=html

test-live:
	uv run pytest -m live -v -rA

lint:
	uv run ruff check src/

typecheck:
	uvx $(BASEDPYRIGHT)

format:
	uv run ruff format src/
	npx prettier --write "**/*.yml" "**/*.md"
