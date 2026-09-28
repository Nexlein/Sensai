from sensai.domain.models import Conversation, ToolCall
from sensai.memory.session import SqliteMemoryStore


async def test_save_then_load_round_trips_conversation(tmp_path):
    store = SqliteMemoryStore(tmp_path / "sensai.db")
    conversation = Conversation()
    conversation.add_message(role="user", content="hello")
    conversation.add_message(
        role="assistant",
        content="hi",
        tool_calls=[ToolCall(name="search", arguments={"q": "hi"})],
    )

    await store.save(conversation)
    loaded = await store.load(conversation.id)

    assert loaded is not None
    assert loaded.id == conversation.id
    assert loaded.created_at == conversation.created_at
    assert loaded.updated_at == conversation.updated_at
    assert [m.content for m in loaded.messages] == ["hello", "hi"]
    assert [m.role for m in loaded.messages] == ["user", "assistant"]
    assert loaded.messages[0].tool_calls is None
    assert loaded.messages[1].tool_calls[0].name == "search"
    assert loaded.messages[1].tool_calls[0].arguments == {"q": "hi"}


async def test_load_unknown_id_returns_none(tmp_path):
    store = SqliteMemoryStore(tmp_path / "sensai.db")
    assert await store.load("does-not-exist") is None


async def test_save_existing_conversation_updates_not_duplicates(tmp_path):
    store = SqliteMemoryStore(tmp_path / "sensai.db")
    conversation = Conversation()
    conversation.add_message(role="user", content="first")
    await store.save(conversation)

    conversation.add_message(role="assistant", content="second")
    await store.save(conversation)

    row_count = store._conn.execute(
        "SELECT COUNT(*) FROM conversations WHERE id = ?", (conversation.id,)
    ).fetchone()[0]
    assert row_count == 1

    loaded = await store.load(conversation.id)
    assert [m.content for m in loaded.messages] == ["first", "second"]
