# External Structured Memory (M3)

This document describes the design, implementation, and architectural justification for Feature **[M3] External Structured Memory** in Sensai.

---

## 1. Architectural Choice: Why M3 Instead of M4

Ticket #40 and `SUBJECT.md` encourage choosing fewer, well-integrated features with depth rather than implementing multiple features shallowly. The team evaluated **M3 (External Structured Memory)** against **M4 (Living Artifact Document)** and selected **M3** for the following architectural and practical reasons:

### No Overlap with Existing Tools

Sensai already provides the `write_file` tool ([tools/fs.py](../../src/sensai/tools/fs.py)) equipped with diff previews and human-in-the-loop confirmation. M4 (editing living document sections) partially overlaps with filesystem editing. In contrast, Sensai previously lacked any mechanism for remembering facts, conventions, and user preferences across distinct sessions. M3 provides an entirely unserved capability.

### Completing the Memory Architecture Trilogy

Sensai's memory model consists of three distinct layers:

1. **[M1] Session Persistence**: Raw turn-by-turn chat history persisted to SQLite (`conversations` and `messages` tables).
2. **[M2] Working Memory Token Budgeting**: Sliding window semantic compression condensing old turns when approaching context caps.
3. **[M3] Long-term Structured Memory**: Persistent knowledge (entities, facts, preferences, conventions) stored in relational tables and recalled across sessions.

M3 completes this layered memory hierarchy, allowing the assistant to retain durable knowledge independently of message history.

### Demonstrable Keynote Impact

For live demonstrations and evaluation:

- In **Session A**, the user mentions preferences (e.g., `"My name is Alice and I develop in Rust with strict clippy rules."`).
- In **Session B** (a brand-new conversation or after restarting Sensai), the user asks `"Write a Fibonacci function."`
- Sensai immediately personalizes the response to Alice in Rust with strict clippy annotations because the structured memory was automatically recalled into the context prompt.

---

## 2. Architecture & Design

### Database Schema (`sensai.db`)

Stored in SQLite via idempotent migrations in [sensai/memory/db.py](../../src/sensai/memory/db.py):

```sql
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'generic',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    entity_name TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_name, key)
);
```

Key guarantees:

- **Idempotency**: Upserts use `INSERT ... ON CONFLICT(entity_name, key) DO UPDATE`, preventing duplicate keys and ensuring clean updates.
- **Relational Integrity**: `ON DELETE CASCADE` ensures deleting an entity removes all associated facts without leaving orphaned rows.

### Domain Models & Protocol Seam

- **Models** ([domain/models.py](../../src/sensai/domain/models.py)): `Entity` and `Fact` Pydantic models.
- **Protocol** ([domain/protocols.py](../../src/sensai/domain/protocols.py)): `StructuredMemory` protocol decouples the engine and tools from the SQLite implementation.

### Agent Tools ([tools/memory.py](../../src/sensai/tools/memory.py))

1. `remember_fact`: Autonomous tool (`requires_confirmation = False`) storing or updating entity facts.
2. `recall_memory`: Autonomous tool searching facts across entity names, keys, and values.
3. `forget_fact`: Sensitive tool (`requires_confirmation = True`) requiring user confirmation and displaying a preview before removing a fact.

### Prompt Injection Lifecycle

When `memory.auto_inject = true`, `ChatEngine._prompt` invokes `memory.format_context()` and passes the formatted facts into `build_prompt`. A dedicated system block is inserted into the prompt before conversational messages:

```text
The following structured facts are remembered from previous interactions. Use them to personalize your answers and respect stated preferences:

- user.preferred_language: Rust
- user.linter: clippy
```

---

## 3. User Commands (`/memory`)

Users inspect and control long-term memory via the `/memory` command:

- `/memory` or `/memory list [entity]`: View all stored memories or filter by entity.
- `/memory get <entity> <key>`: View a specific fact.
- `/memory set <entity> <key> <value>`: Manually create or update a fact.
- `/memory delete <entity> <key>`: Delete a fact.
- `/memory search <query>`: Search memories by word (accents, case and `_` ignored; best matches first).
- `/memory clear`: Clear all memories.

---

## 4. Configuration (`sensai.toml`)

Configured via the `[memory]` table:

```toml
[memory]
enabled = true        # Toggle structured memory and tools
auto_inject = true    # Toggle automatic prompt injection
```
