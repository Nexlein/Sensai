"""Memory tools."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from sensai.memory.manager import SqliteMemoryManager
from sensai.tools.memory import ForgetFactTool, RecallMemoryTool, RememberFactTool


@pytest.fixture
def memory_manager(tmp_path: Path) -> SqliteMemoryManager:
    return SqliteMemoryManager(tmp_path / "test_tools_memory.db")


def test_remember_fact_tool(memory_manager: SqliteMemoryManager) -> None:
    tool = RememberFactTool(memory_manager)
    assert tool.name == "remember_fact"
    assert tool.requires_confirmation is False

    res = asyncio.run(
        tool.execute(
            entity="user",
            key="preferred_editor",
            value="Helix",
            tags=["editor", "dev"],
        )
    )
    assert "Remembered: user.preferred_editor = Helix [editor, dev]" in res

    fact = memory_manager.get_fact("user", "preferred_editor")
    assert fact is not None
    assert fact.value == "Helix"

    # Error handling on invalid input
    err = asyncio.run(tool.execute(entity="", key="k", value="v"))
    assert "Error storing memory" in err


def test_recall_memory_tool(memory_manager: SqliteMemoryManager) -> None:
    tool = RecallMemoryTool(memory_manager)
    assert tool.name == "recall_memory"
    assert tool.requires_confirmation is False

    empty_res = asyncio.run(tool.execute())
    assert empty_res == "No matching memories found."

    memory_manager.store_fact("user", "lang", "Rust")
    memory_manager.store_fact("project", "name", "Sensai")

    # List all
    all_res = asyncio.run(tool.execute())
    assert "- project.name: Sensai" in all_res
    assert "- user.lang: Rust" in all_res

    # Search with query
    query_res = asyncio.run(tool.execute(query="rust"))
    assert "- user.lang: Rust" in query_res
    assert "Sensai" not in query_res

    # Entity filter
    entity_res = asyncio.run(tool.execute(entity="project"))
    assert "- project.name: Sensai" in entity_res
    assert "Rust" not in entity_res


def test_forget_fact_tool(memory_manager: SqliteMemoryManager) -> None:
    tool = ForgetFactTool(memory_manager)
    assert tool.name == "forget_fact"
    assert tool.requires_confirmation is True

    # Preview when not existing
    assert tool.preview("user", "token") is None

    # Add fact
    memory_manager.store_fact("user", "token", "abc123xyz")

    # Preview when existing (unified diff)
    preview = tool.preview("user", "token")
    assert preview is not None
    assert "--- memory/user.token" in preview
    assert "+++ /dev/null" in preview
    assert "-user.token = abc123xyz" in preview

    # Execute deletion
    res = asyncio.run(tool.execute(entity="user", key="token"))
    assert "Successfully deleted memory: user.token" in res
    assert memory_manager.get_fact("user", "token") is None

    # Execute deletion on already deleted
    res_again = asyncio.run(tool.execute(entity="user", key="token"))
    assert "No memory found for user.token" in res_again


@pytest.fixture
def broken_memory(
    memory_manager: SqliteMemoryManager, monkeypatch: pytest.MonkeyPatch
) -> SqliteMemoryManager:
    """A store whose database is unusable, as when the file is locked."""

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    for method in ("search_facts", "list_facts", "delete_fact", "get_fact"):
        monkeypatch.setattr(memory_manager, method, fail)
    return memory_manager


def test_recall_memory_combines_query_and_entity_filter(
    memory_manager: SqliteMemoryManager,
) -> None:
    memory_manager.store_fact("user", "lang", "Rust")
    memory_manager.store_fact("project", "lang", "Python")

    res = asyncio.run(
        RecallMemoryTool(memory_manager).execute(query="lang", entity="USER")
    )

    assert res == "- user.lang: Rust"


def test_recall_memory_reports_database_error(
    broken_memory: SqliteMemoryManager,
) -> None:
    res = asyncio.run(RecallMemoryTool(broken_memory).execute(query="x"))

    assert res == "Error recalling memory: database is locked"


def test_forget_fact_reports_database_error(
    broken_memory: SqliteMemoryManager,
) -> None:
    res = asyncio.run(ForgetFactTool(broken_memory).execute(entity="user", key="k"))

    assert res == "Error forgetting memory: database is locked"
