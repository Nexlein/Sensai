from collections.abc import AsyncIterator

import httpx
import pytest

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.interfaces.tui.renderer import (
    AssistantMessage,
    ChatApp,
    ErrorMessage,
    UserMessage,
    error_text,
)


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def _raising(exc: Exception) -> AsyncIterator[Event]:
    raise exc
    yield  # pragma: no cover


@pytest.mark.asyncio
async def test_submitting_input_mounts_user_message_and_streamed_reply():
    app = ChatApp(
        lambda text: _events(
            TextChunkEvent(content="hel"), TextChunkEvent(content="lo")
        )
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


@pytest.mark.asyncio
async def test_submitting_input_ignores_non_text_events():
    app = ChatApp(
        lambda text: _events(
            ToolCallEvent(tool_name="fs", arguments={}), TextChunkEvent(content="hi")
        )
    )

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        assert len(app.query(AssistantMessage)) == 1


@pytest.mark.asyncio
async def test_provider_error_mounts_error_message():
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")
    app = ChatApp(lambda text: _raising(exc))

    async with app.run_test() as pilot:
        await pilot.click("Input")
        await pilot.press("enter")
        await pilot.pause()

        error_messages = app.query(ErrorMessage)
        assert len(error_messages) == 1
        assert "Connection failed" in str(error_messages.first().content)


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
