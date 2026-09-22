# AGENTS.md

Instructions for AI coding agents working in this repo.

## Project

Sensai — local AI assistant CLI built on Ollama. Constraints and scope: [docs/SUBJECT.md](docs/SUBJECT.md), feature options: [docs/CATALOGUE.md](docs/CATALOGUE.md).

Hard constraints (do not violate):

- Python >= 3.10 (pyproject currently pins >=3.14, follow pyproject).
- No LLM frameworks (LangChain, LlamaIndex, Haystack, equivalent). Direct Ollama HTTP API only.
- Standard lib + utility packages (httpx, pydantic, sqlite3, fastapi, etc.) fine for non-LLM concerns.

## Architecture

Layered, one-way dependency:

```
interfaces/  (cli, web)        -> talks to core, nothing talks to interfaces
core/        (engine, prompt, config, budget) -> orchestrates via domain protocols
providers/ , tools/ , memory/ , eval/  -> pluggable impls of domain/protocols.py
domain/      (models, events, protocols) -> pure data + interfaces, no deps upward
```

`domain/protocols.py` is the seam: `core/engine.py` types against `LLMProvider`/`MemoryStore`/`BaseTool`/`Guardrail` Protocols, never against a concrete class. Swap implementations (mock provider in tests, real Ollama provider at runtime) by injecting at the `interfaces/cli/app.py` wiring point.

## Setup & commands

```bash
make setup   # uv sync + pre-commit install
make test    # uv run pytest
make lint    # uv run ruff check src/
make format  # uv run ruff format src/ + prettier on yml/md
```

Run a single test: `uv run pytest tests/path/to/test_file.py::test_name`

## Working conventions

- Package manager is `uv`. Never call `pip` directly.
- Every new file under `src/sensai/` needs a matching test file under `tests/` in the same change — not a follow-up. See open issues for the current sprint plan.
- `tests/` mirrors `src/sensai/` layout 1:1.
- Ruff handles both lint and format; run `make format` before committing.
- Pre-commit hooks are installed by `make setup` — don't bypass with `--no-verify` unless explicitly told to.
- Domain models (`domain/models.py`, `domain/events.py`) are pydantic `BaseModel`. Extend via new fields/subclasses, don't bypass validation.
- Provider/tool implementations must satisfy the relevant `domain/protocols.py` Protocol — check the protocol signature before adding a new provider or tool.

## Current state (2026-09-22)

Implemented: `domain/` (models, events, protocols), `providers/` (mock, ollama).
Empty stubs, not yet built: `core/`, `interfaces/`, `memory/`, `tools/`, `eval/`.
Sprint plan tracked as GitHub issues (milestones "Sprint 1 - Base Loop MVP", "Sprint 2 - Session, Tools, Logging").
