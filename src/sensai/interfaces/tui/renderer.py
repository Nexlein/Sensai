from collections.abc import AsyncIterator, Awaitable, Callable
from typing import ClassVar

import httpx
from textual import work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, Static

from sensai.core.commands import CommandResult, RenderFn
from sensai.core.engine import ConfirmTool
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, GuardrailEvent, TextChunkEvent
from sensai.domain.models import ToolCall
from sensai.interfaces.notices import guardrail_notice

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


class ConfirmToolScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[BindingType]] = [("escape", "deny", "Refuser")]

    def __init__(self, tc: ToolCall) -> None:
        super().__init__()
        self.tc = tc

    def compose(self) -> ComposeResult:
        yield Static(
            f"Autoriser l'outil {self.tc.name} ?\n{self.tc.arguments}", markup=False
        )
        yield Button("Oui", id="yes")
        yield Button("Non", id="no")

    def on_mount(self) -> None:
        self.query_one("#yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_deny(self) -> None:
        self.dismiss(False)


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
            return await self.push_screen_wait(ConfirmToolScreen(tc))

        async def render(events: AsyncIterator[Event]) -> None:
            label = RoleLabel("sensai", classes="assistant")
            await history.mount(label)
            history.scroll_end(animate=False)
            reply: AssistantMessage | None = None
            content = ""
            try:
                async for chunk_event in events:
                    if isinstance(chunk_event, TextChunkEvent):
                        if reply is None:
                            reply = AssistantMessage("")
                            await history.mount(reply)
                        content += chunk_event.content
                        await reply.update(content)
                        history.scroll_end(animate=False)
                    elif isinstance(chunk_event, GuardrailEvent):
                        await history.mount(
                            GuardrailNotice(f"⚠ {guardrail_notice(chunk_event)}")
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
