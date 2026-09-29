from collections.abc import AsyncIterator

import httpx
from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import BudgetEvent, Event, TextChunkEvent
from sensai.domain.models import Conversation
from sensai.interfaces.usage import format_usage

_ROLE_LABELS = {
    "user": ("you: ", "bold blue"),
    "assistant": ("sensai: ", "bold magenta"),
}


def error_text(exc: Exception) -> str:
    if isinstance(exc, EmptyInputError):
        return "Empty input — please enter a message before sending."
    if isinstance(exc, ProviderError):
        if isinstance(exc.__cause__, httpx.ConnectError):
            return "Connection failed — could not connect to the model server."
        return "Model unavailable — the model is unavailable or returned an error."
    return f"Unexpected error — {exc}"


def render_history(console: Console, conversation: Conversation) -> None:
    for msg in conversation.messages:
        label = _ROLE_LABELS.get(msg.role)
        if label is None:
            continue
        prefix, style = label
        console.print(Text(prefix, style=style) + Text(msg.content))
    if conversation.messages:
        console.print()


async def render_stream(console: Console, events: AsyncIterator[Event]) -> None:
    label = Text("sensai: ", style="bold magenta")
    content = ""
    footer: Text | None = None
    with Live(label, console=console, refresh_per_second=15) as live:
        async for event in events:
            if isinstance(event, TextChunkEvent):
                content += event.content
            elif isinstance(event, BudgetEvent):
                footer = Text(format_usage(event), style="dim")
            else:
                continue
            body = label + Text(content)
            live.update(Group(body, footer) if footer else body)
