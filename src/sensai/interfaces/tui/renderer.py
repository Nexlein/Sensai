from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Markdown, Static

from sensai.core.commands import CommandResult, RenderFn
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import BudgetEvent, Event, GuardrailEvent, TextChunkEvent
from sensai.interfaces.notices import guardrail_notice
from sensai.interfaces.usage import format_usage

ProcessFn = Callable[[str, RenderFn], Awaitable[CommandResult]]


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
        margin: 0 0 0 2;
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

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        input_widget = self.query_one(Input)
        input_widget.value = ""

        history = self.query_one("#history", VerticalScroll)
        await history.mount(RoleLabel("you", classes="user"))
        await history.mount(UserMessage(text))
        history.scroll_end(animate=False)

        async def render(events: AsyncIterator[Event]) -> None:
            # The reply widget appears with the first text, so a blocked message
            # does not leave an empty "sensai" bubble behind.
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

            async for streamed in events:
                if isinstance(streamed, TextChunkEvent):
                    if reply is None:
                        await history.mount(RoleLabel("sensai", classes="assistant"))
                        reply = AssistantMessage("")
                        await history.mount(reply)
                    content += streamed.content
                    await reply.update(content)
                    if usage_text:
                        await show_usage()
                elif isinstance(streamed, BudgetEvent):
                    usage_text = format_usage(streamed)
                    # Usage sits under the reply, so wait until the reply exists.
                    if reply is not None:
                        await show_usage()
                elif isinstance(streamed, GuardrailEvent):
                    await history.mount(
                        GuardrailNotice(f"⚠ {guardrail_notice(streamed)}")
                    )
                history.scroll_end(animate=False)

        try:
            result = await self._process(text, render)
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
