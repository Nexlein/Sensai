"""One model call streamed through output filters."""

import pytest

from sensai.core.streaming import RoundStreamer
from sensai.domain.errors import ProviderError
from sensai.domain.events import (
    BudgetEvent,
    GuardrailEvent,
    TextChunkEvent,
    ThoughtEvent,
    ToolCallEvent,
    UsageEvent,
)
from sensai.domain.models import Message
from sensai.eval.guardrails import RegexGuardrail

PROMPT = [Message(role="user", content="hi")]
SCHEMA = [{"name": "dummy"}]


class Scripted:
    def __init__(self, *events, fail=None):
        self.events = events
        self.fail = fail
        self.options = None

    async def chat_stream(self, messages, tools=None, **options):
        self.options = options
        for event in self.events:
            yield event
        if self.fail is not None:
            raise self.fail


async def _run(streamer, tools=None):
    stream = streamer.open(PROMPT, tools)
    return [event async for event in stream.events()], stream.reply


@pytest.mark.asyncio
async def test_text_is_streamed_and_collected():
    provider = Scripted(TextChunkEvent(content="he"), TextChunkEvent(content="llo"))

    events, reply = await _run(RoundStreamer(provider))

    assert [e.content for e in events] == ["he", "llo"]
    assert reply.text == "hello"
    assert not reply.tool_calls


@pytest.mark.asyncio
async def test_tool_calls_are_recorded_and_forwarded_when_not_held():
    call = ToolCallEvent(tool_name="dummy", arguments={"a": 1})

    events, reply = await _run(RoundStreamer(Scripted(call)), SCHEMA)

    assert events == [call]
    assert [(tc.name, tc.arguments) for tc in reply.tool_calls] == [("dummy", {"a": 1})]


@pytest.mark.asyncio
async def test_native_thoughts_are_dropped_without_reasoning():
    provider = Scripted(ThoughtEvent(content="hmm", source="native"))

    events, reply = await _run(RoundStreamer(provider))

    assert events == []
    assert reply.thought is None


@pytest.mark.asyncio
async def test_native_thoughts_are_kept_with_reasoning():
    provider = Scripted(ThoughtEvent(content="hmm", source="native"))

    events, reply = await _run(RoundStreamer(provider, reasoning=True))

    assert [(e.content, e.source) for e in events] == [("hmm", "native")]
    assert reply.thought == "hmm"


@pytest.mark.asyncio
async def test_text_before_tool_calls_becomes_a_thought_when_held():
    provider = Scripted(
        TextChunkEvent(content="let me look"),
        ToolCallEvent(tool_name="dummy", arguments={}),
    )
    streamer = RoundStreamer(provider, reasoning=True, split_thoughts=True)

    events, reply = await _run(streamer, SCHEMA)

    assert [type(e) for e in events] == [ThoughtEvent, ToolCallEvent]
    assert events[0].source == "text"
    assert reply.message_text == ""
    assert reply.thought == "let me look"


@pytest.mark.asyncio
async def test_held_text_is_released_as_the_answer_without_tool_calls():
    provider = Scripted(TextChunkEvent(content="final"))
    streamer = RoundStreamer(provider, reasoning=True, split_thoughts=True)

    events, reply = await _run(streamer, SCHEMA)

    assert [e.content for e in events] == ["final"]
    assert reply.message_text == "final"


@pytest.mark.asyncio
async def test_think_option_is_passed_only_with_reasoning():
    provider = Scripted()
    await _run(RoundStreamer(provider, reasoning=True, think="high"))
    assert provider.options == {"think": "high"}

    provider = Scripted()
    await _run(RoundStreamer(provider, reasoning=False, think="high"))
    assert provider.options == {}


@pytest.mark.asyncio
async def test_output_guardrail_redacts_and_reports():
    provider = Scripted(TextChunkEvent(content="write to jo@example.com now"))

    events, reply = await _run(RoundStreamer(provider, guardrail=RegexGuardrail()))

    assert "jo@example.com" not in reply.text
    guards = [e for e in events if isinstance(e, GuardrailEvent)]
    assert [(g.stage, g.action) for g in guards] == [("output", "redact")]


@pytest.mark.asyncio
async def test_runtime_error_becomes_a_provider_error():
    provider = Scripted(fail=RuntimeError("HTTP 500"))

    with pytest.raises(ProviderError):
        await _run(RoundStreamer(provider))


@pytest.mark.asyncio
async def test_a_provider_error_passes_through_unchanged():
    original = ProviderError("readable")

    with pytest.raises(ProviderError) as raised:
        await _run(RoundStreamer(Scripted(fail=original)))

    assert raised.value is original


@pytest.mark.asyncio
async def test_budget_events_track_usage():
    from sensai.core.budget import BudgetConfig, ContextBudget

    class Summ:
        async def summarize(self, messages):
            return ""

    budget = ContextBudget(BudgetConfig(), Summ())
    provider = Scripted(TextChunkEvent(content="hello"))

    events, _ = await _run(RoundStreamer(provider, budget=budget))

    budgets = [e for e in events if isinstance(e, BudgetEvent)]
    assert len(budgets) == 2
    assert budgets[1].used > budgets[0].used


@pytest.mark.asyncio
async def test_usage_is_passed_on_and_kept_on_the_reply():
    usage = UsageEvent(prompt_tokens=10, reply_tokens=2)
    provider = Scripted(TextChunkEvent(content="ok"), usage)

    events, reply = await _run(RoundStreamer(provider))

    assert usage in events
    assert reply.usage is usage
