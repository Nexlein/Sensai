from collections.abc import AsyncIterator, Callable

import httpx
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Markdown, Static

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent

SendFn = Callable[[str], AsyncIterator[Event]]


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


class ErrorMessage(Static):
    DEFAULT_CSS = """
    ErrorMessage {
        color: $text-error;
        text-style: bold;
        margin: 1 0 0 2;
    }
    """


class ChatApp(App[None]):
    CSS = """
    Input {
        dock: bottom;
    }
    """

    def __init__(self, send: SendFn) -> None:
        super().__init__()
        self._send = send

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

        await history.mount(RoleLabel("sensai", classes="assistant"))
        reply = AssistantMessage("")
        await history.mount(reply)
        history.scroll_end(animate=False)

        content = ""
        try:
            async for chunk_event in self._send(text):
                if isinstance(chunk_event, TextChunkEvent):
                    content += chunk_event.content
                    await reply.update(content)
                    history.scroll_end(animate=False)
        except (EmptyInputError, ProviderError) as exc:
            await history.mount(ErrorMessage(error_text(exc)))
            history.scroll_end(animate=False)


def run_chat(send: SendFn) -> None:
    ChatApp(send).run()
