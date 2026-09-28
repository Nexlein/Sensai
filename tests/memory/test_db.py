import pathlib

from sensai.memory.db import DEFAULT_DATA_DIR, DEFAULT_DB_PATH, connect


def test_connect_creates_schema(tmp_path):
    conn = connect(tmp_path / "sensai.db")
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"conversations", "messages"} <= tables


def test_connect_is_idempotent_on_repeat_init(tmp_path):
    db_path = tmp_path / "sensai.db"
    connect(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO conversations (id, created_at, updated_at) VALUES (?, ?, ?)",
        ("c1", "t", "t"),
    )
    conn.commit()
    conn2 = connect(db_path)
    row = conn2.execute("SELECT id FROM conversations WHERE id = 'c1'").fetchone()
    assert row == ("c1",)


def test_default_db_path_is_dot_sensai_folder():
    assert DEFAULT_DB_PATH == DEFAULT_DATA_DIR / "sensai.db"
    assert DEFAULT_DATA_DIR == pathlib.Path(".sensai")


def test_connect_creates_data_dir_and_gitignore(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect(DEFAULT_DB_PATH)

    gitignore = tmp_path / ".sensai" / ".gitignore"
    assert gitignore.exists()
    assert gitignore.read_text() == "*\n"


def test_connect_does_not_overwrite_existing_gitignore(tmp_path):
    data_dir = tmp_path / "custom"
    data_dir.mkdir()
    (data_dir / ".gitignore").write_text("custom-content\n")

    connect(data_dir / "sensai.db")

    assert (data_dir / ".gitignore").read_text() == "custom-content\n"
