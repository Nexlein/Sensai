from sensai.domain.events import TextChunkEvent, ThoughtEvent, ToolCallEvent
from sensai.domain.models import Message
from sensai.providers.mock import MockLLMProvider, MockToolCallingLLMProvider


async def test_mock_provider_streams_words_as_chunks():
    provider = MockLLMProvider(default_response="hi there", simulated_delay=0)
    events = [e async for e in provider.chat_stream(messages=[])]
    assert [e.content for e in events] == ["hi", " there"]
    assert all(isinstance(e, TextChunkEvent) for e in events)


async def test_mock_provider_ignores_messages_and_tools():
    provider = MockLLMProvider(default_response="ok", simulated_delay=0)
    msg = Message(role="user", content="hello")
    events = [e async for e in provider.chat_stream(messages=[msg], tools=[{"a": 1}])]
    assert [e.content for e in events] == ["ok"]


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
    assert [e.content for e in events] == ["ok"]


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
