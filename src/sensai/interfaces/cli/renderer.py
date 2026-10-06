import sys
from collections.abc import AsyncIterator
from typing import TypeVar

import httpx
from rich.console import Console
from rich.text import Text

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    AssistantStartEvent,
    BudgetEvent,
    Event,
    GuardrailEvent,
    TextChunkEvent,
)
from sensai.domain.models import Conversation, ToolCall
from sensai.interfaces.cli.select import select
from sensai.interfaces.notices import guardrail_notice
from sensai.interfaces.prompts import Question, tool_confirmation, tool_decision
from sensai.interfaces.usage import format_usage

T = TypeVar("T")

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

    def _interactive(self) -> bool:
        return self.console.is_terminal and sys.stdin.isatty()

    def _ask_text(self, question: Question[T]) -> T:
        self.console.print(Text(f"  {question.title}", style="bold"))
        width = max((len(key) for key, _ in question.details), default=0)
        for key, value in question.details:
            self.console.print(Text(f"    {key.ljust(width)}  ", style="dim") + value)
        labels = "/".join(option.label for option in question.options)
        try:
            answer = self.console.input(Text(f"  [{labels}] ", style="dim"))
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return question.cancel_value
        return question.resolve(answer)

    async def ask(self, question: Question[T]) -> T:
        self._finish_line()
        if self._interactive():
            return await select(question)
        return self._ask_text(question)

    async def confirm_tool(self, tc: ToolCall) -> bool:
        approved = await self.ask(tool_confirmation(tc))
        style = "green" if approved else "red"
        self.console.print(Text(f"  {tool_decision(tc, approved)}", style=style))
        return approved

    async def render(self, events: AsyncIterator[Event]) -> None:
        self._line_open = False
        usage: BudgetEvent | None = None
        try:
            async for event in events:
                if isinstance(event, AssistantStartEvent):
                    self._start_reply()
                elif isinstance(event, TextChunkEvent):
                    self._start_reply()
                    self.console.print(Text(event.content), end="", soft_wrap=True)
                elif isinstance(event, BudgetEvent):
                    usage = event
                elif isinstance(event, GuardrailEvent):
                    self._finish_line()
                    self.console.print(
                        Text(f"⚠ {guardrail_notice(event)}", style="yellow")
                    )
        finally:
            self._finish_line()
            if usage is not None:
                self.console.print(Text(format_usage(usage), style="dim"))


async def render_stream(console: Console, events: AsyncIterator[Event]) -> None:
    await CliRenderer(console).render(events)
