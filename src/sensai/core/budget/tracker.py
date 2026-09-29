from sensai.core.budget.tokens import count_text
from sensai.core.budget.usage import BudgetUsage


class UsageTracker:
    """Running token count of one request while its answer streams in."""

    def __init__(self, prompt_tokens: int, max_tokens: int) -> None:
        self.used = prompt_tokens
        self.max_tokens = max_tokens

    def add(self, text: str) -> BudgetUsage:
        self.used += count_text(text)
        return BudgetUsage(self.used, self.max_tokens)
