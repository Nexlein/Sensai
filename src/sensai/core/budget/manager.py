import httpx

from sensai.core.budget.config import BudgetConfig
from sensai.core.budget.tokens import count_message
from sensai.core.budget.tracker import UsageTracker
from sensai.core.budget.usage import BudgetUsage
from sensai.core.budget.window import split_window
from sensai.domain.models import Conversation, Message, now_utc
from sensai.domain.protocols import Summarizer

SUMMARY_PREFIX = "Summary of earlier conversation:\n"


def _is_summary(message: Message) -> bool:
    return message.role == "system" and message.content.startswith(SUMMARY_PREFIX)


class ContextBudget:
    def __init__(self, config: BudgetConfig, summarizer: Summarizer) -> None:
        self.config = config
        self.summarizer = summarizer

    def usage(self, conversation: Conversation) -> BudgetUsage:
        used = sum(count_message(m) for m in conversation.messages)
        return BudgetUsage(used, self.config.max_tokens)

    def tracker(self, prompt: list[Message]) -> UsageTracker:
        """Start live counting from the exact prompt about to be sent."""
        used = sum(count_message(m) for m in prompt)
        return UsageTracker(used, self.config.max_tokens)

    async def fit(self, conversation: Conversation) -> bool:
        """Condense the oldest turns once the threshold is reached."""
        if self.usage(conversation).ratio < self.config.threshold:
            return False

        old, recent = split_window(conversation.messages, self.config.keep_recent_turns)
        if not old or (len(old) == 1 and _is_summary(old[0])):
            return False

        try:
            summary = await self.summarizer.summarize(old)
        except (RuntimeError, httpx.HTTPError):
            return False
        if not summary:
            return False

        conversation.messages = [
            Message(role="system", content=SUMMARY_PREFIX + summary),
            *recent,
        ]
        conversation.updated_at = now_utc()
        return True
