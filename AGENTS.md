# AGENTS.md

Instructions for AI coding agents working in this repo.

## Project

Sensai — local AI assistant CLI built on Ollama. Constraints and scope: [docs/SUBJECT.md](docs/SUBJECT.md), feature options: [docs/CATALOGUE.md](docs/CATALOGUE.md).

Hard constraints (do not violate):

- Python >= 3.10 as declared in `pyproject.toml` (note: the code already uses `datetime.UTC`, which needs 3.11+).
- No LLM frameworks (LangChain, LlamaIndex, Haystack, equivalent). Direct Ollama HTTP API only.
- Standard lib + utility packages (httpx, pydantic, sqlite3, fastapi, etc.) fine for non-LLM concerns.

## Architecture

Layered, one-way dependency:

```
interfaces/  (cli, tui, web)   -> talks to core, nothing talks to interfaces
core/        (engine, bootstrap, commands, config, prompt, budget) -> orchestrates via domain protocols
providers/ , tools/ , memory/ , eval/  -> pluggable impls of domain/protocols.py
domain/      (models, events, protocols) -> pure data + interfaces, no deps upward
```

`domain/protocols.py` is the seam: `core/engine.py` types against `LLMProvider`/`MemoryStore`/`BaseTool`/`Guardrail` Protocols, never against a concrete class. Swap implementations (mock provider in tests, real Ollama provider at runtime) by injecting at the `core/bootstrap.py` wiring point (`build_session`), shared by the CLI and the TUI.

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

## Current state (2026-09-29)

Implemented:

- `domain/`: models (`Message`, `Conversation`, `ToolCall`, `Persona`, `Document`, `Chunk`, `ScoredChunk`, `GuardrailVerdict`, `GuardrailFinding`), events (`TextChunkEvent`, `ToolCallEvent`, `GuardrailEvent`), protocols (`LLMProvider`, `BaseTool`, `MemoryStore`, `Guardrail`, `OutputStream`, `ToolRegistry`, `EmbeddingProvider`, `VectorStore`, `ContextRetriever`), errors.
- `providers/`: `OllamaLLMProvider`, `OllamaEmbeddingProvider`, `MockLLMProvider`, name-based registry (`get_provider`).
- `core/`: `ChatEngine` (streaming, tool-calling loop capped at 5 iterations, optional RAG retriever and guardrail), `bootstrap.py` (`build_session`), `commands.py` (slash commands), `config.py` (CLI > `sensai.toml` > defaults, `[tools]` and `[guardrails]` sections), `prompt.py`, `input.py`.
- `tools/`: `ToolRegistry`, `ReadFileTool`, `ListDirTool` (confined to `fs_allowed_root`).
- `memory/`: SQLite session persistence (`--session`), RAG (`TextChunker`, `SQLiteVectorStore`, `RAGRetriever`, enabled with `--rag-dir`).
- `eval/guardrails/` (EV2): regex + checksum PII detectors, heuristic injection rules, `RegexGuardrail`, `PiiOutputStream`. On by default; disable with `[guardrails] enabled = false`.
- `eval/evaluator.py` + `eval/adversarial/` (EV4): attack corpus (`corpus.py`, `known_gap` marks what the heuristics miss) replayed at guardrail and engine level, with a report. Run with `python -m sensai.eval.adversarial`.
- `interfaces/`: CLI (rich), TUI (textual, `--ui tui`), shared dispatcher and notice wording.

Built but not wired into the runtime: `eval/logger.py` (`TurnLogger`), `Persona` (`build_prompt` accepts one, nothing passes it).

Empty stubs, not yet built: `core/budget.py`, `memory/manager.py`, `memory/artifact.py`, `tools/mcp.py`, `tools/sandbox.py`, `tools/web.py`, `interfaces/web/*`.

Guardrail scope and known limits: input, model output and tool results are filtered. Not covered: PII inside tool-call arguments written by the model, the RAG context injected into the prompt, names and postal addresses. Reference design: [docs/elevenlabs-guardrails.md](docs/elevenlabs-guardrails.md).

Sprint plan tracked as GitHub issues (milestones "Sprint 1 - Base Loop MVP", "Sprint 2 - Session, Tools, Logging", "Sprint 3 - Tools, Permissions, Eval").
