# Sensai User Stories

## Feature: [T4] File Access within Permissions (Filesystem Tools)

As a user, I want the agent restricted to a project subdirectory, so that it can't read or leak unrelated files on my machine.

Acceptance criteria:

- Path traversal outside the root (relative, absolute, symlink) is rejected.
- `AppConfig.tools.fs_allowed_root` defaults to `None`; fs tool is not registered when unset.

As a developer, I want the agent to list and read files in my project, so that it can answer questions grounded in my actual code.

Acceptance criteria:

- ReadFile/ListDir succeed for paths inside the allowed root.
- Nonexistent file returns a clean error string, no raw exception leak.

## Feature: [R1] Basic RAG

As a user, I want the agent to ingest my local project documentation, so I can ask questions about my codebase.

Acceptance criteria:

- Local Markdown and Text files are ingested and chunked.
- Chunks are stored in a local vector database.

As a user, I want the agent to retrieve relevant information based on my query, so its answers are grounded in my actual documentation.

Acceptance criteria:

- Retrieval finds semantically relevant chunks.
- The retrieved context is injected into the prompt before generation.

## Feature: Shared CLI/TUI Session Bootstrap

As a user, I want to select the CLI or TUI from the command line or my config file, so I can use my preferred interface with the same assistant settings.

Acceptance criteria:

- `interface` defaults to `cli` and accepts `cli`, `tui`, or `web`.
- `--ui` overrides `interface` from `sensai.toml`.
- Selecting `web` reports that the interface is not implemented yet.

As a user, I want my saved conversation and tools available in the TUI, so switching interfaces does not lose my session.

Acceptance criteria:

- CLI and TUI obtain their engine, session store, tools, and RAG from the same bootstrap.
- TUI replies are saved to the existing session store.

## Feature: [M2] Token Budgeting & Semantic Compression

As a user, I want long conversations to keep working, so the agent does not lose the thread or hit the model's context limit.

Acceptance criteria:

- Token usage is counted for every outgoing prompt against `budget.max_tokens`.
- At `budget.threshold`, the oldest turns are replaced by one summary message.
- The last `budget.keep_recent_turns` turns are kept verbatim, and a tool call is never separated from its result.
- If summarizing fails, the chat continues with the history unchanged.

As a user, I want to set the token budget in `sensai.toml`, so it matches the context window of the model I run.

Acceptance criteria:

- `[budget]` accepts `max_tokens`, `threshold` and `keep_recent_turns`, with defaults when omitted.
- Out-of-range values are rejected with a config error.
- The engine emits a budget event before and during streaming, so an interface can show live usage.
