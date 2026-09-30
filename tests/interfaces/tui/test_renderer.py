import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from sensai.core.commands import CommandResult, RenderFn
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, GuardrailEvent, TextChunkEvent, ToolCallEvent
from sensai.interfaces.tui.renderer import (
    AssistantMessage,
    ChatApp,
    ErrorMessage,
    GuardrailNotice,
    RoleLabel,
    UserMessage,
    error_text,
)


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def _raising(exc: Exception) -> AsyncIterator[Event]:
    raise exc
    yield  # pragma: no cover


def _process_events(*items: Event):
    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(_events(*items))
        return CommandResult()

    return process


@pytest.mark.asyncio
async def test_submitting_input_mounts_user_message_and_streamed_reply():
    app = ChatApp(
        _process_events(TextChunkEvent(content="hel"), TextChunkEvent(content="lo"))
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        for char in "hi":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

        user_messages = app.query(UserMessage)
        assert len(user_messages) == 1
        assert "hi" in user_messages.first().source

        assistant_messages = app.query(AssistantMessage)
        assert len(assistant_messages) == 1
        assert assistant_messages.first().source == "hello"


@pytest.mark.asyncio
async def test_speaker_is_visible_before_first_model_chunk():
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def events() -> AsyncIterator[Event]:
        waiting.set()
        await release.wait()
        yield TextChunkEvent(content="Bonjour")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(events())
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await asyncio.wait_for(waiting.wait(), timeout=2)
        labels = app.query(RoleLabel)
        assert [
            str(label.content) for label in labels if "assistant" in label.classes
        ] == ["sensai"]
        assert len(app.query(AssistantMessage)) == 0
        release.set()
        await pilot.pause()
        assert app.query(AssistantMessage).first().source == "Bonjour"


@pytest.mark.asyncio
async def test_submitting_input_ignores_non_text_events():
    app = ChatApp(
        _process_events(
            ToolCallEvent(tool_name="fs", arguments={}),
            TextChunkEvent(content="hi"),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert app.query(AssistantMessage).first().source == "hi"


@pytest.mark.asyncio
async def test_blocked_input_mounts_notice_and_no_empty_reply():
    app = ChatApp(
        _process_events(
            GuardrailEvent(
                stage="input", action="block", reason="injection: ignore_instructions"
            )
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        notices = app.query(GuardrailNotice)
        assert len(notices) == 1
        assert "Message blocked" in str(notices.first().content)
        assert "injection: ignore_instructions" in str(notices.first().content)
        assert len(app.query(AssistantMessage)) == 0
        assert len(app.query("RoleLabel.assistant")) == 0


@pytest.mark.asyncio
async def test_masked_reply_shows_text_then_notice():
    app = ChatApp(
        _process_events(
            TextChunkEvent(content="Write to [EMAIL]"),
            GuardrailEvent(stage="output", action="redact", reason="pii: email"),
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert app.query(AssistantMessage).first().source == "Write to [EMAIL]"
        notices = app.query(GuardrailNotice)
        assert len(notices) == 1
        assert "masked" in str(notices.first().content)


@pytest.mark.asyncio
async def test_provider_error_mounts_error_message():
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")

    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        await render(_raising(exc))
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        error_messages = app.query(ErrorMessage)
        assert len(error_messages) == 1
        assert "Connection failed" in str(error_messages.first().content)


@pytest.mark.asyncio
async def test_command_result_is_shown_without_empty_streamed_reply():
    async def process(text: str, render: RenderFn, confirm_tool) -> CommandResult:
        assert text == "/clear"
        return CommandResult(message="Conversation cleared.")

    app = ChatApp(process)
    async with app.run_test() as pilot:
        await pilot.click("Input")
        for char in "/clear":
            await pilot.press(char)
        await pilot.press("enter")
        await pilot.pause()

        replies = app.query(AssistantMessage)
        assert len(replies) == 1
        assert replies.first().source == "Conversation cleared."


def test_error_text_reports_empty_input():
    assert "Empty input" in error_text(EmptyInputError("user_text must not be empty"))


def test_error_text_reports_connection_failure():
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")
    assert "Connection failed" in error_text(exc)


def test_error_text_reports_unavailable_model():
    exc = ProviderError("provider request failed")
    exc.__cause__ = RuntimeError("HTTP Provider Error [404]: model not found")
    assert "Model unavailable" in error_text(exc)


def test_error_text_handles_unknown_exception():
    text = error_text(ValueError("boom"))
    assert "Unexpected error" in text
    assert "boom" in text


@pytest.mark.parametrize(
    "choice, approved",
    [
        ("yes", True),
        ("enter", True),
        ("no", False),
        ("escape", False),
        ("no_enter", False),
    ],
)
async def test_tool_confirmation_returns_choice_and_chat_resumes(choice, approved):
    from textual.widgets import Input

    from sensai.domain.models import ToolCall
    from sensai.interfaces.tui.renderer import ConfirmToolScreen

    decisions = []

    async def process(text, render, confirm_tool):
        decisions.append(
            await confirm_tool(
                ToolCall(name="web_search", arguments={"query": "Sensai"})
            )
        )
        await render(_events(TextChunkEvent(content="Terminé")))
        return CommandResult()

    app = ChatApp(process)
    async with app.run_test() as pilot:
        input_widget = app.query_one(Input)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmToolScreen)
        assert input_widget.disabled
        if choice in {"escape", "enter"}:
            await pilot.press(choice)
        elif choice == "no_enter":
            app.screen.query_one("#no").focus()
            await pilot.press("enter")
        else:
            await pilot.click(f"#{choice}")
        await pilot.pause()
        assert decisions == [approved]
        assert app.query(AssistantMessage).first().source == "Terminé"
        assert not input_widget.disabled
