# Architecture

Sensai is a local assistant written in plain Python on top of the Ollama HTTP API: no LLM
framework, a custom tool-calling loop, a custom RAG pipeline and custom guardrails.

## Layers

Dependencies only point down.

```text
interfaces/   cli (rich), tui (textual), web (FastAPI + websocket), shared wording
core/         engine, streaming, tool runner, prompt, budget, config, settings, commands, bootstrap
providers/    Ollama (chat + embeddings), Groq (opt-in), mock
tools/        files, web search, Python sandbox, MCP client, memory tools
memory/       sessions, structured memory, RAG (chunker, vector store, retriever)
eval/         guardrails, adversarial corpus, LLM judge, loggers, benchmarks
domain/       pydantic models, events, protocols, errors — no dependency on anything above
```

`domain/protocols.py` is the seam: `core/engine.py` types against `LLMProvider`,
`ToolRegistry`, `Guardrail`, `ContextRetriever`… never against a concrete class. Concrete
classes are chosen in one place, `core/bootstrap.py` (`build_session`), shared by the three
interfaces. Tests inject fakes at the same seam.

## One turn

```text
user text ──► "/..." ? ──► core/commands.py (/config, /model, /memory, /prompt, /ps …)
   │
   ▼
ChatEngine.send
   1. input guardrail      injection → block | flag, personal data → mask | block
   2. retrieval (RAG)      embed the filtered question, add the closest chunks
   3. prompt               persona · tool guidance · privacy note · memory · RAG · summary · history
   4. budget               summarize old turns past 80 % of budget.max_tokens
   5. model call           Ollama /api/chat, streamed (NDJSON) as typed events
   6. output guardrail     mask personal data in the stream, even split across chunks
   7. tool calls?          confirm if sensitive → run → filter the result → back to 3
                           (at most reasoning.max_steps rounds, then a tool-free answer)
   ▼
answer stored, session saved (SQLite), usage line shown
```

Everything flows as typed events (`TextChunkEvent`, `ToolCallEvent`, `ThoughtEvent`,
`GuardrailEvent`, `UsageEvent`, `BudgetEvent`…), which each interface renders its own way.
A cancelled or failed turn removes the unanswered user message, so history stays consistent.

## Where things live

| Concern                      | Code                                                                              | Doc                                                                  |
| ---------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Turn loop, steps, step limit | `core/engine.py`, `core/streaming.py`, `core/tool_runner.py`, `core/turn.py`      | —                                                                    |
| Prompt and its sources       | `core/prompt.py` (`/prompt`, `[eval] log_prompts`)                                | —                                                                    |
| Token budget (M2)            | `core/budget/`                                                                    | —                                                                    |
| Settings                     | `core/config.py`, `core/config_file.py`, `core/settings.py`, `core/components.py` | [configuration.md](configuration.md)                                 |
| Guardrails (EV2)             | `eval/guardrails/`                                                                | [features/guardrails-reference.md](features/guardrails-reference.md) |
| Adversarial suite, judge     | `eval/adversarial/`, `eval/judge/`, `eval/evaluator.py`                           | [features/evaluation.md](features/evaluation.md)                     |
| Benchmarks                   | `eval/bench/`                                                                     | [benchmarks.md](benchmarks.md)                                       |
| RAG (R1)                     | `memory/rag/`                                                                     | —                                                                    |
| Sessions, structured memory  | `memory/session.py`, `memory/manager.py`, `tools/memory.py`                       | [features/memory.md](features/memory.md)                             |
| Files (T4)                   | `tools/fs.py` (confined to `tools.fs_allowed_root`)                               | —                                                                    |
| Web search (T3)              | `tools/web.py` (local SearXNG)                                                    | —                                                                    |
| Python sandbox (T2)          | `tools/sandbox.py` (throwaway Docker container)                                   | [features/sandbox.md](features/sandbox.md)                           |
| MCP (T1)                     | `tools/mcp.py` (stdio JSON-RPC client)                                            | [features/mcp.md](features/mcp.md)                                   |
| Interfaces                   | `interfaces/cli/`, `interfaces/tui/`, `interfaces/web/`                           | —                                                                    |

## Design choices in one line each

- **Streaming first**: replies are rendered token by token; the output filter only holds back
  the last 48 characters (an IBAN fits) so a value is never shown half-masked.
- **Deterministic guardrails** (regex + checksums) instead of a classifier model: microseconds
  per message (see [benchmarks](benchmarks.md#sensais-own-code)), testable, no extra model call.
- **SQLite everywhere** (sessions, facts, vectors): one file, no service to run.
- **Human in the loop**: every tool that writes, runs code, searches the web or calls MCP asks
  first, with a full diff or the full code.
- **Settings are self-describing**: every key has a type, a default and a description in the
  schema; `/config`, `sensai config`, the template and the reference doc all come from it.

The reasoning behind the bigger choices, with alternatives, is in
[soutenance/decisions.md](soutenance/decisions.md) (French). Known weaknesses are in the
[code review](code-review.md).
