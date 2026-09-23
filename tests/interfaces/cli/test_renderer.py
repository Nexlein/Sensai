from collections.abc import AsyncIterator

import httpx
from rich.console import Console

from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event, TextChunkEvent, ToolCallEvent
from sensai.interfaces.cli.renderer import error_text, run_chat


async def _events(*items: Event) -> AsyncIterator[Event]:
    for item in items:
        yield item


async def _raising(exc: Exception) -> AsyncIterator[Event]:
    raise exc
    yield  # pragma: no cover


def _run_with_inputs(monkeypatch, send, inputs):
    answers = iter(inputs)

    def fake_input(self, prompt=""):
        try:
            return next(answers)
        except StopIteration as exc:
            raise EOFError from exc

    monkeypatch.setattr(Console, "input", fake_input)
    run_chat(send)


def test_streams_reply_for_each_input(monkeypatch, capsys):
    _run_with_inputs(
        monkeypatch,
        lambda text: _events(
            TextChunkEvent(content="hel"), TextChunkEvent(content="lo")
        ),
        ["hi"],
    )

    out = capsys.readouterr().out
    assert "sensai:" in out
    assert "hello" in out


def test_ignores_non_text_events(monkeypatch, capsys):
    _run_with_inputs(
        monkeypatch,
        lambda text: _events(
            ToolCallEvent(tool_name="fs", arguments={}), TextChunkEvent(content="hi")
        ),
        ["hello"],
    )

    assert "hi" in capsys.readouterr().out


def test_provider_error_is_printed(monkeypatch, capsys):
    exc = ProviderError("provider request failed")
    exc.__cause__ = httpx.ConnectError("connection refused")

    _run_with_inputs(monkeypatch, lambda text: _raising(exc), ["hi"])

    assert "Connection failed" in capsys.readouterr().out


def test_empty_input_error_is_printed(monkeypatch, capsys):
    exc = EmptyInputError("user_text must not be empty")

    _run_with_inputs(monkeypatch, lambda text: _raising(exc), ["hi"])

    assert "Empty input" in capsys.readouterr().out


def test_model_unavailable_error_is_printed(monkeypatch, capsys):
    exc = ProviderError("provider request failed")
    exc.__cause__ = RuntimeError("HTTP Provider Error [404]: model not found")

    _run_with_inputs(monkeypatch, lambda text: _raising(exc), ["hi"])

    assert "Model unavailable" in capsys.readouterr().out


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
