import json
from collections.abc import AsyncIterator

import httpx
from rich.console import Console
from rich.text import Text

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    AssistantStartEvent,
    Event,
    GuardrailEvent,
    TextChunkEvent,
)
from sensai.domain.models import Conversation, ToolCall
from sensai.interfaces.notices import guardrail_notice

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


class CliRenderer:
    """Write chunks as they arrive and keep tool prompts on separate lines."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._line_open = False

    def _start_reply(self) -> None:
        if not self._line_open:
            self.console.print(Text("sensai: ", style="bold magenta"), end="")
            self._line_open = True

    def _finish_line(self) -> None:
        if self._line_open:
            self.console.print()
            self._line_open = False

    async def confirm_tool(self, tc: ToolCall) -> bool:
        self._finish_line()
        self.console.print(Text(json.dumps(tc.arguments, ensure_ascii=False)))
        try:
            answer = self.console.input(Text(f"Autoriser {tc.name} ? [O/n] "))
            return answer.strip().lower() in {"", "o", "oui", "y", "yes"}
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return False

    async def render(self, events: AsyncIterator[Event]) -> None:
        self._line_open = False
        try:
            async for event in events:
                if isinstance(event, AssistantStartEvent):
                    self._start_reply()
                elif isinstance(event, TextChunkEvent):
                    self._start_reply()
                    self.console.print(Text(event.content), end="", soft_wrap=True)
                elif isinstance(event, GuardrailEvent):
                    self._finish_line()
                    self.console.print(
                        Text(f"⚠ {guardrail_notice(event)}", style="yellow")
                    )
        finally:
            self._finish_line()


async def render_stream(console: Console, events: AsyncIterator[Event]) -> None:
    await CliRenderer(console).render(events)
