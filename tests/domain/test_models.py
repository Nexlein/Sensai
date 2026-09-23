from sensai.domain.models import Conversation, Message, Persona, ToolCall


def test_message_defaults_id_and_timestamp():
    msg = Message(role="user", content="hi")
    assert msg.id
    assert msg.timestamp is not None
    assert msg.tool_calls is None


def test_message_with_tool_calls():
    tc = ToolCall(name="search", arguments={"q": "x"})
    msg = Message(role="assistant", content="", tool_calls=[tc])
    assert msg.tool_calls == [tc]
    assert msg.tool_calls[0].name == "search"


def test_tool_call_defaults_id():
    tc = ToolCall(name="search", arguments={"q": "x"})
    assert tc.id
    assert tc.arguments == {"q": "x"}


def test_conversation_starts_empty():
    convo = Conversation()
    assert convo.messages == []
    assert convo.id
    assert convo.created_at is not None


def test_conversation_add_message_appends_and_returns():
    convo = Conversation()
    msg = convo.add_message(role="user", content="hello")
    assert convo.messages == [msg]
    assert msg.role == "user"
    assert msg.content == "hello"


def test_conversation_add_message_updates_updated_at():
    convo = Conversation()
    original_updated_at = convo.updated_at
    convo.add_message(role="user", content="hello")
    assert convo.updated_at >= original_updated_at


def test_conversation_add_message_with_tool_calls():
    convo = Conversation()
    tc = ToolCall(name="search", arguments={})
    msg = convo.add_message(role="assistant", content="", tool_calls=[tc])
    assert msg.tool_calls == [tc]


def test_persona_fields():
    persona = Persona(
        id="p1",
        name="Assistant",
        description="A helpful assistant",
        system_instruction="Be helpful.",
    )
    assert persona.id == "p1"
    assert persona.name == "Assistant"
