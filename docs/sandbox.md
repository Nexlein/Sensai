# The code sandbox in Sensai

How the assistant runs Python without putting your machine at risk, explained from scratch. For the short "what do I need" version, see the Code execution section of the [README](../README.md). The tool-calling loop itself is explained in [docs/mcp.md](mcp.md), section 1.

## Contents

1. [Why a sandbox](#1-why-a-sandbox)
2. [The tool the model sees](#2-the-tool-the-model-sees)
3. [One run, step by step](#3-one-run-step-by-step)
4. [What the container is not allowed to do](#4-what-the-container-is-not-allowed-to-do)
5. [Confirmation: you read the code first](#5-confirmation-you-read-the-code-first)
6. [What the model gets back](#6-what-the-model-gets-back)
7. [Timeouts and cleanup](#7-timeouts-and-cleanup)
8. [When things go wrong](#8-when-things-go-wrong)
9. [Setup](#9-setup)
10. [Testing](#10-testing)
11. [Known limits](#11-known-limits)
12. [File map](#12-file-map)
13. [FAQ](#13-faq)

---

## 1. Why a sandbox

A model that can write code is much more useful when it can also **run** it: it computes instead of guessing, and when its script fails it reads the traceback and fixes it.

But generated code is untrusted. It may be wrong, it may loop forever, and a prompt injection hidden in a web page could make it malicious. Running it inside the Sensai process, or directly on your machine, would give that code your files, your network and your user rights.

So Sensai runs it in a **throwaway Docker container** that has none of those things. Two layers protect you:

1. **Confirmation.** Every run asks you first, and you see the whole script (section 5).
2. **Isolation.** Even a script you approved cannot reach your files or the network (section 4).

## 2. The tool the model sees

`run_python` is a normal Sensai tool, like `read_file` or `web_search`. The model receives its name, a description and two arguments:

| Argument  | Required | Meaning                                                          |
| --------- | -------- | ---------------------------------------------------------------- |
| `code`    | yes      | The complete Python 3 source. Results must be printed to stdout. |
| `timeout` | no       | Seconds before the run is killed. Default 10, capped at 60.      |

It is a `SensitiveTool` (`requires_confirmation = True`), so the engine will not execute it without an explicit yes. The description tells the model the sandbox has no network and no access to your files, and to fix and rerun the code if it fails.

## 3. One run, step by step

```
model asks for run_python(code=...)
        │
        ▼
ChatEngine._run_tool        builds the preview (the code as a diff)
        │
        ▼
UI shows the code + "Allow run_python?"      you answer yes / no
        │ yes
        ▼
RunCodeTool.execute         validates the arguments
        │
        ▼
docker run --rm -i ... python -I -           the code is written to its stdin
        │
        ▼
exit code + stdout + stderr  ──►  back to the model, which writes the answer
```

The code travels through **stdin**, never through a file on disk, so nothing from your machine is mounted into the container. `python -I` is Python's isolated mode: it ignores environment variables and the current directory when importing.

Every run starts a new container named `sensai-sandbox-<random>` and removes it afterwards (`--rm`). Nothing persists between runs: a variable defined in one call does not exist in the next, and the model has to send the whole script each time.

## 4. What the container is not allowed to do

| Flag                               | Effect                                                            |
| ---------------------------------- | ----------------------------------------------------------------- |
| `--network none`                   | No network at all: no downloads, no calls out, no data leaving.   |
| `--read-only`                      | The image filesystem cannot be written to.                        |
| `--tmpfs /tmp:rw,size=16m`         | The only writable place: 16 MB of memory-backed scratch space.    |
| no `-v` / `--volume`               | Your files are not in the container. Not even the project folder. |
| `--cap-drop ALL`                   | No Linux capabilities (no mounting, no raw sockets, and so on).   |
| `--security-opt no-new-privileges` | A program cannot gain rights through setuid binaries.             |
| `--user 65534:65534`               | Runs as `nobody`, not root.                                       |
| `--memory 256m --memory-swap 256m` | At most 256 MB of RAM, and no swap to spill into.                 |
| `--cpus 1`                         | At most one CPU core.                                             |
| `--pids-limit 64`                  | At most 64 processes: a fork bomb stops at 64.                    |

The command is built in `RunCodeTool._command`, and a unit test checks the important flags are present and that no volume is ever mounted.

## 5. Confirmation: you read the code first

A confirmation that only said "Allow run_python?" would be useless, because you would be approving something you cannot see. So `RunCodeTool.preview` turns the code into a unified diff made only of added lines, and the existing diff display shows it above the question:

```
● run_python
  ⎿  +3 -0
     1 + import math
     2 + print(math.factorial(20))
     3 +
  Allow run_python?
    timeout  10
    ❯ Yes   No
```

The UI hides the `code` argument from the question's detail lines, since the diff above already shows it (the same trick used for `content` in `write_file`).

Two rules come from the confirmation gate itself, not from this tool:

- If the UI callback crashes, the run is treated as **declined**, never as approved.
- A decline sends the model the message `Tool execution declined by the user.` and the turn ends with "I didn't run the requested tool".

The whole script is drawn, however long, so you read all of it before you allow it.

## 6. What the model gets back

On any run that actually started, the tool returns three parts:

```
exit code: 0
stdout:
42

stderr:
(empty)
```

A failing script is **not** a tool error. It is a normal result with a non-zero exit code and the traceback in stderr, because that is exactly what the model needs to fix its code:

```
exit code: 1
stdout:
(empty)
stderr:
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
ZeroDivisionError: division by zero
```

Each of stdout and stderr is cut at 4000 characters, with a note like `… [1200 more chars]`, so one chatty script cannot fill the model's context window. Like every tool result, the output also goes through the guardrails before the model sees it (personal data in it is masked).

## 7. Timeouts and cleanup

The default limit is 10 seconds, the model can ask for more with `timeout`, and the tool never allows more than 60. `timeout` must be a positive number; text, booleans, zero and negatives are refused before any container starts.

When the time is up:

1. `docker kill <name>` stops the container itself. This matters: killing only the local `docker` command would leave the script running inside the daemon.
2. The local `docker` process is killed and awaited.
3. The model receives `Error: timed out after 10s and was killed`.

If you stop the turn yourself (Ctrl+C in the CLI, Esc in the TUI), the same cleanup runs and the cancellation then continues normally.

## 8. When things go wrong

| What happened                                                                | What the model receives                                   |
| ---------------------------------------------------------------------------- | --------------------------------------------------------- |
| The script raised an exception                                               | exit code 1 plus the traceback on stderr                  |
| The script ran past its timeout                                              | `Error: timed out after Ns and was killed`                |
| `code` is missing, empty or not a string                                     | `Error: code must be a non-empty string`                  |
| `timeout` is not a number, or is zero or negative                            | `Error: timeout must be a number` / `must be positive`    |
| The `docker` binary does not exist                                           | `Error: sandbox unavailable, could not start Docker: ...` |
| Docker is installed but failed (daemon down, image missing and not pullable) | `Error: sandbox unavailable: <docker's message>`          |

The last row is told apart by Docker's own exit codes (125 to 127) with an empty stdout. Without that, "the daemon is not running" would look like a script bug and the model would waste turns trying to fix perfectly good code.

## 9. Setup

You need Docker running and the image available locally:

```bash
docker pull python:3.12-alpine
```

If the image is missing, `docker run` tries to download it, and that download counts against the 10-second timeout. Pull it once beforehand.

There is nothing to configure: the tool is registered by `build_default_registry` next to the other built-in tools. The image name and Docker binary are constructor arguments of `RunCodeTool`, not settings in `sensai.toml` yet.

## 10. Testing

| What                                                                   | Where                                       | Needs                                      |
| ---------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------ |
| The tool against a **fake `docker`** executable                        | `tests/tools/test_sandbox.py`               | nothing                                    |
| The registry contains `run_python`                                     | `tests/tools/test_tool_registry.py`         | nothing                                    |
| The confirmation hides `code` when a preview is shown                  | `tests/interfaces/test_prompts.py`          | nothing                                    |
| **Real containers**: network cut, files hidden, read-only, loop killed | `TestLive` in `tests/tools/test_sandbox.py` | Docker, the image, `SENSAI_LIVE_SANDBOX=1` |

The fake `docker` is a few lines of Python written into a temporary directory and passed as `docker_bin`. It echoes stdin, writes a traceback, sleeps forever or exits with 125, depending on the test, and records the `docker kill` call. That checks all the Python-side logic (validation, clipping, timeout, error mapping) without needing Docker.

Run everything except the live tests:

```bash
uv run python -m pytest
```

Run the live tests:

```bash
docker pull python:3.12-alpine
SENSAI_LIVE_SANDBOX=1 uv run python -m pytest tests/tools/test_sandbox.py
```

They run real code and check, from inside the container, that a socket to the internet fails, that a file created on the host is not visible, that writing to `/` fails, and that `while True: pass` is killed.

## 11. Known limits

- **Python only.** There is no shell or Node variant.
- **No packages.** The image has the standard library only, and with no network `pip install` cannot work. Scripts needing numpy or requests will fail with `ModuleNotFoundError`.
- **No state and no files in or out.** Each run is fresh, and the model cannot read your project from inside the sandbox or write results back. For that it uses `read_file` and `write_file`, which have their own confirmation.
- **Output is buffered before it is clipped.** A script that prints gigabytes inside 10 seconds would fill Sensai's memory before the 4000-character cut applies. The container's 256 MB limit does not cover output already sent to the host.
- **Docker is a strong wall, not an absolute one.** Containers share the host kernel, so a kernel or runtime bug could in theory be used to escape. The flags above remove most of the surface, but this is not a virtual machine.
- **Access to Docker is itself powerful.** A user who can run Docker commands usually has rights close to root on the host. This is a property of Docker, not of Sensai.
- **Fixed image and limits.** The image, memory, CPU and process caps are constants in `sandbox.py`, not config.
- **The confirmation is the main guard.** Isolation limits the damage, but a script can still burn 10 seconds of one CPU core per run, and it can still print misleading text into the model's context.

## 12. File map

| File                               | Role                                                          |
| ---------------------------------- | ------------------------------------------------------------- |
| `src/sensai/tools/sandbox.py`      | `RunCodeTool`: arguments, preview, Docker command, result     |
| `src/sensai/tools/registry.py`     | Registers `RunCodeTool()` with the built-in tools             |
| `src/sensai/tools/base.py`         | `SensitiveTool`, which sets `requires_confirmation`           |
| `src/sensai/core/engine.py`        | Builds the preview and asks for confirmation before `execute` |
| `src/sensai/interfaces/diff.py`    | Draws the preview diff                                        |
| `src/sensai/interfaces/prompts.py` | The question; hides `code` when a preview is shown            |
| `tests/tools/test_sandbox.py`      | Unit tests and the opt-in live tests                          |

## 13. FAQ

**Is it safe to answer yes without reading?**
Safer than without the sandbox, but still read. Isolation stops the script reaching your files and network, not wasting CPU or producing misleading output.

**Why not just run a subprocess on my machine?**
A subprocess is the same user with the same files and the same network. Resource limits do not change that. Only a container (or a VM) puts a real wall around the code.

**Can it install a package?**
No. There is no network, so `pip` cannot download anything.

**Why did it work in the container but my project's imports do not?**
The container does not contain your project or your virtual environment. It is a clean Python.

**Is anything left on my machine after a run?**
No. The container is removed on exit, the code only travelled through stdin, and `/tmp` inside it was memory-backed. After a timeout, `docker ps -a` should show no `sensai-sandbox-*` container.

**Does the model see my files?**
Not through this tool. It only sees what you or another tool put in the conversation.

**The model printed the tool call as text instead of answering. Is that the sandbox?**
No. The run succeeded and the model got the output; weak models sometimes echo the call back instead of summarising. Try another model.

**Can I use a different image or a custom Docker binary?**
In code: `RunCodeTool(image="python:3.13-slim", docker_bin="podman")`. Podman accepts the same flags in most setups, but this is untested.
