# MCP in Sensai

How Sensai talks to MCP servers, explained from scratch. Written for someone who has never used MCP or tool calling. For the short "how do I configure it" version, see the MCP section of the [README](../README.md).

## Contents

1. [Why tools exist](#1-why-tools-exist)
2. [What MCP is](#2-what-mcp-is)
3. [The three actors](#3-the-three-actors)
4. [Vocabulary](#4-vocabulary)
5. [Declaring a server: the config](#5-declaring-a-server-the-config)
6. [Connecting: what happens at startup](#6-connecting-what-happens-at-startup)
7. [The protocol: JSON-RPC over stdio](#7-the-protocol-json-rpc-over-stdio)
8. [Telling the model about the tools](#8-telling-the-model-about-the-tools)
9. [Handling a question and its response](#9-handling-a-question-and-its-response)
10. [Confirmation: why every call asks first](#10-confirmation-why-every-call-asks-first)
11. [When things go wrong](#11-when-things-go-wrong)
12. [Shutting down](#12-shutting-down)
13. [Testing](#13-testing)
14. [Adding your own server](#14-adding-your-own-server)
15. [Known limits](#15-known-limits)
16. [File map](#16-file-map)
17. [FAQ](#17-faq)

---

## 1. Why tools exist

A language model only produces text. On its own it cannot read your GitHub issues, search the web, or run code. It also does not know anything that happened after its training.

**Tool calling** works around this with a simple agreement between the app and the model:

1. The app sends the model your question plus a list of functions it may use ("tools"), each with a name, a description and the arguments it takes.
2. If the model decides it needs one, it does not answer. It replies with "please call function X with these arguments".
3. The app runs the function, then sends the result back to the model.
4. The model reads the result and writes the final answer.

The model never runs anything itself. It only asks. The app decides whether to do it.

Sensai already had this loop with its own Python tools (`read_file`, `list_dir`, `write_file`, `web_search`). Each of those is code inside Sensai.

## 2. What MCP is

**MCP (Model Context Protocol)** is a standard that lets tools live in a **separate program**, called an **MCP server**, instead of inside the app. Anyone can write a server, and any app that speaks MCP can use it.

For Sensai this means:

- There is no GitHub code in Sensai. A GitHub MCP server exists, and Sensai just talks to it.
- Adding a tool is a few lines of config, not new Python.
- The same server works in other MCP apps too.

MCP defines many things (resources, prompts, several transports). Sensai implements **only the tool part, over the stdio transport**. That is enough to use the large majority of servers people publish.

## 3. The three actors

```
 You ──question──▶  Sensai  ◀────── JSON messages ──────▶  MCP server
                    (the "client")                          (separate process:
                       │                                    GitHub, Context7, ...)
                       └─── prompt + tool list ───▶  LLM (Ollama)
```

- **Sensai** is the MCP _client_. It is the middleman.
- The **LLM** never talks to the MCP server. It only sees names and descriptions of tools, and asks Sensai to call them.
- The **MCP server** never sees your question or the conversation. It only receives "run tool T with arguments A" and returns a result.

This split is why Sensai can sit between them and ask you for permission (section 10).

## 4. Vocabulary

| Term                | Meaning                                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **MCP server**      | A program that offers tools. Run as a child process of Sensai.                                                                                               |
| **MCP client**      | The part of Sensai that talks to a server (`McpClient`).                                                                                                     |
| **Tool**            | One function the server offers, e.g. `list_issues`.                                                                                                          |
| **Tool schema**     | The description of a tool: name, description, and a JSON Schema (`inputSchema`) saying which arguments it takes.                                             |
| **Transport**       | How messages travel. Sensai uses **stdio**: the server's standard input and output.                                                                          |
| **JSON-RPC 2.0**    | The message format: small JSON objects, "call method M with params P, tell me the result".                                                                   |
| **Request**         | A message with an `id`. It expects a reply carrying the same `id`.                                                                                           |
| **Notification**    | A message without an `id`. It expects no reply.                                                                                                              |
| **Handshake**       | The opening exchange (`initialize`) where both sides say who they are.                                                                                       |
| **Tool call**       | The model's request to run a tool: a name plus arguments.                                                                                                    |
| **Confirmation**    | The prompt asking the user to approve a tool call before it runs.                                                                                            |
| **Registry**        | The list of all tools the engine can use (`ToolRegistry`). Built-in and MCP tools live in the same one.                                                      |
| **Child process**   | A program started by another program. Sensai starts each MCP server this way, and stops it on exit.                                                          |
| **stdin / stdout**  | A program's input and output streams. Sensai writes to the server's stdin and reads its stdout.                                                              |
| **Function schema** | The format Ollama expects for a tool list: `{"type": "function", "function": {"name", "description", "parameters"}}`. Same idea as the tool schema, wrapped. |

## 5. Declaring a server: the config

Servers are declared in `sensai.toml`, one table per server:

```toml
[mcp.servers.github]
command = "docker"
args = ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server", "stdio", "--read-only", "--toolsets", "issues"]
timeout = 60

[mcp.servers.ctx7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]

[mcp.servers.ctx7.env]
CONTEXT7_API_KEY = "your-key"
```

| Key       | Required | Default | Meaning                                                                                                                               |
| --------- | -------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `command` | yes      |         | The program to start. Must not be blank.                                                                                              |
| `args`    | no       | `[]`    | Its arguments, as a list.                                                                                                             |
| `env`     | no       | `{}`    | Extra environment variables for the server. Added on top of Sensai's own environment.                                                 |
| `timeout` | no       | `30.0`  | Seconds Sensai waits for **each** request before giving up. Must be positive. Raise it for servers that start slowly (`npx`, Docker). |

The table name (`github`, `ctx7`) must match `[A-Za-z0-9_-]+`. It becomes the **prefix of every tool name**: the server's `list_issues` is shown to the model as `github__list_issues`. The prefix stops two servers from clashing on a common name like `search`. It also keeps names safe to use as function names.

**Nothing connects at this point.** This is only a description of how to start each server.

Code: `McpServerConfig` and `McpConfig` in `src/sensai/core/config.py`. Pydantic validates the values, and a bad entry becomes a `ConfigError` with a clear message.

**One trap.** `save_config` does not edit your file. It regenerates the whole `sensai.toml` from the in-memory config. So it must write the `[mcp.*]` tables back, or a `/model` command would silently delete your servers. It does, and tests check that they round-trip. Two consequences: **comments in `sensai.toml` are lost** on the next save, and **any new config section must also be added to `save_config`**.

**Secrets.** The `env` table stores keys in plain text. `sensai.toml` is git-ignored, but never paste it into an issue or a PR. A safer alternative is to leave a variable out of the file and export it in your shell: Sensai passes its own environment to the server, so `CONTEXT7_API_KEY=… sensai chat` works. Docker's `-e NAME` (without a value) copies the variable from that environment, which is how the GitHub example works.

## 6. Connecting: what happens at startup

Everything happens once, in `build_session` (`src/sensai/core/bootstrap.py`), after RAG indexing and before the engine is created.

```
build_session
  └─ _start_mcp_servers(config.mcp)
       └─ for every server, in parallel (asyncio.gather):
            _start_mcp_server(name, server)
              1. McpClient(command, args, env, timeout)
              2. client.start()        → launch the process + handshake
              3. client.list_tools()   → ask what tools exist
              4. McpTool(...) per tool → wrap each for the engine
```

### Step 2: `client.start()`

1. **Launch the child process** with `asyncio.create_subprocess_exec`. Sensai now holds the server's stdin (to write) and stdout (to read).
   - stderr goes to `DEVNULL`. Servers write logs there, and if nobody reads that pipe it eventually fills up and the server blocks.
   - The read buffer is raised to 16 MiB (`MAX_LINE_BYTES`) because one message is one line and tool results can be large. Python's default of 64 KiB would fail on a big result.
2. **Handshake.** Two messages:
   - `initialize` (a request): "I speak protocol version `2025-06-18`, my name is sensai." The server answers with its own version and capabilities.
   - `notifications/initialized` (a notification, no reply): "Handshake done, you can start."

### Step 3: `client.list_tools()`

Sends `tools/list`. The server answers with its menu. Entries without a string `name` are dropped, since they could not be called anyway.

### Step 4: `McpTool`

Each remote tool is wrapped in an `McpTool` (`src/sensai/tools/mcp.py`). It is the adapter that makes a remote tool look like any local one:

| Attribute               | Value                                                               |
| ----------------------- | ------------------------------------------------------------------- |
| `name`                  | `<server>__<remote name>`, e.g. `github__list_issues`               |
| `description`           | the server's description (or `"<name> (MCP: <server>)"` if missing) |
| `parameters_schema`     | the server's `inputSchema` (or an empty object schema if missing)   |
| `requires_confirmation` | always `True` (it subclasses `SensitiveTool`)                       |
| `execute(**arguments)`  | forwards the call to the server (section 9)                         |

### Registering the tools

Back in `build_session`, the MCP tools are passed to the registry through `build_default_registry(allowed_root, extra_tools=mcp_tools)`. The factory is wrapped in `functools.partial` so the MCP tools are remembered: when `/config set tools.fs_allowed_root …` rebuilds the registry, the MCP tools come back with it. Built-in tools are registered after the extra ones, so a built-in always wins a name clash.

### If a server fails

`McpError` (cannot start, bad handshake, crash, timeout) is caught per server. The process is closed, and a warning string `MCP server 'x' skipped: <reason>` is recorded in `CommandContext.startup_warnings`. The dispatcher prints these in yellow before the interface starts. The other servers and all the built-in tools keep working. The session never refuses to start because of an MCP server.

> In the TUI the warnings are printed before Textual takes over the screen, so you usually will not see them. The CLI shows them. A skipped server is visible there by the absence of its tools.

## 7. The protocol: JSON-RPC over stdio

Messages are **JSON-RPC 2.0**, **one JSON object per line**, written to the server's stdin and read from its stdout. A message never contains a raw newline.

Request (has an `id`, expects a reply with the same `id`):

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "list_issues",
    "arguments": { "owner": "Nexlein", "repo": "Sensai", "state": "OPEN" }
  }
}
```

Success reply:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": { "content": [{ "type": "text", "text": "{\"issues\":[...]}" }] }
}
```

Error reply:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "error": { "code": -32602, "message": "unknown tool" }
}
```

Notification (no `id`, no reply):

```json
{ "jsonrpc": "2.0", "method": "notifications/initialized" }
```

### The three calls Sensai uses

| Method       | Sent by        | Purpose                              | Result                                               |
| ------------ | -------------- | ------------------------------------ | ---------------------------------------------------- |
| `initialize` | `start()`      | Handshake: versions and capabilities | the server's protocol version, capabilities, name    |
| `tools/list` | `list_tools()` | Ask what tools exist                 | `{"tools": [{name, description, inputSchema}, ...]}` |
| `tools/call` | `call_tool()`  | Run one tool                         | `{"content": [...blocks...], "isError": bool}`       |

### A full conversation, as bytes

```
Sensai → server   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"sensai","version":"0.1.0"}}}
server → Sensai   {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{...}}}
Sensai → server   {"jsonrpc":"2.0","method":"notifications/initialized"}
Sensai → server   {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
server → Sensai   {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"add","description":"Add two numbers.","inputSchema":{...}}]}}
        ... later, when the model asks for a tool ...
Sensai → server   {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add","arguments":{"a":2,"b":3}}}
server → Sensai   {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"5"}]}}
```

### How the client reads replies (`_request` and `_read_response`)

- Each request gets the next integer `id` (1, 2, 3 …).
- A **lock** allows only one request in flight at a time. Replies are matched by reading in order, and the engine runs tools one after another anyway.
- `_read_response` reads lines until it finds the one whose `id` matches. It **skips**:
  - lines that are not valid JSON (stray output on stdout),
  - server-initiated notifications (logs, progress), which have a `method` and no matching `id`.
- An `error` object in the reply becomes `McpError("MCP error: <message>")`.
- An empty read means the server closed stdout, i.e. it died: `McpError("MCP server exited unexpectedly")`.
- The wait is wrapped in `asyncio.wait_for(…, timeout)`, so a hung server becomes `McpError("'tools/call' timed out after 30.0s")` instead of freezing Sensai.

### Result content

A `tools/call` result is a list of **content blocks**. `_content_to_text` flattens it into one string for the model:

- `{"type": "text", "text": "..."}` → the text is kept.
- anything else (image, audio, resource) → replaced by a marker like `[image content omitted]`, because the model here is text-only.
- `isError: true` → the string becomes `Error: <text>`, so the model learns the tool failed rather than being handed an error as if it were data.

## 8. Telling the model about the tools

The model can only use tools it has been told about. On every message, the engine asks the registry for the schema list (`ToolRegistry.get_tools_schema()`) and passes it to the provider (Ollama) along with the conversation. For one MCP tool it looks like:

```json
{
  "type": "function",
  "function": {
    "name": "github__list_issues",
    "description": "List issues in a GitHub repository ...",
    "parameters": { "type": "object", "properties": { "owner": {...}, "repo": {...} }, "required": ["owner", "repo"] }
  }
}
```

MCP tools and built-in tools are indistinguishable at this point. The `parameters` field is the server's own `inputSchema`, passed through unchanged.

The **description is everything the model knows about a tool.** A vague one produces bad calls. Because Sensai just forwards what the server wrote, the quality of MCP tool use depends partly on the server author and heavily on the model (section 15).

## 9. Handling a question and its response

This is the heart of it: the loop in `ChatEngine.send` (`src/sensai/core/engine.py`).

```
you ─ question ─▶ engine
                    │  1. build prompt (+ tool list)
                    ▼
                  LLM ── plain text? ──────────────▶ answer shown, done
                    │
                    └─ tool call (name + arguments)
                    ▼
                  2. look up the tool in the registry
                  3. needs confirmation? ── ask you ── declined? ─▶ tell the model "declined"
                    │ approved
                    ▼
                  4. McpTool.execute(**arguments)
                    ▼
                  5. McpClient.call_tool → tools/call → server → real service (GitHub…)
                    ▼
                  6. result text ─ guardrails ─▶ added to the conversation as a "tool" message
                    ▼
                  back to step 1 (the model now sees the result)
```

Up to `MAX_TOOL_ROUNDS = 5` rounds happen per question, so a model cannot loop forever.

Step by step with a real example: _"What are the open issues in Nexlein/Sensai?"_

1. The engine sends your message and the tool list to Ollama.
2. The model replies with a tool call: `github__list_issues`, `{"owner": "Nexlein", "repo": "Sensai", "state": "OPEN"}`.
3. `_run_tool` finds `github__list_issues` in the registry. If the name does not exist it returns `Error: Tool '…' not found in registry.` to the model.
4. The tool has `requires_confirmation = True`, so the UI asks you (section 10).
5. You approve. The engine calls `tool.execute(**arguments)`.
6. `McpTool.execute` removes the `github__` prefix (the server only knows `list_issues`) and calls `McpClient.call_tool("list_issues", arguments)`.
7. The client sends `tools/call` to the GitHub server's stdin. The server calls the GitHub API and writes the issues to stdout.
8. `_read_response` picks up the reply with the matching `id`, and `_content_to_text` turns it into a string.
9. The engine runs the string through the guardrails (`_store_tool_result`): personal data can be masked, or the whole result withheld. It is then stored as a `tool` message.
10. The loop runs again. The model now sees the issue list and writes the answer you read.

Two details worth knowing:

- **`execute` never raises.** `McpTool.execute` catches `McpError` and returns `Error: …` as a string. A broken server produces a sentence the model can explain, not a crash. The engine also wraps tool execution in its own catch-all.
- **Tool output is treated as data.** The system prompt tells the model to treat tool outputs as data, not instructions. This matters for MCP because the content comes from outside (issue bodies written by strangers, web docs). It is not a complete defence against prompt injection, only a first layer, alongside the guardrails.

## 10. Confirmation: why every call asks first

MCP servers are programs you did not write and may not have audited. A server can do anything its credentials allow. So every MCP tool is a `SensitiveTool` (`requires_confirmation = True`), and the engine's existing confirmation gate handles the rest:

- Before `execute`, the engine builds a `ToolCall` and asks the UI (CLI or TUI) for approval. The prompt shows the tool name and arguments.
- **Declined:** `execute` is never called. The server is never contacted. The model is told the call was declined and can explain that to you.
- **The confirmation callback itself fails:** the call is treated as _not_ authorized. A broken UI never approves anything.
- There is no "always allow" option. Every call asks.

You can also reduce risk at the server level. The GitHub example runs with `--read-only` and `--toolsets issues`, so even an approved call cannot write anything, and only 6 tools exist instead of dozens.

## 11. When things go wrong

| Situation                                | What happens                                                                                               |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `command` does not exist                 | `McpError("cannot start …")`. Server skipped, warning shown at startup.                                    |
| Server exits during the handshake        | `McpError("MCP server exited unexpectedly")`. Server skipped, warning shown.                               |
| Handshake or `tools/list` takes too long | `McpError("… timed out after Ns")`. Server skipped. Raise `timeout` for slow starters (npx, Docker).       |
| Server crashes in the middle of a call   | The tool returns `Error: MCP server exited unexpectedly`. The chat continues.                              |
| Server hangs on a call                   | After `timeout` seconds the tool returns `Error: … timed out …`. The chat continues.                       |
| Server returns a JSON-RPC `error`        | The tool returns `Error: MCP error: <message>`.                                                            |
| Server reports `isError: true`           | The tool returns `Error: <its message>`.                                                                   |
| Server returns images or other blocks    | They become markers like `[image content omitted]`.                                                        |
| Call after the server was stopped        | `Error: MCP server is not running`.                                                                        |
| Model calls a tool that does not exist   | `Error: Tool 'x' not found in registry.` is returned to the model.                                         |
| Model passes bad arguments               | The server rejects them with an error, which comes back as above. The model can retry within the 5 rounds. |
| You decline the confirmation             | `Tool execution declined by the user.` The server is never called.                                         |
| Every configured server fails            | The session still starts, with the built-in tools only.                                                    |

## 12. Shutting down

A server is a running process, so it must be stopped. `CommandContext.aclose()` awaits one closer per server and is called from a `finally` block in `interfaces/dispatcher.py`, so it runs on a normal exit, on Ctrl-C and when the interface crashes.

`McpClient.close()`:

1. Closes the server's stdin. For a stdio server this is the polite "please stop", and well-behaved servers exit on their own.
2. Waits up to 2 seconds for the process to exit.
3. Kills it if it did not.

It is idempotent (safe to call twice). Without this, you would leave orphan processes behind, and for the Docker-based GitHub server, orphan containers.

In `build_session`, MCP startup is deliberately the **last step that can fail**. If it ran earlier and something after it raised (for example RAG indexing), the started servers would never be closed.

## 13. Testing

| What                                                         | Where                                 | Needs                                                |
| ------------------------------------------------------------ | ------------------------------------- | ---------------------------------------------------- |
| The client against a **self-built server**                   | `tests/tools/test_mcp.py`             | nothing                                              |
| The self-built server itself                                 | `tests/tools/mcp_test_server.py`      | nothing                                              |
| Config parsing, validation and `save_config` round trip      | `tests/core/test_config.py`           | nothing                                              |
| Startup, warnings, registry rebuilds, shutdown               | `tests/core/test_bootstrap.py`        | nothing                                              |
| Warnings printed and server closed, even when the UI crashes | `tests/interfaces/test_dispatcher.py` | nothing                                              |
| `extra_tools` in the registry                                | `tests/tools/test_tool_registry.py`   | nothing                                              |
| A **real third-party server** (official GitHub MCP server)   | `tests/tools/test_mcp_live.py`        | Docker, network, a GitHub token, `SENSAI_LIVE_MCP=1` |

The self-built server (`mcp_test_server.py`) is about 70 lines of plain Python that reads JSON from stdin and answers on stdout. It offers `add`, `boom` (reports a tool error) and `image` (returns a non-text block). It can be told to crash or hang in the middle of a call, and it emits a stray notification before its handshake reply so the tests check the client skips it. It is a good place to read what a server minimally looks like.

Run everything except the live test:

```bash
uv run pytest
```

Run the live test (read-only, issues toolset only, nothing can write to GitHub):

```bash
SENSAI_LIVE_MCP=1 GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) \
  uv run pytest tests/tools/test_mcp_live.py
```

## 14. Adding your own server

1. Find a server that runs as a local command (stdio). The usual forms are `npx -y <package>`, `uvx <package>` and `docker run -i --rm <image>`.
2. Add a table to `sensai.toml`:

   ```toml
   [mcp.servers.myserver]
   command = "npx"
   args = ["-y", "some-mcp-package"]
   timeout = 60
   ```

3. If it needs a key, put it in `[mcp.servers.myserver.env]`, or export it in your shell.
4. Start `sensai chat`. A yellow `MCP server 'myserver' skipped: …` line means it failed to start; the reason is in the message.
5. Ask the model something that needs the tool. Naming the tool or the order of calls in your prompt helps small models.
6. Approve the confirmation prompt.

To see what a server offers before wiring it in, list its tools through the client (a script can do it in a few lines):

```python
import asyncio
from sensai.tools.mcp import McpClient

async def main():
    client = McpClient("npx", ["-y", "@upstash/context7-mcp"], timeout=120)
    await client.start()
    for tool in await client.list_tools():
        print(tool["name"], list(tool.get("inputSchema", {}).get("properties", {})))
    await client.close()

asyncio.run(main())
```

Two servers tried so far:

| Server   | Command                                                                                                                   | Tools                                                                                              | Notes                                                                                                                   |
| -------- | ------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| GitHub   | `docker run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN ghcr.io/github/github-mcp-server stdio --read-only --toolsets issues` | `get_label`, `issue_read`, `list_issue_fields`, `list_issue_types`, `list_issues`, `search_issues` | Needs a token. `--read-only` and `--toolsets` keep it small and safe.                                                   |
| Context7 | `npx -y @upstash/context7-mcp`                                                                                            | `resolve-library-id` (`query`, `libraryName`), `query-docs` (`libraryId`, `query`, `language`)     | Needs two calls in order: resolve the library ID first, then query. An API key raises rate limits (`CONTEXT7_API_KEY`). |

## 15. Known limits

**What Sensai does not support**

- **stdio only.** Servers that are only reachable over HTTP or SSE cannot be used.
- **Tools only.** MCP also defines resources, prompts and sampling; they are ignored.
- **One request at a time per server.** Calls to the same server are serialized.
- **No reconnection.** If a server dies mid-session its tools return errors until you restart Sensai.
- **No tool-list refresh.** The tool list is read once at startup; servers that change their tools later are not noticed.
- **Non-text results are dropped**, replaced by a marker.

**What depends on the model, not on MCP**

Most problems seen in practice are the LLM, not the plumbing. With small local models:

- **Wrong language.** After a long English tool result, `qwen3.5:4b` answered in Chinese, despite the system prompt asking it to reply in the user's language.
- **Misreading data.** The same run invented priorities that were not in the issues.
- **Skipping steps.** `llama3.1:8b` called Context7's `query-docs` with a guessed library ID instead of calling `resolve-library-id` first.
- **Inventing tools and printing calls as text.** The same model produced `{"name": "ctx7__search", …}` as plain text. That tool does not exist, and a call printed as text is never executed.
- **Many tools hurt.** The more tools a server offers, the worse small models choose between them. Use `--toolsets` style options, or prefer small servers.

When MCP "does not work", check first that the confirmation prompt appeared and that the server's reply reached the model. If so, the protocol part worked and the problem is the model's choice or reading. A larger model, or a prompt that spells out the order of calls, is the first thing to try.

**Open follow-ups**

- Large tool results (such as full issue bodies) take much of the token budget. Truncating them before they reach the model would help every tool.
- The engine could detect a reply that is only a tool call written as text, and either run it or tell the model which tools exist.
- The TUI does not show startup warnings.

**Security notes**

- A server runs with your user's permissions, plus whatever tokens you give it. Only configure servers you trust, and prefer read-only modes.
- Tool results can contain text written by strangers (issue bodies, web pages). The model is told to treat them as data, and guardrails filter personal data, but a determined prompt injection is not fully prevented.
- What the model sends as arguments leaves your machine when the server is a hosted service (Context7, for example). The confirmation prompt shows the arguments before anything is sent.
- API keys in `sensai.toml` are in plain text. Do not share the file.

## 16. File map

| Concern                                            | File                                    |
| -------------------------------------------------- | --------------------------------------- |
| Config models, validation, saving                  | `src/sensai/core/config.py`             |
| Starting servers, skip-and-warn, registry factory  | `src/sensai/core/bootstrap.py`          |
| `startup_warnings`, `closers`, `aclose()`          | `src/sensai/core/commands.py`           |
| MCP client (process, handshake, requests)          | `src/sensai/tools/mcp.py` (`McpClient`) |
| Adapter that makes a remote tool look local        | `src/sensai/tools/mcp.py` (`McpTool`)   |
| `SensitiveTool` (confirmation required)            | `src/sensai/tools/base.py`              |
| Registry, `extra_tools`, schema list for the model | `src/sensai/tools/registry.py`          |
| Tool loop, confirmation, guardrails on results     | `src/sensai/core/engine.py`             |
| Printing warnings, closing servers on exit         | `src/sensai/interfaces/dispatcher.py`   |

## 17. FAQ

**Is the MCP server on the network?**
No. It is a child process of Sensai, and the two talk through pipes. The server may then call the network itself (the GitHub server calls the GitHub API), but that is its business.

**Does the model run the tool?**
No. It only emits a request. Sensai decides, asks you, runs it, and returns the result.

**Does the server see my conversation?**
No. It only receives the tool name and arguments for each call.

**Why `github__list_issues` and not `list_issues`?**
So several servers can offer tools with the same name. Sensai strips the prefix before calling the server.

**Why a hand-written client instead of the official `mcp` package?**
The project forbids LLM frameworks, and a stdio client for three methods is about 150 lines with no new dependency. It also keeps the whole protocol readable in one file. The trade-off is that only the stdio transport and the tool features are covered.

**Why does it ask for confirmation every time?**
Because the server is code the user did not vet. See section 10.

**A server shows up in my config but its tools are missing.**
It failed to start. Look for the yellow `MCP server '…' skipped` line printed before the chat starts (CLI), or run the listing script in section 14 to see the error.

**The model said it would use a tool but nothing happened.**
No confirmation prompt means no tool call was made. Small models sometimes describe a call, or print it as text, instead of making it. Try a larger model.

**I changed the model with `/model` and my servers vanished.**
They should not: `save_config` writes the `[mcp.*]` tables back. If you see that, it is a bug. Comments in the file are lost on save, which is expected.
