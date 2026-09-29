import httpx

from sensai.core.budget import BudgetConfig
from sensai.core.budget.manager import SUMMARY_PREFIX, ContextBudget
from sensai.core.budget.tokens import count_message
from sensai.domain.models import Conversation, Message


class FakeSummarizer:
    def __init__(self, result: str = "short", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[list[Message]] = []

    async def summarize(self, messages: list[Message]) -> str:
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.result


def _conversation(turns: int, size: int = 40) -> Conversation:
    conversation = Conversation()
    for n in range(turns):
        conversation.add_message("user", f"q{n} " + "x" * size)
        conversation.add_message("assistant", f"a{n} " + "x" * size)
    return conversation


def _budget(
    summarizer: FakeSummarizer, conversation: Conversation, threshold: float = 0.8
) -> ContextBudget:
    used = sum(count_message(m) for m in conversation.messages)
    config = BudgetConfig(max_tokens=used, threshold=threshold, keep_recent_turns=2)
    return ContextBudget(config, summarizer)


def test_usage_sums_message_tokens():
    conversation = _conversation(2)
    budget = _budget(FakeSummarizer(), conversation)

    usage = budget.usage(conversation)

    assert usage.used == sum(count_message(m) for m in conversation.messages)
    assert usage.ratio == 1.0


def test_usage_of_empty_conversation_is_zero():
    budget = ContextBudget(BudgetConfig(), FakeSummarizer())

    usage = budget.usage(Conversation())

    assert (usage.used, usage.ratio) == (0, 0)


async def test_below_threshold_does_nothing():
    conversation = _conversation(4)
    summarizer = FakeSummarizer()
    budget = ContextBudget(BudgetConfig(max_tokens=100_000), summarizer)

    assert await budget.fit(conversation) is False
    assert summarizer.calls == []
    assert len(conversation.messages) == 8


async def test_at_threshold_compresses():
    conversation = _conversation(4)
    original = list(conversation.messages)
    summarizer = FakeSummarizer("the gist")
    budget = _budget(summarizer, conversation, threshold=1.0)

    assert await budget.fit(conversation) is True

    assert summarizer.calls == [original[:4]]
    summary, *recent = conversation.messages
    assert summary.role == "system"
    assert summary.content == SUMMARY_PREFIX + "the gist"
    assert recent == original[4:]


async def test_nothing_old_enough_does_nothing():
    conversation = _conversation(2)
    summarizer = FakeSummarizer()
    budget = _budget(summarizer, conversation)

    assert await budget.fit(conversation) is False
    assert summarizer.calls == []


async def test_summarizer_error_leaves_history_untouched():
    for error in (RuntimeError("boom"), httpx.ConnectError("down")):
        conversation = _conversation(4)
        original = list(conversation.messages)
        budget = _budget(FakeSummarizer(error=error), conversation)

        assert await budget.fit(conversation) is False
        assert conversation.messages == original


async def test_empty_summary_leaves_history_untouched():
    conversation = _conversation(4)
    original = list(conversation.messages)
    budget = _budget(FakeSummarizer(""), conversation)

    assert await budget.fit(conversation) is False
    assert conversation.messages == original


async def test_second_pass_folds_previous_summary():
    conversation = _conversation(4)
    summarizer = FakeSummarizer("first")
    budget = _budget(summarizer, conversation, threshold=0.1)
    await budget.fit(conversation)
    for n in range(4, 6):
        conversation.add_message("user", f"q{n}")
        conversation.add_message("assistant", f"a{n}")
    summarizer.result = "second"

    assert await budget.fit(conversation) is True

    assert summarizer.calls[1][0].content == SUMMARY_PREFIX + "first"
    assert conversation.messages[0].content == SUMMARY_PREFIX + "second"
    assert sum(m.role == "system" for m in conversation.messages) == 1


async def test_lone_summary_is_not_resummarized():
    conversation = _conversation(4)
    summarizer = FakeSummarizer("first")
    budget = _budget(summarizer, conversation, threshold=0.1)
    await budget.fit(conversation)

    assert await budget.fit(conversation) is False
    assert len(summarizer.calls) == 1
