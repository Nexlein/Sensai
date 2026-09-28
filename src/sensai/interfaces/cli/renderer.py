from collections.abc import AsyncIterator

import httpx
from rich.console import Console
from rich.live import Live
from rich.text import Text

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent
from sensai.domain.models import Conversation

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
    with Live(label, console=console, refresh_per_second=15) as live:
        async for chunk_event in events:
            if isinstance(chunk_event, TextChunkEvent):
                content += chunk_event.content
                live.update(label + Text(content))
