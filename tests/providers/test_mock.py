"""Mock providers."""

from sensai.domain.events import Event, TextChunkEvent, ThoughtEvent, ToolCallEvent
from sensai.domain.models import Message
from sensai.providers.mock import MockLLMProvider, MockToolCallingLLMProvider


def _texts(events: list[Event]) -> list[str]:
    return [e.content for e in events if isinstance(e, TextChunkEvent)]


async def test_mock_provider_streams_words_as_chunks():
    provider = MockLLMProvider(default_response="hi there", simulated_delay=0)
    events = [e async for e in provider.chat_stream(messages=[])]
    assert all(isinstance(e, TextChunkEvent) for e in events)
    assert _texts(events) == ["hi", " there"]


async def test_mock_provider_ignores_messages_and_tools():
    provider = MockLLMProvider(default_response="ok", simulated_delay=0)
    msg = Message(role="user", content="hello")
    events = [e async for e in provider.chat_stream(messages=[msg], tools=[{"a": 1}])]
    assert _texts(events) == ["ok"]


async def test_mock_provider_yields_scripted_thought_first():
    provider = MockLLMProvider(
        default_response="ok", simulated_delay=0, thought="think first"
    )
    events = [e async for e in provider.chat_stream(messages=[])]
    assert isinstance(events[0], ThoughtEvent)
    assert events[0].content == "think first"
    assert isinstance(events[1], TextChunkEvent)


async def test_mock_provider_accepts_think_argument():
    provider = MockLLMProvider(default_response="ok", simulated_delay=0)
    events = [e async for e in provider.chat_stream(messages=[], think="high")]
    assert _texts(events) == ["ok"]


async def test_mock_tool_calling_provider_yields_tool_call():
    provider = MockToolCallingLLMProvider(
        tool_name="search", tool_args={"query": "sensai"}, simulated_delay=0
    )
    events = [e async for e in provider.chat_stream(messages=[])]
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ToolCallEvent)
    assert event.tool_name == "search"
    assert event.arguments == {"query": "sensai"}


async def test_scripted_provider_plays_one_round_per_call():
    from sensai.providers.mock import ScriptedLLMProvider

    call = ToolCallEvent(tool_name="list_dir", arguments={"path": "."})
    provider = ScriptedLLMProvider(call, "done", [TextChunkEvent(content="a")])

    rounds = []
    for _ in range(3):
        rounds.append([e async for e in provider.chat_stream(messages=[])])

    assert rounds[0] == [call]
    assert [[e.content for e in r] for r in rounds[1:]] == [["done"], ["a"]]


async def test_scripted_provider_records_what_each_call_received():
    from sensai.providers.mock import ScriptedLLMProvider

    provider = ScriptedLLMProvider("ok")
    message = Message(role="user", content="hello")
    tools = [{"type": "function"}]

    [e async for e in provider.chat_stream(messages=[message], tools=tools)]
    message.content = "changed later"

    assert provider.calls[0].messages[0].content == "hello"
    assert provider.calls[0].tools == tools


async def test_scripted_provider_raises_once_the_script_is_exhausted():
    import pytest

    from sensai.providers.mock import ScriptedLLMProvider

    provider = ScriptedLLMProvider()

    with pytest.raises(RuntimeError, match="no scripted round left"):
        [e async for e in provider.chat_stream(messages=[])]
    assert len(provider.calls) == 1
