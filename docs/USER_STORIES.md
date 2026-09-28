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
