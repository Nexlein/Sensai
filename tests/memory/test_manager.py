from pathlib import Path

import pytest

from sensai.memory.manager import SqliteMemoryManager


@pytest.fixture
def memory_manager(tmp_path: Path) -> SqliteMemoryManager:
    db_file = tmp_path / "test_memory.db"
    return SqliteMemoryManager(db_file)


def test_store_and_get_fact(memory_manager: SqliteMemoryManager) -> None:
    fact = memory_manager.store_fact(
        entity="user",
        key="preferred_language",
        value="Python",
        confidence=0.9,
        tags=["preference", "dev"],
    )
    assert fact.entity_name == "user"
    assert fact.key == "preferred_language"
    assert fact.value == "Python"
    assert fact.confidence == 0.9
    assert fact.tags == ["preference", "dev"]

    retrieved = memory_manager.get_fact("user", "preferred_language")
    assert retrieved is not None
    assert retrieved.id == fact.id
    assert retrieved.value == "Python"
    assert retrieved.tags == ["preference", "dev"]


def test_get_nonexistent_fact(memory_manager: SqliteMemoryManager) -> None:
    assert memory_manager.get_fact("user", "nonexistent") is None


def test_store_fact_upsert(memory_manager: SqliteMemoryManager) -> None:
    first = memory_manager.store_fact("user", "editor", "vim")
    assert first.value == "vim"

    second = memory_manager.store_fact(
        "user", "editor", "neovim", tags=["editor", "tools"]
    )
    assert second.value == "neovim"
    assert second.tags == ["editor", "tools"]

    loaded = memory_manager.get_fact("user", "editor")
    assert loaded is not None
    assert loaded.value == "neovim"
    assert loaded.tags == ["editor", "tools"]


def test_store_blank_validation(memory_manager: SqliteMemoryManager) -> None:
    with pytest.raises(ValueError, match="entity name"):
        memory_manager.store_fact("", "key", "val")
    with pytest.raises(ValueError, match="fact key"):
        memory_manager.store_fact("user", "  ", "val")
    with pytest.raises(ValueError, match="fact value"):
        memory_manager.store_fact("user", "key", "")


def test_list_facts_filtering(memory_manager: SqliteMemoryManager) -> None:
    memory_manager.store_fact("user", "name", "Alice", tags=["profile"])
    memory_manager.store_fact("user", "language", "Python", tags=["preference", "dev"])
    memory_manager.store_fact("project", "framework", "FastAPI", tags=["dev"])

    all_facts = memory_manager.list_facts()
    assert len(all_facts) == 3

    user_facts = memory_manager.list_facts(entity="user")
    assert len(user_facts) == 2
    assert {f.key for f in user_facts} == {"name", "language"}

    dev_facts = memory_manager.list_facts(tag="dev")
    assert len(dev_facts) == 2
    assert {f.key for f in dev_facts} == {"language", "framework"}


def test_search_facts(memory_manager: SqliteMemoryManager) -> None:
    memory_manager.store_fact("user", "fav_db", "PostgreSQL")
    memory_manager.store_fact("infra", "host", "aws-eu-west")
    memory_manager.store_fact("project", "name", "Sensai")

    # Empty search
    assert memory_manager.search_facts("") == []
    assert memory_manager.search_facts("   ") == []

    # Search matches key
    res_key = memory_manager.search_facts("db")
    assert len(res_key) == 1
    assert res_key[0].key == "fav_db"

    # Search matches value
    res_val = memory_manager.search_facts("postgres")
    assert len(res_val) == 1
    assert res_val[0].value == "PostgreSQL"

    # Search matches entity name
    res_entity = memory_manager.search_facts("infra")
    assert len(res_entity) == 1
    assert res_entity[0].entity_name == "infra"


def test_delete_fact(memory_manager: SqliteMemoryManager) -> None:
    memory_manager.store_fact("user", "theme", "dark")
    assert memory_manager.delete_fact("user", "theme") is True
    assert memory_manager.get_fact("user", "theme") is None
    assert memory_manager.delete_fact("user", "theme") is False


def test_delete_entity_cascades(memory_manager: SqliteMemoryManager) -> None:
    memory_manager.store_fact("temp_entity", "key1", "val1")
    memory_manager.store_fact("temp_entity", "key2", "val2")
    assert len(memory_manager.list_facts(entity="temp_entity")) == 2

    assert memory_manager.delete_entity("temp_entity") is True
    assert len(memory_manager.list_facts(entity="temp_entity")) == 0
    assert memory_manager.delete_entity("temp_entity") is False


def test_clear(memory_manager: SqliteMemoryManager) -> None:
    memory_manager.store_fact("e1", "k1", "v1")
    memory_manager.store_fact("e2", "k2", "v2")
    memory_manager.clear()
    assert memory_manager.list_facts() == []


def test_format_context(memory_manager: SqliteMemoryManager) -> None:
    assert memory_manager.format_context() == ""

    memory_manager.store_fact("user", "lang", "Python")
    memory_manager.store_fact("user", "linter", "ruff")
    memory_manager.store_fact("project", "type", "CLI")

    context = memory_manager.format_context()
    lines = context.splitlines()
    assert len(lines) == 3
    assert "- project.type: CLI" in lines
    assert "- user.lang: Python" in lines
    assert "- user.linter: ruff" in lines

    # Limit max facts
    capped = memory_manager.format_context(max_facts=2)
    assert len(capped.splitlines()) == 2
