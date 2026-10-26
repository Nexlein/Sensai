import pathlib
import sqlite3
from contextlib import closing

import pytest

from sensai.memory.db import DEFAULT_DATA_DIR, DEFAULT_DB_PATH, connect, transaction


def test_connect_creates_schema(tmp_path):
    with closing(connect(tmp_path / "sensai.db")) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"conversations", "messages"} <= tables


def test_connect_is_idempotent_on_repeat_init(tmp_path):
    db_path = tmp_path / "sensai.db"
    connect(db_path).close()
    with closing(connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
            ("c1", "t", "t"),
        )
        conn.commit()
    with closing(connect(db_path)) as conn2:
        row = conn2.execute("SELECT id FROM conversations WHERE id = 'c1'").fetchone()
    assert row == ("c1",)


def test_default_db_path_is_dot_sensai_folder():
    assert DEFAULT_DB_PATH == DEFAULT_DATA_DIR / "sensai.db"
    assert DEFAULT_DATA_DIR == pathlib.Path(".sensai")


def test_connect_creates_data_dir_and_gitignore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect(DEFAULT_DB_PATH).close()

    gitignore = tmp_path / ".sensai" / ".gitignore"
    assert gitignore.exists()
    assert gitignore.read_text() == "*\n"


def test_connect_does_not_overwrite_existing_gitignore(tmp_path):
    data_dir = tmp_path / "custom"
    data_dir.mkdir()
    (data_dir / ".gitignore").write_text("custom-content\n")

    connect(data_dir / "sensai.db").close()

    assert (data_dir / ".gitignore").read_text() == "custom-content\n"


def test_connect_closes_the_connection_when_schema_init_fails(
    tmp_path, opened_connections
):
    db_path = tmp_path / "sensai.db"
    db_path.write_bytes(b"not a database" * 100)

    with pytest.raises(sqlite3.DatabaseError):
        connect(db_path)

    (conn,) = opened_connections
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_transaction_commits_then_closes(tmp_path):
    db_path = tmp_path / "sensai.db"

    with transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
            ("c1", "t", "t"),
        )

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")
    with closing(connect(db_path)) as check:
        assert check.execute("SELECT id FROM conversations").fetchall() == [("c1",)]


def test_transaction_rolls_back_on_error_then_closes(tmp_path):
    db_path = tmp_path / "sensai.db"

    with pytest.raises(RuntimeError, match="boom"), transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
            ("c1", "t", "t"),
        )
        raise RuntimeError("boom")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")
    with closing(connect(db_path)) as check:
        assert check.execute("SELECT COUNT(*) FROM conversations").fetchone() == (0,)
