from collections.abc import AsyncIterator

import httpx
from rich.console import Console

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.interfaces.cli.renderer import error_text, render_stream


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def test_render_stream_prints_text_chunks(capsys):
    console = Console()
    await render_stream(
        console, _events(TextChunkEvent(content="hel"), TextChunkEvent(content="lo"))
    )

    out = capsys.readouterr().out
    assert "sensai:" in out
    assert "hello" in out


async def test_render_stream_ignores_non_text_events(capsys):
    console = Console()
    await render_stream(
        console,
        _events(
            ToolCallEvent(tool_name="fs", arguments={}), TextChunkEvent(content="hi")
        ),
    )

    assert "hi" in capsys.readouterr().out


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
