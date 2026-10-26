import sys
from collections.abc import AsyncIterator
from typing import TypeVar

from rich.console import Console
from rich.control import Control
from rich.segment import ControlType
from rich.text import Text

from sensai.domain.events import (
    AssistantStartEvent,
    BudgetEvent,
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
    ThoughtEvent,
    UsageEvent,
)
from sensai.domain.models import Conversation, ToolCall
from sensai.interfaces.cli.select import select
from sensai.interfaces.diff import diff_text
from sensai.interfaces.notices import guardrail_notice, max_steps_notice, step_notice
from sensai.interfaces.prompts import Question, tool_confirmation, tool_decision
from sensai.interfaces.thinking import Thinking, format_thinking
from sensai.interfaces.usage import format_metrics, format_usage

T = TypeVar("T")

_ROLE_LABELS = {
    "user": ("you: ", "bold blue"),
    "assistant": ("sensai: ", "bold magenta"),
}


def render_history(
    console: Console, conversation: Conversation, show_thoughts: bool = False
) -> None:
    for msg in conversation.messages:
        label = _ROLE_LABELS.get(msg.role)
        if label is None:
            continue
        prefix, style = label
        if show_thoughts and msg.thought:
            console.print(Text(f"  {msg.thought}", style="dim italic"))
        if msg.content or not msg.tool_calls:
            console.print(Text(prefix, style=style) + Text(msg.content))
    if conversation.messages:
        console.print()


class CliRenderer:
    def __init__(self, console: Console, show_thoughts: bool = False) -> None:
        self.console = console
        self.show_thoughts = show_thoughts
        self._line_open = False
        self._thought_open = False
        self._streaming = False
        self._thinking = Thinking(self._show_thinking)

    async def _show_thinking(self, elapsed: int | None) -> None:
        # Rewrites the current line, so it must not run over streamed text.
        if self._streaming or not self.console.is_terminal:
            return
        self.console.print(
            Control(ControlType.CARRIAGE_RETURN, (ControlType.ERASE_IN_LINE, 2)),
            end="",
        )
        label = Text("sensai: ", style="bold magenta") if self._line_open else Text()
        if elapsed is None:
            self.console.print(label, end="")
        else:
            label.append(format_thinking(elapsed, "Ctrl+C"), style="dim")
            self.console.print(label, end="")

    def _start_reply(self) -> None:
        if not self._line_open:
            self.console.print(Text("sensai: ", style="bold magenta"), end="")
            self._line_open = True

    def _close_thought(self) -> None:
        if self._thought_open:
            self.console.print()
            self._thought_open = False
            self._streaming = False

    def _show_thought(self, content: str) -> None:
        if not self._thought_open:
            self._finish_line()
            content = "  " + content.lstrip()
            self._thought_open = True
            self._streaming = True
        self.console.print(Text(content, style="dim italic"), end="", soft_wrap=True)

    def _finish_line(self) -> None:
        if self._line_open:
            self.console.print()
            self._line_open = False
        self._streaming = False

    def _interactive(self) -> bool:
        return self.console.is_terminal and sys.stdin.isatty()

    def _ask_text(self, question: Question[T]) -> T:
        self.console.print(Text(f"  {question.title}", style="bold"))
        width = max((len(key) for key, _ in question.details), default=0)
        for key, value in question.details:
            self.console.print(Text(f"    {key.ljust(width)}  ", style="dim") + value)
        labels = "/".join(option.text for option in question.options)
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
        diff = diff_text(tc)
        if diff is not None:
            self._finish_line()
            self.console.print(diff, end="")
        async with self._thinking.hold():
            approved = await self.ask(tool_confirmation(tc))
        style = "green" if approved else "red"
        self.console.print(Text(f"  {tool_decision(tc, approved)}", style=style))
        return approved

    async def render(self, events: AsyncIterator[Event]) -> None:
        self._line_open = False
        usage: BudgetEvent | None = None
        metrics = ""
        try:
            async for event in self._thinking.watch(events):
                if not isinstance(event, ThoughtEvent):
                    self._close_thought()
                if isinstance(event, AssistantStartEvent):
                    self._start_reply()
                elif isinstance(event, TextChunkEvent):
                    self._start_reply()
                    self._streaming = True
                    self.console.print(Text(event.content), end="", soft_wrap=True)
                elif isinstance(event, StepEvent):
                    if self.show_thoughts:
                        self._finish_line()
                        self.console.print(Text(step_notice(event), style="dim"))
                elif isinstance(event, ThoughtEvent):
                    if self.show_thoughts:
                        self._show_thought(event.content)
                elif isinstance(event, MaxStepsEvent):
                    self._finish_line()
                    self.console.print(Text(max_steps_notice(event), style="yellow"))
                elif isinstance(event, BudgetEvent):
                    usage = event
                elif isinstance(event, UsageEvent):
                    metrics = format_metrics(event)  # last call = the reply
                elif isinstance(event, GuardrailEvent):
                    self._finish_line()
                    self.console.print(
                        Text(f"⚠ {guardrail_notice(event)}", style="yellow")
                    )
        finally:
            self._close_thought()
            self._finish_line()
            if usage is not None:
                self.console.print(Text(format_usage(usage), style="dim"))
            if metrics:
                self.console.print(Text(metrics, style="dim"))


async def render_stream(console: Console, events: AsyncIterator[Event]) -> None:
    await CliRenderer(console).render(events)
