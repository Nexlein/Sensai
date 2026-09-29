from collections.abc import AsyncIterator

import httpx
from rich.console import Console

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import BudgetEvent, Event, TextChunkEvent, ToolCallEvent
from sensai.domain.models import Conversation
from sensai.interfaces.cli.renderer import (
    error_text,
    render_history,
    render_stream,
    usage_text,
)


def test_render_history_prints_prior_messages(capsys):
    console = Console()
    conversation = Conversation()
    conversation.add_message(role="user", content="hello")
    conversation.add_message(role="assistant", content="hi there")

    render_history(console, conversation)

    out = capsys.readouterr().out
    assert "you:" in out
    assert "hello" in out
    assert "sensai:" in out
    assert "hi there" in out


def test_render_history_skips_empty_conversation(capsys):
    console = Console()
    render_history(console, Conversation())

    assert capsys.readouterr().out == ""


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


def test_usage_text_shows_short_counts_and_percent():
    text = usage_text(BudgetEvent(used=4100, max_tokens=8192))

    assert text.plain == "4.1k / 8.2k tokens (50%)"


def test_usage_text_keeps_small_counts_exact():
    text = usage_text(BudgetEvent(used=5, max_tokens=800))

    assert text.plain == "5 / 800 tokens (0%)"


def test_usage_text_can_exceed_full():
    text = usage_text(BudgetEvent(used=1200, max_tokens=1000))

    assert "(120%)" in text.plain


async def test_render_stream_shows_usage_footer(capsys):
    console = Console()
    await render_stream(
        console,
        _events(
            BudgetEvent(used=100, max_tokens=1000),
            TextChunkEvent(content="hi"),
            BudgetEvent(used=101, max_tokens=1000),
        ),
    )

    out = capsys.readouterr().out
    assert "hi" in out
    assert "101 / 1.0k tokens (10%)" in out


async def test_render_stream_footer_shows_before_first_chunk(capsys):
    console = Console()
    await render_stream(console, _events(BudgetEvent(used=100, max_tokens=1000)))

    assert "100 / 1.0k tokens (10%)" in capsys.readouterr().out


async def test_render_stream_without_budget_prints_no_footer(capsys):
    console = Console()
    await render_stream(console, _events(TextChunkEvent(content="hi")))

    assert "tokens" not in capsys.readouterr().out


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
