# Sensai

A local AI assistant that runs on your own machine through [Ollama](https://ollama.com/):
streaming chat, tools (files, web search, Python sandbox, MCP), document retrieval (RAG),
long-term memory and privacy guardrails, in a terminal, a TUI or a browser. Plain Python, no
LLM framework.

Demo scenario: _Sensai Collecte_, the assistant of a (fictional) waste-collection authority,
answering team leaders from their own rule books without sending data anywhere
([docs/soutenance/scenario.md](docs/soutenance/scenario.md)).

## Features

| Feature                | What it does                                                                                                | Turn it off / on          |
| ---------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------- |
| Streaming chat (B1)    | Replies appear token by token; history kept in the session; one-line errors                                 | —                         |
| Sessions (M1)          | `--session name` resumes a saved conversation (SQLite)                                                      | —                         |
| Token budget (M2)      | Old turns are summarized before the prompt outgrows the window                                              | `[budget]`                |
| Structured memory (M3) | Remembers facts (`user.secteur = B`) across sessions; `/memory` to view or edit                             | `[memory] enabled`        |
| RAG (R1)               | Answers from your Markdown/text files, with sources                                                         | `[rag]` or `--rag-dir`    |
| File tools (T4)        | Read, list and write files inside one folder; every write shows a diff and asks                             | `[tools] fs_allowed_root` |
| Web search (T3)        | Through a local SearXNG; asks before searching                                                              | `[tools] web_search`      |
| Python sandbox (T2)    | Runs code in a locked-down Docker container; shows the code and asks                                        | `[tools] sandbox`         |
| MCP tools (T1)         | Uses tools of any MCP server (stdio); asks before each call                                                 | `[mcp.servers.*]`         |
| Reasoning (A1)         | Tool rounds with optional visible thoughts; thinking effort with `/effort`                                  | `[reasoning]`             |
| Human in the loop (A3) | Every sensitive tool waits for your yes                                                                     | —                         |
| Persona (A5)           | A domain system prompt, switchable live with `/persona on\|off`                                             | `[persona]`               |
| Guardrails (EV2)       | Blocks prompt injection; masks emails, phones, IBANs, cards, French SSNs in input, replies and tool results | `[guardrails]`            |
| Evaluation (EV1, EV4)  | LLM judge for replies; adversarial attack suite                                                             | `python -m sensai.eval.*` |
| Observability          | `/prompt` shows the exact prompt; real token counts and tok/s after each reply; `/ps` shows RAM/VRAM        | `[eval] log_prompts`      |
| Web and TUI (X1)       | `--ui web` (localhost) or `--ui tui`                                                                        | `interface`               |

## Quick start

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/).
Docker is optional (sandbox, SearXNG).

```bash
git clone git@github.com:Nexlein/Sensai.git && cd Sensai
make setup                       # dependencies + git hooks
ollama pull qwen3.5:4b           # default chat model
ollama pull nomic-embed-text     # only for RAG
uv run sensai chat
```

```text
you: Bonjour, tu sers à quoi ?
sensai: Je suis Sensai, un assistant local…
2.1k / 8.2k tokens (25%)
prompt 412 tok · reply 96 tok · 12.4 tok/s · first token 3.1 s · total 11.0 s
```

`Ctrl+C` stops the current reply; `/exit` or `Ctrl+D` leaves.

## Usage examples

```bash
uv run sensai chat --model llama3.2:3b             # another model for this run
uv run sensai chat --ui web                        # http://127.0.0.1:8000
uv run sensai chat --ui tui
uv run sensai chat --session incident-1018         # resume or create a named session
uv run sensai chat --rag-dir data/collecte         # answer from these documents
uv run sensai chat --provider mock                 # offline demo, no model needed
```

Inside a session:

| Command                                                                       | Effect                                                     |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `/help`                                                                       | All commands                                               |
| `/model qwen3.5:9b`, `/provider ollama`                                       | Switch model or provider for the next turn                 |
| `/effort [low\|medium\|high\|off]`                                            | Thinking effort (picker without argument)                  |
| `/persona on\|off`                                                            | Switch the domain persona                                  |
| `/config`, `/config set <key> <value>`, `/config reset <key>`, `/config keys` | Settings, see below                                        |
| `/memory`, `/memory set user secteur B`, `/memory search B`                   | Long-term facts                                            |
| `/prompt`                                                                     | The full prompt of the last model call, message by message |
| `/ps`                                                                         | Models in memory, size, CPU/GPU split                      |
| `/new`, `/clear`                                                              | New conversation / empty this one                          |

Example with the scenario corpus and persona:

```text
you: Il a neigé cette nuit, qu'est-ce que je dois changer ?
sensai: L'Opération Hérisson s'applique : prise de poste décalée d'une heure (secteurs B et C : 7 h 00),
chaînes montées au dépôt, aucun agent sur le marchepied… [plan-hivernal-herisson.md]
you: Écris le rapport d'incident dans rapports/2026-10-21-tilleuls.md
Allow write_file?   (the full diff of the file is shown first)
✓ allowed write_file
```

## Configuration

One file, `sensai.toml`, in the launch directory. Precedence: CLI flag > file > default.

```bash
uv run sensai config init                          # documented file with every setting
uv run sensai config set options.temperature 0.2
uv run sensai config keys rag                      # what each RAG setting does
```

Inside a session, `/config set` applies a change to the next turn and **saves it at once**
(`autosave = true`), keeping your comments in the file. Invalid values are refused with one
line. Full reference, every key, live vs restart: [docs/configuration.md](docs/configuration.md).

```toml
model = "qwen3.5:4b"

[options]
temperature = 0.2
num_ctx = 8192          # default; must hold budget.max_tokens

[rag]
enabled = true
dir = "data/collecte"

[persona]
enabled = true
name = "Sensai Collecte"
file = "personas/collecte.md"
```

### Optional services

- **Web search**: `cp .env.example .env`, set `SEARXNG_SECRET` (`openssl rand -hex 32`), then
  `docker compose up -d searxng` (SearXNG on `127.0.0.1:8888`).
- **Python sandbox**: `docker pull python:3.15-alpine`. Details: [docs/features/sandbox.md](docs/features/sandbox.md).
- **MCP servers**: one `[mcp.servers.<name>]` table each. Details: [docs/features/mcp.md](docs/features/mcp.md).
- **Groq** (hosted, opt-in, not local): `provider = "groq"`, a Groq model name and `GROQ_API_KEY`.
  RAG embeddings stay on Ollama.

## Performance in short

Measured on an i7-13650HX with 16 GB of RAM, Ollama on CPU (RAG A/B on the RTX 4060)
([full results and method](docs/benchmarks.md)):

| What                                                          | Measured                                                                |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Sensai's own work per turn (prompt, guardrails, session save) | under 5 ms                                                              |
| Start-up                                                      | 216 ms                                                                  |
| qwen3.5:4b (default): first token / writing speed             | ~7 s / 11 tokens/s                                                      |
| Fastest model: granite3.1-moe                                 | 46 tokens/s, but never calls tools                                      |
| Right tool chosen (10 cases)                                  | qwen3.5:4b and gemma4:e4b 10/10; granite, mistral, phi4-mini 4/10       |
| Fact found in a long prompt                                   | yes up to 25 000 tokens, but 9 min to read on CPU; 8 192 window ≈ 100 s |
| Thinking on vs off (same right answer)                        | 7 min vs 16 s                                                           |
| RAG on the demo corpus (22 questions, GPU)                    | 23 % → 82 % right answers; 3 min for the whole A/B                      |

The model is the only slow part. Running Ollama on the GPU (CUDA build) is the biggest win
left; see the [code review](docs/code-review.md) for the rest.

## Development

```bash
make test          # every test by title with ✓/✗, summary per area (about 25 s)
make test-report   # same, plus reports/tests.md
make coverage      # coverage per file
make lint          # ruff
make format        # ruff format + prettier
uv run python -m sensai.eval.bench perf           # Sensai's own overhead, no model
uv run python -m sensai.eval.bench speed          # every installed model
uv run python -m sensai.eval.bench rag            # RAG / persona A/B on 22 questions
```

Conventions for contributors and AI agents: [AGENTS.md](AGENTS.md). Architecture, code review
and testing guide: [docs/](docs/README.md).

## Team

Nielsen Combe-Bracciale (Nexlein), Teddy Bertrand, Mathys Aberkane (Vulcaaa), Alban Lambrez
(Saitamadupauvre) — Epitech.
