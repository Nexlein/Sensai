from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Markdown, Static

from sensai.core.commands import CommandResult, RenderFn
from sensai.core.engine import ConfirmTool
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import BudgetEvent, Event, GuardrailEvent, TextChunkEvent
from sensai.domain.models import ToolCall
from sensai.interfaces.diff import diff_text
from sensai.interfaces.notices import guardrail_notice
from sensai.interfaces.prompts import Question, tool_confirmation, tool_decision
from sensai.interfaces.tui.question import QuestionPrompt
from sensai.interfaces.usage import format_usage

T = TypeVar("T")

ProcessFn = Callable[[str, RenderFn, ConfirmTool], Awaitable[CommandResult]]


def error_text(exc: Exception) -> str:
    if isinstance(exc, EmptyInputError):
        return "Empty input — please enter a message before sending."
    if isinstance(exc, ProviderError):
        if isinstance(exc.__cause__, httpx.ConnectError):
            return "Connection failed — could not connect to the model server."
        return "Model unavailable — the model is unavailable or returned an error."
    return f"Unexpected error — {exc}"


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


class ChatApp(App[None]):
    CSS = """
    Input {
        dock: bottom;
    }
    """

    def __init__(self, process: ProcessFn) -> None:
        super().__init__()
        self._process = process

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
        self._respond(event.value, input_widget)

    @work
    async def _respond(self, text: str, input_widget: Input) -> None:
        try:
            await self._process_turn(text)
        finally:
            input_widget.disabled = False
            input_widget.focus()

    async def _process_turn(self, text: str) -> None:
        history = self.query_one("#history", VerticalScroll)
        await history.mount(RoleLabel("you", classes="user"))
        await history.mount(UserMessage(text))
        history.scroll_end(animate=False)

        async def confirm_tool(tc: ToolCall) -> bool:
            diff = diff_text(tc)
            if diff is not None:
                await history.mount(ToolDiff(diff))
                history.scroll_end(animate=False)
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
                async for streamed in events:
                    if isinstance(streamed, TextChunkEvent):
                        if reply is None:
                            reply = AssistantMessage("")
                            await history.mount(reply)
                        content += streamed.content
                        await reply.update(content)
                        if usage_text:
                            await show_usage()
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
                if reply is None:
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
