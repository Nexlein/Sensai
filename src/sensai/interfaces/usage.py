from sensai.domain.events import BudgetEvent


def _short(tokens: int) -> str:
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)


def format_usage(event: BudgetEvent) -> str:
    percent = event.used * 100 // event.max_tokens
    return f"{_short(event.used)} / {_short(event.max_tokens)} tokens ({percent}%)"
