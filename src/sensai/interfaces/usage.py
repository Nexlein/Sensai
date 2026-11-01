from sensai.domain.events import BudgetEvent, UsageEvent


def _short(tokens: int) -> str:
    return f"{tokens / 1000:.1f}k" if tokens >= 1000 else str(tokens)


def format_usage(event: BudgetEvent) -> str:
    percent = event.used * 100 // event.max_tokens
    return f"{_short(event.used)} / {_short(event.max_tokens)} tokens ({percent}%)"


def _count(tokens: int) -> str:
    return f"{tokens:,}".replace(",", " ")


def format_metrics(event: UsageEvent) -> str:
    """The server's real counters for the reply; "" when it reported none."""
    parts = []
    if event.prompt_tokens is not None:
        parts.append(f"prompt {_count(event.prompt_tokens)} tok")
    if event.reply_tokens is not None:
        parts.append(f"reply {_count(event.reply_tokens)} tok")
    if event.reply_rate is not None:
        parts.append(f"{event.reply_rate:.1f} tok/s")
    if event.first_token_seconds is not None:
        parts.append(f"first token {event.first_token_seconds:.1f} s")
    if event.total_seconds is not None:
        parts.append(f"total {event.total_seconds:.1f} s")
    return " · ".join(parts)
