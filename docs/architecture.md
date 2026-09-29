# Technical Architecture Document — SENSAI

## 1. Project Overview

- **Business scenario (keynote)**: to be defined by the team.
- **Objective**: build a modular, framework-free AI assistant that talks directly to Ollama's native HTTP API.

## 2. Design Principles

- **Clean architecture & decoupling**: strict separation between domain (Pydantic models + Protocols), infrastructure (httpx/Ollama, SQLite), core logic (engine) and interfaces (CLI/TUI/Web). Dependencies only point downward.
- **Stream-first & event-driven**: real-time token streaming through typed events (`TextChunkEvent`, `ToolCallEvent`, `GuardrailEvent`).
- **Protocol seam**: `core/engine.py` depends on `domain/protocols.py` (`LLMProvider`, `ToolRegistry`, `Guardrail`, ...), never on concrete classes. Implementations are injected in `core/bootstrap.py`, shared by every interface.
- **No LLM frameworks**: custom tool-calling loop, custom RAG pipeline, custom guardrails. No LangChain, LlamaIndex or Haystack.

## 3. Layers

```text
interfaces/  cli (rich), tui (textual), web (stub)   + dispatcher, shared notices
core/        engine, bootstrap, commands, config, prompt, budget (stub)
providers/ tools/ memory/ eval/                      pluggable implementations
domain/      models, events, protocols, errors
```

## 4. Execution Pipeline (implemented)

```text
[User input]
      │
      ▼
[REPL / TUI] ── starts with "/" ──► [commands.py] (/help /clear /new /exit /config ...)
      │
      ▼
[ChatEngine.send]
      │
      ▼
[1. Input guardrail]   filter_input: injection ──► block | flag;  PII ──► redact | block
      │                 (only the filtered text goes further, and into the history)
      ▼
[2. Retrieval (RAG)]   embed the filtered query, add matching chunks to the prompt
      │
      ▼
[3. build_prompt]      conversation (+ optional persona, + retrieved context)
      │
      ▼
[4. LLMProvider]       stream from Ollama /api/chat
      │
      ▼
[5. Output guardrail]  PiiOutputStream: mask PII in the stream, even across chunk boundaries
      │
      ▼
tool calls? ── yes ──► [ToolRegistry.get(name).execute()] ──► [6. Tool-result guardrail]
      │                                                              │
      no                          "tool" message ─► back to step 3 ◄─┘  (max 5 iterations)
      ▼
[assistant message stored] ──► [renderer] ──► [SqliteMemoryStore.save]
```

Guardrails are optional (`[guardrails] enabled = true`). With none injected, the engine behaves exactly as without them. Whenever a guardrail acts, the engine yields a `GuardrailEvent` (stage, action, rule names, never the matched value) and the renderers display a one-line notice.

## 5. Guardrails (EV2) in detail

| Piece                           | Role                                                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `domain`: `GuardrailVerdict`    | Result of a check: `allow`, `redact`, `block` or `flag`, the text to use, and the findings (rule + category).                     |
| `eval/guardrails.py` detectors  | Regex + checksum validators (Luhn, IBAN mod-97, NIR key) for PII; heuristic rules for prompt injection.                           |
| `RegexGuardrail`                | Implements the `Guardrail` protocol: `filter_input`, `filter_output` (also used for tool results), `new_output_stream`.           |
| `PiiOutputStream`               | Incremental filter. Holds back a short tail (at least 48 characters, plus the trailing word up to 320) so a value is never split. |
| `core/config.py` `[guardrails]` | `enabled` (default off), `injection = block \| flag`, `pii = redact \| block`.                                                    |

Design choices and the reference design they were compared against are in [elevenlabs-guardrails.md](elevenlabs-guardrails.md).

## 6. Module Status

| Area                                         | Status                           |
| -------------------------------------------- | -------------------------------- |
| Domain models / events / protocols           | Done                             |
| Providers (Ollama, embeddings, mock)         | Done                             |
| Chat engine + tool-calling loop              | Done                             |
| Slash commands, TOML config                  | Done                             |
| Session persistence, SQLite (M1)             | Done (no user profile yet)       |
| FS tools with sandbox root (T4)              | Done                             |
| RAG chunker / vector store / retriever       | Done, enabled with `--rag-dir`   |
| CLI and TUI, shared bootstrap                | Done, `--ui cli\|tui`            |
| Content & privacy guardrails (EV2)           | Done, opt-in                     |
| Turn logger (EV3)                            | Built, not wired into the engine |
| Token budget (M2), artifact (M4), manager    | Stubs                            |
| MCP (T1), sandbox exec (T2), web search (T3) | Stubs                            |
| Evaluator (EV1)                              | Stub                             |
| Web interface (FastAPI SSE)                  | Stub                             |

## 7. Target Pipeline (planned additions)

Persona (A5) and user profile (M1) in the context builder, token budgeting (M2), MCP / sandbox / web-search tools (T1-T3), automated evaluation (EV1), logging and metrics (EV3), artifact updates (M4) and a web interface (X1) are planned on top of the pipeline above.
