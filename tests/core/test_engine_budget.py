from collections.abc import AsyncGenerator
from typing import Any

from sensai.core.budget import BudgetConfig, ContextBudget
from sensai.core.budget.manager import SUMMARY_PREFIX
from sensai.core.budget.tokens import count_message, count_text
from sensai.core.engine import ChatEngine
from sensai.domain.events import BudgetEvent, Event, TextChunkEvent
from sensai.domain.models import Conversation, Message


class RecordingProvider:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.prompts: list[list[Message]] = []

    async def chat_stream(
        self, messages: list[Message], tools: list[dict[str, Any]] | None = None
    ) -> AsyncGenerator[Event]:
        self.prompts.append(messages)
        for chunk in self.chunks:
            yield TextChunkEvent(content=chunk)


class FakeSummarizer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def summarize(self, messages: list[Message]) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return "gist"


def _long_conversation(turns: int = 6) -> Conversation:
    conversation = Conversation()
    for n in range(turns):
        conversation.add_message("user", f"q{n} " + "x" * 40)
        conversation.add_message("assistant", f"a{n} " + "x" * 40)
    return conversation


def _budget(max_tokens: int, summarizer: FakeSummarizer) -> ContextBudget:
    config = BudgetConfig(max_tokens=max_tokens, keep_recent_turns=2)
    return ContextBudget(config, summarizer)


async def test_no_budget_yields_no_budget_events():
    engine = ChatEngine(RecordingProvider(["hi"]), Conversation())

    events = [event async for event in engine.send("hello")]

    assert not any(isinstance(e, BudgetEvent) for e in events)


async def test_budget_events_track_prompt_then_each_chunk():
    provider = RecordingProvider(["abcd", "efghijkl"])
    engine = ChatEngine(
        provider, Conversation(), budget=_budget(10_000, FakeSummarizer())
    )

    events = [event async for event in engine.send("hello")]

    budgets = [e for e in events if isinstance(e, BudgetEvent)]
    prompt_tokens = sum(count_message(m) for m in provider.prompts[0])
    assert [b.used for b in budgets] == [
        prompt_tokens,
        prompt_tokens + count_text("abcd"),
        prompt_tokens + count_text("abcd") + count_text("efghijkl"),
    ]
    assert {b.max_tokens for b in budgets} == {10_000}


async def test_budget_event_follows_its_text_chunk():
    engine = ChatEngine(
        RecordingProvider(["a"]),
        Conversation(),
        budget=_budget(10_000, FakeSummarizer()),
    )

    kinds = [e.type async for e in engine.send("hello")]

    assert kinds == ["assistant_start", "budget", "text_chunk", "budget"]


async def test_history_compressed_before_the_model_call():
    conversation = _long_conversation()
    summarizer = FakeSummarizer()
    provider = RecordingProvider(["ok"])
    engine = ChatEngine(provider, conversation, budget=_budget(200, summarizer))

    _ = [event async for event in engine.send("latest question")]

    assert summarizer.calls == 1
    sent = provider.prompts[0]
    assert sent[0].content == SUMMARY_PREFIX + "gist"
    assert sent[-1].content == "latest question"
    assert conversation.messages[-1].role == "assistant"
    assert len(sent) < 13


async def test_summarizer_failure_does_not_break_the_chat():
    conversation = _long_conversation()
    provider = RecordingProvider(["ok"])
    engine = ChatEngine(
        provider, conversation, budget=_budget(200, FakeSummarizer(fail=True))
    )

    _ = [event async for event in engine.send("latest question")]

    assert len(provider.prompts[0]) == 13
    assert conversation.messages[-1].content == "ok"
