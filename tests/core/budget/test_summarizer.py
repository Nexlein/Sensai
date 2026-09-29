from collections.abc import AsyncGenerator
from typing import Any

from sensai.core.budget.summarizer import INSTRUCTION, LLMSummarizer
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Message, ToolCall
from sensai.providers.mock import MockLLMProvider


class RecordingProvider:
    def __init__(self, events: list[Event]) -> None:
        self.events = events
        self.prompts: list[list[Message]] = []
        self.tools: list[Any] = []

    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]:
        self.prompts.append(messages)
        self.tools.append(tools)
        for event in self.events:
            yield event


async def test_joins_streamed_chunks_and_strips():
    provider = MockLLMProvider(default_response=" the summary ", simulated_delay=0)

    result = await LLMSummarizer(lambda: provider).summarize(
        [Message(role="user", content="hi")]
    )

    assert result == "the summary"


async def test_prompt_is_instruction_then_transcript():
    provider = RecordingProvider([TextChunkEvent(content="ok")])
    messages = [
        Message(role="user", content="read a.txt"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(name="read_file", arguments={"path": "a.txt"})],
        ),
        Message(role="tool", content="body"),
    ]

    await LLMSummarizer(lambda: provider).summarize(messages)

    system, transcript = provider.prompts[0]
    assert system.role == "system"
    assert system.content == INSTRUCTION
    assert transcript.role == "user"
    assert transcript.content.splitlines() == [
        "user: read a.txt",
        "assistant:  [called read_file]",
        "tool: body",
    ]


async def test_no_tools_offered_to_the_model():
    provider = RecordingProvider([TextChunkEvent(content="ok")])

    await LLMSummarizer(lambda: provider).summarize(
        [Message(role="user", content="hi")]
    )

    assert provider.tools == [None]


async def test_tool_call_events_are_ignored():
    provider = RecordingProvider(
        [
            ToolCallEvent(tool_name="x", arguments={}),
            TextChunkEvent(content="kept"),
        ]
    )

    result = await LLMSummarizer(lambda: provider).summarize(
        [Message(role="user", content="hi")]
    )

    assert result == "kept"


async def test_empty_stream_gives_empty_summary():
    provider = RecordingProvider([])

    result = await LLMSummarizer(lambda: provider).summarize(
        [Message(role="user", content="hi")]
    )

    assert result == ""


async def test_provider_is_resolved_on_each_call():
    current = RecordingProvider([TextChunkEvent(content="first")])
    summarizer = LLMSummarizer(lambda: current)
    messages = [Message(role="user", content="hi")]

    assert await summarizer.summarize(messages) == "first"
    current = RecordingProvider([TextChunkEvent(content="second")])

    assert await summarizer.summarize(messages) == "second"
