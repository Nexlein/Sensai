import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import ClassVar, TypeVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.widgets import Input, Markdown, Static
from textual.worker import Worker

from sensai.core.commands import CommandResult, RenderFn
from sensai.core.tool_runner import ConfirmTool
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import (
    BudgetEvent,
    Event,
    GuardrailEvent,
    MaxStepsEvent,
    StepEvent,
    TextChunkEvent,
    ThoughtEvent,
)
from sensai.domain.models import ToolCall
from sensai.interfaces.diff import diff_text
from sensai.interfaces.notices import (
    error_text,
    guardrail_notice,
    max_steps_notice,
    step_notice,
)
from sensai.interfaces.prompts import Question, tool_confirmation, tool_decision
from sensai.interfaces.thinking import Thinking, format_thinking
from sensai.interfaces.tui.question import QuestionPrompt
from sensai.interfaces.usage import format_usage

T = TypeVar("T")

ProcessFn = Callable[[str, RenderFn, ConfirmTool], Awaitable[CommandResult]]


class RoleLabel(Static):
    DEFAULT_CSS = """
    RoleLabel {
        text-style: bold;
        height: 1;
    }
    RoleLabel.user {
        margin: 1 0 0 2;
        color: #7aa2f7;
    }
    RoleLabel.assistant {
        margin: 0 0 0 2;
        color: #bb9af7;
    }
    """


class UserMessage(Markdown):
    DEFAULT_CSS = """
    UserMessage {
        margin: 0 0 0 2;
        padding: 0 0 0 0;
    }
    UserMessage > MarkdownParagraph {
        margin: 0 0 0 0;
    }
    """


class AssistantMessage(Markdown):
    DEFAULT_CSS = """
    AssistantMessage {
        margin: 0 0 1 2;
        padding: 0 0 0 0;
    }
    AssistantMessage > MarkdownParagraph {
        margin: 0 0 0 0;
    }
    """


class UsageLabel(Static):
    DEFAULT_CSS = """
    UsageLabel {
        margin: 0 0 0 2;
        color: $text-muted;
    }
    """


class ErrorMessage(Static):
    DEFAULT_CSS = """
    ErrorMessage {
        color: $text-error;
        text-style: bold;
        margin: 1 0 0 2;
    }
    """


class GuardrailNotice(Static):
    DEFAULT_CSS = """
    GuardrailNotice {
        color: $text-warning;
        margin: 0 0 0 2;
    }
    """


class ToolDiff(Static):
    DEFAULT_CSS = """
    ToolDiff {
        margin: 0 0 0 2;
    }
    """


class ToolDecisionNotice(Static):
    DEFAULT_CSS = """
    ToolDecisionNotice {
        margin: 0 0 0 2;
        color: $text-muted;
    }
    ToolDecisionNotice.approved {
        color: $text-success;
    }
    ToolDecisionNotice.declined {
        color: $text-error;
    }
    """


class ThinkingLabel(Static):
    DEFAULT_CSS = """
    ThinkingLabel {
        margin: 0 0 0 2;
        color: $text-muted;
        text-style: italic;
    }
    """


class ThoughtMessage(Static):
    DEFAULT_CSS = """
    ThoughtMessage {
        margin: 0 0 0 2;
        color: $text-muted;
        text-style: italic;
    }
    """


class StepLabel(Static):
    DEFAULT_CSS = """
    StepLabel {
        margin: 0 0 0 2;
        color: $text-muted;
    }
    """


class StoppedNotice(Static):
    DEFAULT_CSS = """
    StoppedNotice {
        margin: 1 0 0 2;
        color: $text-warning;
    }
    """


class ChatApp(App[None]):
    CSS = """
    Input {
        dock: bottom;
    }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "stop_turn", "Stop", show=False),
    ]

    def __init__(self, process: ProcessFn, show_thoughts: bool = False) -> None:
        super().__init__()
        self._show_thoughts = show_thoughts
        self._process = process
        self._turn: Worker[None] | None = None

    def action_stop_turn(self) -> None:
        if self._turn is not None and self._turn.is_running:
            self._turn.cancel()

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="history")
        yield Input(placeholder="Message Sensai…")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    async def ask(self, question: Question[T]) -> T:
        input_widget = self.query_one(Input)
        prompt: QuestionPrompt[T] = QuestionPrompt(question)
        input_widget.display = False
        await self.mount(prompt)
        prompt.focus()
        try:
            return await prompt.answer
        finally:
            await prompt.remove()
            input_widget.display = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_widget = self.query_one(Input)
        if input_widget.disabled:
            return
        input_widget.disabled = True
        input_widget.value = ""
        self._turn = self._respond(event.value, input_widget)

    @work
    async def _respond(self, text: str, input_widget: Input) -> None:
        try:
            await self._process_turn(text)
        except asyncio.CancelledError:
            # Esc stopped the turn: report it and go back to the prompt.
            history = self.query_one("#history", VerticalScroll)
            await history.mount(StoppedNotice("Stopped."))
            history.scroll_end(animate=False)
        finally:
            input_widget.disabled = False
            input_widget.focus()

    async def _process_turn(self, text: str) -> None:
        history = self.query_one("#history", VerticalScroll)
        await history.mount(RoleLabel("you", classes="user"))
        await history.mount(UserMessage(text))
        history.scroll_end(animate=False)

        indicator: ThinkingLabel | None = None

        async def show_thinking(elapsed: int | None) -> None:
            nonlocal indicator
            if elapsed is None:
                if indicator is not None:
                    await indicator.remove()
                    indicator = None
                return
            text = format_thinking(elapsed, "Esc")
            if indicator is None:
                indicator = ThinkingLabel(text)
                await history.mount(indicator)
                history.scroll_end(animate=False)
            else:
                indicator.update(text)

        thinking = Thinking(show_thinking)

        async def confirm_tool(tc: ToolCall) -> bool:
            diff = diff_text(tc)
            if diff is not None:
                await history.mount(ToolDiff(diff))
                history.scroll_end(animate=False)
            async with thinking.hold():
                approved = await self.ask(tool_confirmation(tc))
            await history.mount(
                ToolDecisionNotice(
                    tool_decision(tc, approved),
                    classes="approved" if approved else "declined",
                )
            )
            history.scroll_end(animate=False)
            return approved

        async def render(events: AsyncIterator[Event]) -> None:
            label = RoleLabel("sensai", classes="assistant")
            await history.mount(label)
            history.scroll_end(animate=False)
            reply: AssistantMessage | None = None
            shown = False
            thought: ThoughtMessage | None = None
            thought_text = ""
            content = ""
            usage: UsageLabel | None = None
            usage_text = ""

            async def show_usage() -> None:
                nonlocal usage
                if usage is None:
                    usage = UsageLabel()
                    await history.mount(usage)
                usage.update(usage_text)

            try:
                async for streamed in thinking.watch(events):
                    if not isinstance(streamed, ThoughtEvent):
                        thought = None
                    if isinstance(streamed, TextChunkEvent):
                        if reply is None:
                            reply = AssistantMessage("")
                            await history.mount(reply)
                        content += streamed.content
                        await reply.update(content)
                        if usage_text:
                            await show_usage()
                    elif isinstance(streamed, StepEvent):
                        if self._show_thoughts:
                            shown = True
                            await history.mount(StepLabel(step_notice(streamed)))
                    elif isinstance(streamed, ThoughtEvent):
                        if self._show_thoughts:
                            shown = True
                            if thought is None:
                                thought_text = ""
                                thought = ThoughtMessage("")
                                await history.mount(thought)
                            thought_text += streamed.content
                            thought.update(thought_text.strip())
                    elif isinstance(streamed, MaxStepsEvent):
                        await history.mount(GuardrailNotice(max_steps_notice(streamed)))
                    elif isinstance(streamed, BudgetEvent):
                        usage_text = format_usage(streamed)
                        if reply is not None:
                            await show_usage()
                    elif isinstance(streamed, GuardrailEvent):
                        await history.mount(
                            GuardrailNotice(f"⚠ {guardrail_notice(streamed)}")
                        )
                    history.scroll_end(animate=False)
            finally:
                if reply is None and not shown:
                    await label.remove()

        try:
            result = await self._process(text, render, confirm_tool)
        except (EmptyInputError, ProviderError) as exc:
            await history.mount(ErrorMessage(error_text(exc)))
            history.scroll_end(animate=False)
            return

        if result.message:
            await history.mount(RoleLabel("sensai", classes="assistant"))
            await history.mount(AssistantMessage(result.message))
            history.scroll_end(animate=False)
        if result.should_exit:
            self.exit()


def run_chat(process: ProcessFn) -> None:
    ChatApp(process).run()
