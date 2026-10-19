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
core/        (engine, streaming, tool_runner, turn, guard, bootstrap, commands, config, prompt, budget) -> orchestrates via domain protocols
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
- Every feature PR adds at least two user stories (role/action/outcome plus acceptance criteria) to `docs/USER_STORIES.md`, as SUBJECT.md requires.
- Ruff handles both lint and format; run `make format` before committing.
- Pre-commit hooks are installed by `make setup` — don't bypass with `--no-verify` unless explicitly told to.
- Domain models (`domain/models.py`, `domain/events.py`) are pydantic `BaseModel`. Extend via new fields/subclasses, don't bypass validation.
- Provider/tool implementations must satisfy the relevant `domain/protocols.py` Protocol — check the protocol signature before adding a new provider or tool.

## Current state (2026-09-29)

Implemented:

- `domain/`: models (`Message`, `Conversation`, `ToolCall`, `Persona`, `Document`, `Chunk`, `ScoredChunk`, `GuardrailVerdict`, `GuardrailFinding`), events (`TextChunkEvent`, `ToolCallEvent`, `GuardrailEvent`), protocols (`LLMProvider`, `BaseTool`, `MemoryStore`, `Guardrail`, `OutputStream`, `ToolRegistry`, `EmbeddingProvider`, `VectorStore`, `ContextRetriever`, `ReplyRecorder`), errors.
- `providers/`: `OllamaLLMProvider`, `OllamaEmbeddingProvider`, `MockLLMProvider`, name-based registry (`get_provider`). `GroqLLMProvider` (`providers/groq.py`) is an opt-in extra over Groq's OpenAI-compatible SSE API; it deviates from the Ollama-only rule above, so Ollama must stay the default. It takes `api_key` (config `api_key` or `GROQ_API_KEY`), ignores `base_url`, and `/config` masks the key.
- `core/`: `ChatEngine` (streaming, tool-calling loop capped at 5 iterations, optional RAG retriever and guardrail), `bootstrap.py` (`build_session`), `commands.py` (slash commands), `config.py` (CLI > `sensai.toml` > defaults, `[tools]` and `[guardrails]` sections), `prompt.py`, `input.py`.
- `tools/`: `ToolRegistry`, `ReadFileTool`, `ListDirTool` (confined to `fs_allowed_root`).
- `tools/mcp.py` (T1): hand-written MCP client over stdio (`McpClient`: initialize, `tools/list`, `tools/call`) and `McpTool` (a `SensitiveTool`, named `<server>__<tool>`). Servers come from `[mcp.servers.<name>]` in `sensai.toml`; `build_session` starts them in parallel, skips a failing one with a warning in `CommandContext.startup_warnings`, and `CommandContext.aclose()` stops them. `save_config` rewrites the whole file, so new config sections must be written back there too. Live test against the GitHub server: `SENSAI_LIVE_MCP=1` (needs Docker and `GITHUB_PERSONAL_ACCESS_TOKEN`).
- `memory/`: SQLite session persistence (`--session`), RAG (`TextChunker`, `SQLiteVectorStore`, `RAGRetriever`, enabled with `--rag-dir`), structured memory `manager.py` (M3: SQLite CRUD over entities and facts, auto-injected into prompt and managed via `/memory`).
- `tools/sandbox.py` (T2): `RunCodeTool` (`run_python`, a `SensitiveTool`) pipes the code to `python -I -` in a throwaway `docker run` (no network, read-only, all caps dropped, non-root, 256m/1 cpu/64 pids, timeout 10s default and 60s max, container killed on timeout). Output is `exit code / stdout / stderr`, each clipped at 4000 chars; Docker failures come back as `Error: sandbox unavailable…`. Always registered by `build_default_registry`. `preview` renders the code as an all-added diff so the confirmation prompt shows it in full (`tool_confirmation` hides the `code` argument then). Needs Docker and `python:3.12-alpine`. Live test: `SENSAI_LIVE_SANDBOX=1`.
- Slow or failing model server: `OllamaLLMProvider` has no read timeout (`wait_forever`; connect and write stay bounded), so a slow CPU model is never cut off. `ChatEngine` turns any `httpx.HTTPError` or `RuntimeError` from the provider into `ProviderError` (with the cause chained), and `interfaces/notices.error_text` words it in one line for both UIs, never a traceback. `interfaces/thinking.py` (`Thinking.watch`) shows "thinking… N s" after a 1 s grace while the next event is awaited and pauses during confirmations (`hold`). Ctrl+C in the CLI (`_stoppable` in `cli/app.py`) and Esc in the TUI cancel only the current turn; `ChatEngine.send` then drops the unanswered user message.
- `memory/`: SQLite session persistence (`--session`), RAG (`TextChunker`, `SQLiteVectorStore`, `RAGRetriever`, enabled with `--rag-dir`).
- `eval/guardrails/` (EV2): regex + checksum PII detectors, heuristic injection rules, `RegexGuardrail`, `PiiOutputStream`. On by default; disable with `[guardrails] enabled = false`.
- `eval/evaluator.py` + `eval/adversarial/` (EV4): attack corpus (`corpus.py`, `known_gap` marks what the heuristics miss) replayed at guardrail and engine level, with a report. Run with `python -m sensai.eval.adversarial`.
- `eval/judge/` (EV1): `LLMJudge` grades a reply for relevance and coherence (1-5) and checks its claims against the RAG context, through an injected `LLMProvider`. Failures come back as a verdict with `error`, never an exception. Run with `python -m sensai.eval.judge replies.jsonl`. Not wired into the chat loop. Its input comes from `ReplyLogger` (`eval/logger.py`, a `ReplyRecorder`): with `[eval] log_replies = true`, `ChatEngine` appends each final, non-refused reply to `logs/replies.jsonl`. Live test: `SENSAI_LIVE_JUDGE=1` (needs Ollama). Usage and test guide for EV1/EV4: [docs/evaluation.md](docs/evaluation.md).
- Reasoning loop: with `[reasoning] enabled` (default) `ChatEngine` emits `StepEvent`, `ThoughtEvent` (`source` native or text) and `MaxStepsEvent`, stores the thought on `Message.thought`, and at `max_steps` makes one last tool-free call. `split_thoughts` (set from `show_thoughts`) is what holds text back during a round that may call tools; off by default so answers stream. `think` is the effort passed to `chat_stream(think=...)`; the default is `DEFAULT_EFFORT = "low"` and `/effort` changes it live through `CommandContext.choose`, a picker each UI provides. `save_config` writes the `[reasoning]` section back.
- `interfaces/diff.py`: the confirmation diff shows every changed line, with 3 lines of context per change and `⋮` between changes; there is no line cap.
- `interfaces/`: CLI (rich), TUI (textual, `--ui tui`), shared dispatcher and notice wording.
- `interfaces/web/` (X1): FastAPI app (`app.py`, `run_web` serves on 127.0.0.1:8000 with uvicorn) with one page (`index.html`) and one websocket `/ws` (`routes.py`). Each message goes through `process_input` on the shared session, so slash commands, guardrails and persistence behave as in the CLI. Wire format: client sends `message`, `confirm` (`approved`), `stop`; server sends `history`, `text_chunk`, `notice`, `usage` (last budget event of the turn only), `error`, `confirm`, `done`. One turn at a time per connection. Local use only: no auth, bound to localhost.

Prompt log: `PromptComposer.compose_parts` returns `PromptPart`s (message + source: persona, step_limit, tools, privacy, memory, rag, summary, history). `ChatEngine._round` keeps them in `engine.last_prompt` (shown by `/prompt` via `format_prompt`) and, with `[eval] log_prompts`, hands `prompt_entry(...)` to a `PromptRecorder` (`eval/logger.PromptLogger`, `logs/prompts.jsonl`) in a `finally`, so failed calls are logged too. CLI command results print with `markup=False`.

Built but not wired into the runtime: `eval/logger.py` (`TurnLogger`), `Persona` (`build_prompt` accepts one, nothing passes it).

Empty stubs, not yet built: `tools/sandbox.py`.
Empty stubs, not yet built: `core/budget.py`, `memory/manager.py`, `memory/artifact.py`.

Guardrail scope and known limits: input, model output and tool results are filtered. Not covered: PII inside tool-call arguments written by the model, the RAG context injected into the prompt, names and postal addresses. Reference design: [docs/elevenlabs-guardrails.md](docs/elevenlabs-guardrails.md).

Sprint plan tracked as GitHub issues (milestones "Sprint 1 - Base Loop MVP", "Sprint 2 - Session, Tools, Logging", "Sprint 3 - Tools, Permissions, Eval").
