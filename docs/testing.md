# Testing

About 1 250 tests, all offline, in about 25 seconds. A handful of "live" tests talk to a real
model, Docker or GitHub and are skipped unless you ask for them.

## Running them

```bash
make test              # every test, by title, with its result
make test-report       # same, and writes reports/tests.md (one table per file)
make test-classic      # plain pytest output (dots)
make coverage          # coverage per file, missing lines
uv run pytest tests/eval/guardrails          # one area
uv run pytest tests/core/test_config.py -k autosave   # one topic
```

## What the output looks like

Every test prints on its own line under the file it belongs to. The title is the first line
of the test's docstring, or its name made readable. A file's title is its module docstring.

```text
core/config_file — Config file editing: comments and unknown keys survive every write
  ✓ Missing file reads as an empty document
  ✓ Update keeps comments and unknown keys
  ✓ Removing the last key of a table drops the table

tools/sandbox — Python sandbox (T2), with optional live Docker tests
  ✓ Timeout kills the container  (0.52 s)
  – Live › Runs code in a container  — set SENSAI_LIVE_SANDBOX=1 (needs Docker …)

=============================== results by area ================================
  core          442 passed    0 failed    0 skipped
  eval          382 passed    0 failed    1 skipped
  ...
```

| Mark | Meaning                                              |
| ---- | ---------------------------------------------------- |
| ✓    | passed                                               |
| ✗    | failed or errored, with the first line of the reason |
| –    | skipped, with the reason (usually how to enable it)  |
| ~ !  | expected failure / unexpected pass                   |

Tests slower than half a second show their time. Failures still get pytest's full traceback
and short summary at the end. `-v`, `-q` or `--classic` turn the titles off.
`--test-report PATH` writes the same list as Markdown, handy for a review or a slide.

The reporter is a small pytest plugin in `tests/conftest.py`; it only changes how results are
printed.

## Layout

`tests/` mirrors `src/sensai/` one to one: `src/sensai/core/settings.py` is tested by
`tests/core/test_settings.py`. Every new source file comes with its test file in the same
change.

| Area         | What is covered                                                                      |
| ------------ | ------------------------------------------------------------------------------------ |
| `core`       | engine loop, streaming, tools runner, prompt, budget, config, `/commands`, bootstrap |
| `domain`     | models and events                                                                    |
| `eval`       | guardrails, adversarial corpus, LLM judge, loggers, benchmarks                       |
| `interfaces` | CLI, TUI, web socket protocol, notices, diff, `sensai config`                        |
| `memory`     | sessions, structured memory, RAG chunker/store/retriever                             |
| `providers`  | Ollama, Groq, mock, registry                                                         |
| `tools`      | files, web search, sandbox, MCP, memory tools                                        |

Unit tests use `MockLLMProvider`, `httpx.MockTransport` or tiny fakes, never a network.

## Live tests

| Test                        | Command                                                                                    | Needs                                   |
| --------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------- |
| Model picks the right tools | `SENSAI_OLLAMA_TEST_MODEL=qwen3.5:4b uv run pytest tests/providers/test_ollama.py -k live` | Ollama + the model                      |
| LLM judge                   | `SENSAI_LIVE_JUDGE=1 SENSAI_LIVE_MODEL=qwen3.5:4b uv run pytest tests/eval/judge`          | Ollama                                  |
| Docker sandbox              | `SENSAI_LIVE_SANDBOX=1 uv run pytest tests/tools/test_sandbox.py`                          | Docker + `python:3.12-alpine`           |
| GitHub MCP server           | `SENSAI_LIVE_MCP=1 uv run pytest tests/tools/test_mcp_live.py`                             | Docker + `GITHUB_PERSONAL_ACCESS_TOKEN` |

The model benchmarks ([benchmarks.md](benchmarks.md)) are the other "real" check: they measure
answers, where unit tests check code.

## Known weak spot

`tests/eval/guardrails/test_pii.py::test_detectors_stay_linear_on_hostile_input` asserts a
wall-clock bound (2 s). It passes in milliseconds on an idle machine but can fail while
another process saturates the CPU (an Ollama benchmark, for instance).
