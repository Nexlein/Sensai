from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent


def test_text_chunk_event_type_and_content():
    event = TextChunkEvent(content="hello")
    assert event.type == "text_chunk"
    assert event.content == "hello"
    assert event.timestamp is not None


def test_tool_call_event_type_and_fields():
    event = ToolCallEvent(tool_name="search", arguments={"q": "x"})
    assert event.type == "tool_call"
    assert event.tool_name == "search"
    assert event.arguments == {"q": "x"}


def test_events_are_event_instances():
    assert isinstance(TextChunkEvent(content="hi"), Event)
    assert isinstance(ToolCallEvent(tool_name="x", arguments={}), Event)
