# Configuration

Everything Sensai can be told lives in one TOML file, `sensai.toml` in the directory you
launch from (`--config <path>` picks another one). The file is local and ignored by Git.

## How a value is chosen

```text
CLI flag (--model, --provider, --base-url, --ui, --rag-*)  >  sensai.toml  >  built-in default
```

- A missing file means "all defaults". A file that is malformed or holds an invalid value
  stops Sensai with one line naming the key and the reason, never a traceback.
- Values are checked one by one (types, bounds such as `0 < top_p ≤ 1`) and across keys:
  `budget.max_tokens` must fit in `options.num_ctx - options.num_predict`, an enabled persona
  needs a text, `rag.chunk_overlap` must stay below `rag.chunk_size`.

## Three ways to edit it

### 1. Inside a session: `/config`

| Command                     | What it does                                                                       |
| --------------------------- | ---------------------------------------------------------------------------------- |
| `/config`                   | Every setting, by section, each tagged with where it comes from (see below)        |
| `/config show options`      | One section (or one key)                                                           |
| `/config get options.seed`  | One value                                                                          |
| `/config set <key> <value>` | Change a setting now: validated, applied to the next turn, saved to the file       |
| `/config reset <key>`       | Back to the default; the key is removed from the file                              |
| `/config keys [prefix]`     | Every setting with its type, default, whether it needs a restart, and what it does |
| `/config save`              | Write the whole session to the file (useful with `autosave = false`)               |

`/model`, `/provider`, `/effort` and `/persona on|off` are shortcuts that go through the same
path, so they are validated and saved the same way.

Values are read like TOML: `true`, `0.2`, `8192`, `"text"`, `["a", "b"]`. Plain words need no
quotes (`/config set model llama3.2:3b`, `/config set persona.name Sensai Collecte`). `none`
unsets a value (an option is then not sent to the model; `tools.fs_allowed_root none` turns the
file tools off).

```text
you: /config set options.temperature 0.7
options.temperature = 0.7 (saved to sensai.toml)
you: /config set options.num_ctx 2048
Invalid options.num_ctx: budget.max_tokens (8192) must not exceed options.num_ctx - options.num_predict (2048)
you: /config set rag.top_k 3
rag.top_k = 3 (applies on the next start; saved to sensai.toml)
```

Sources shown by `/config`:

| Source    | Meaning                                                           |
| --------- | ----------------------------------------------------------------- |
| `default` | Nobody set it                                                     |
| `file`    | `sensai.toml` sets it                                             |
| `flag`    | A CLI flag set it for this run (not written unless you change it) |
| `session` | Changed in this session while autosave was off, not saved yet     |

### 2. From the shell: `sensai config`

```bash
sensai config init                        # write a sensai.toml listing every setting, commented, at its default
sensai config                             # show all settings and their source
sensai config get reasoning.think
sensai config set options.temperature 0.2
sensai config reset options.temperature
sensai config keys guardrails             # describe a section
sensai config path                        # which file is used
```

Every action takes `--config <path>`. Errors print one line and exit with status 1.

### 3. By hand

Edit the file. Comments and key order are yours: Sensai keeps them when it writes a value.

## Saving: autosave

`autosave = true` (the default) writes each change the moment it is made, and only that key:
your comments, the order of keys, keys Sensai does not know and values given by CLI flags are
left alone. The file is replaced atomically, so a crash never leaves it half written.

Two safety nets:

- A change that the running session cannot use (an unknown provider, an unreadable persona file)
  is refused and nothing changes, in the session or in the file.
- If the key alone would make the file invalid at the next start (for example
  `persona.enabled = true` while the persona text only lives in the session), the other changed
  keys of the same section are written with it. If the file still would not load, it is put back
  as it was and the reply says `not saved: …`.

With `/config set autosave false`, changes stay in the session; `/config` lists them as
`unsaved` and `/config save` writes everything.

## Live or on restart

Most settings apply to the next turn: provider and model (the provider is rebuilt), options,
budget, guardrails, reasoning, persona, logs, tools (the tool registry is rebuilt, MCP tools
kept). Settings read once at start-up say `applies on the next start`: `interface`, `rag.*`,
`memory.enabled`, `reasoning.show_thoughts` and MCP servers.

## Context window: why `num_ctx` is set

Ollama runs every model with its own default window (4096 tokens on a machine without a
GPU) and **silently drops the start of a longer prompt**: the persona and system notes go
first. Sensai's budget assumes 8192 tokens, so `options.num_ctx` defaults to 8192 and is sent
with every request. `[options]` tables that do not mention `num_ctx` keep that default. To
use a smaller window, lower `budget.max_tokens` with it. Measured effect:
[benchmarks.md](benchmarks.md#context-window-limits).

## Every setting

Generated from the schema (`sensai config keys` prints the same list); a test keeps this table
in sync with the code.

| Key                        | Type                                        | Default                    | Live    | Meaning                                                                                                            |
| -------------------------- | ------------------------------------------- | -------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------ |
| `interface`                | "cli" \| "tui" \| "web"                     | `"cli"`                    | restart | Interface started by `sensai chat`                                                                                 |
| `provider`                 | str                                         | `"ollama"`                 | yes     | ollama, groq or mock                                                                                               |
| `model`                    | str                                         | `"qwen3.5:4b"`             | yes     | Model name for the provider                                                                                        |
| `base_url`                 | str                                         | `"http://localhost:11434"` | yes     | Ollama server URL                                                                                                  |
| `api_key`                  | str \| none                                 | `(unset)`                  | yes     | Groq key (prefer the GROQ_API_KEY variable)                                                                        |
| `autosave`                 | bool                                        | `true`                     | yes     | Write each change made in a session (/config set, /model, /provider, /effort, /persona) to the config file at once |
| `tools.fs_allowed_root`    | str \| none                                 | `"."`                      | yes     | Root of read_file/list_dir/write_file, relative to the launch directory; false turns the file tools off            |
| `tools.web_search`         | bool                                        | `true`                     | yes     | Register web_search (local SearXNG on :8888)                                                                       |
| `tools.sandbox`            | bool                                        | `true`                     | yes     | Register run_python (throwaway Docker container)                                                                   |
| `budget.max_tokens`        | int > 0                                     | `8192`                     | yes     | Token budget of a prompt; keep it within options.num_ctx                                                           |
| `budget.threshold`         | float > 0 ≤ 1                               | `0.8`                      | yes     | Share of max_tokens that triggers a summary                                                                        |
| `budget.keep_recent_turns` | int ≥ 1                                     | `4`                        | yes     | Latest turns always kept verbatim                                                                                  |
| `guardrails.enabled`       | bool                                        | `true`                     | yes     | Filter input, replies and tool results                                                                             |
| `guardrails.injection`     | "block" \| "flag"                           | `"block"`                  | yes     | On a prompt-injection match: block or warn only                                                                    |
| `guardrails.pii`           | "redact" \| "block"                         | `"redact"`                 | yes     | On personal data: mask it or refuse the text                                                                       |
| `eval.log_replies`         | bool                                        | `false`                    | yes     | Append each final reply to replies_path                                                                            |
| `eval.replies_path`        | str                                         | `"logs/replies.jsonl"`     | yes     | JSONL file of replies                                                                                              |
| `eval.log_prompts`         | bool                                        | `false`                    | yes     | Append every prompt sent to the model to prompts_path                                                              |
| `eval.prompts_path`        | str                                         | `"logs/prompts.jsonl"`     | yes     | JSONL file of prompts                                                                                              |
| `memory.enabled`           | bool                                        | `true`                     | restart | Structured memory tools and /memory                                                                                |
| `memory.auto_inject`       | bool                                        | `true`                     | yes     | Put the remembered facts in every prompt                                                                           |
| `reasoning.enabled`        | bool                                        | `true`                     | yes     | Step and thought events, think effort                                                                              |
| `reasoning.show_thoughts`  | bool                                        | `false`                    | restart | Show thoughts and steps (answers then appear per round)                                                            |
| `reasoning.max_steps`      | int ≥ 1                                     | `5`                        | yes     | Tool rounds before a forced tool-free answer                                                                       |
| `reasoning.think`          | bool \| "low" \| "medium" \| "high" \| none | `"low"`                    | yes     | Thinking effort: "low", "medium", "high", false (off) or true                                                      |
| `persona.enabled`          | bool                                        | `false`                    | yes     | Lead every prompt with the persona                                                                                 |
| `persona.name`             | str                                         | `"Sensai"`                 | yes     | Name shown by /persona                                                                                             |
| `persona.instruction`      | str \| none                                 | `(unset)`                  | yes     | Persona text (or use file, not both)                                                                               |
| `persona.file`             | str \| none                                 | `(unset)`                  | yes     | Text file holding the persona, relative to the launch directory                                                    |
| `rag.enabled`              | bool                                        | `false`                    | restart | Index dir at launch and retrieve per question                                                                      |
| `rag.dir`                  | str \| none                                 | `(unset)`                  | restart | Directory of .md/.txt files                                                                                        |
| `rag.model`                | str                                         | `"nomic-embed-text"`       | restart | Ollama embedding model                                                                                             |
| `rag.db`                   | str                                         | `"rag.db"`                 | restart | SQLite index file                                                                                                  |
| `rag.top_k`                | int ≥ 1                                     | `5`                        | restart | Chunks added to each prompt                                                                                        |
| `rag.chunk_size`           | int > 0                                     | `500`                      | restart | Characters per chunk                                                                                               |
| `rag.chunk_overlap`        | int ≥ 0                                     | `50`                       | restart | Characters shared by consecutive chunks (< chunk_size)                                                             |
| `options.temperature`      | float \| none ≥ 0                           | `(unset)`                  | yes     | Sampling temperature: 0 is repeatable                                                                              |
| `options.num_ctx`          | int \| none > 0                             | `8192`                     | yes     | Context window in tokens (Ollama's own default is 4096 here)                                                       |
| `options.top_p`            | float \| none > 0 ≤ 1                       | `(unset)`                  | yes     | Nucleus sampling cut-off                                                                                           |
| `options.seed`             | int \| none                                 | `(unset)`                  | yes     | Fixed seed for repeatable runs                                                                                     |
| `options.num_predict`      | int \| none > 0                             | `(unset)`                  | yes     | Maximum tokens in one reply                                                                                        |

### MCP servers

Edited in the file only, one table per server; the table name prefixes the tool names
(`github__list_issues`). Details: [features/mcp.md](features/mcp.md).

```toml
[mcp.servers.github]
command = "docker"
args = ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server", "stdio", "--read-only", "--toolsets", "issues"]
timeout = 30.0

[mcp.servers.github.env]
GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_..."
```

## Example

```toml
model = "qwen3.5:4b"

[options]
temperature = 0.2
seed = 42

[rag]
enabled = true
dir = "data/collecte"

[persona]
enabled = true
name = "Sensai Collecte"
file = "personas/collecte.md"
```

## Where the code is

| File                       | Role                                                                     |
| -------------------------- | ------------------------------------------------------------------------ |
| `core/config.py`           | Schema (pydantic, with descriptions), `load_config`, `save_config`       |
| `core/config_file.py`      | TOML editing that keeps comments (tomlkit), atomic writes                |
| `core/settings.py`         | Dotted keys: catalog, parsing, validation, sources, formatting, template |
| `core/components.py`       | Applies a changed setting to the running session                         |
| `core/commands.py`         | `/config` and the shortcuts that change settings                         |
| `interfaces/cli/config.py` | `sensai config` in the shell                                             |
