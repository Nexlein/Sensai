import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

DEFAULT_DATA_DIR = Path(".sensai")
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "sensai.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

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

CREATE INDEX IF NOT EXISTS idx_facts_entity_name ON facts(entity_name);
CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
"""


def _ensure_gitignore(data_dir: Path) -> None:
    gitignore = data_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with the schema initialized (idempotent)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(db_path.parent)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        conn.commit()
    except BaseException:
        conn.close()
        raise
    return conn


@contextmanager
def transaction(db_path: Path | str = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a connection that commits on success, rolls back on error, then closes."""
    with closing(connect(db_path)) as conn, conn:
        yield conn
