from collections.abc import AsyncIterator

import pytest

from sensai.core.commands import is_exit_command, run_repl
from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.providers.mock import MockLLMProvider


@pytest.mark.parametrize("text", ["exit", "Exit", "  EXIT  "])
def test_is_exit_command_matches_case_and_whitespace_insensitively(text):
    assert is_exit_command(text)


@pytest.mark.parametrize("text", ["", "hello", "exitnow"])
def test_is_exit_command_rejects_other_input(text):
    assert not is_exit_command(text)


def _engine(response: str = "hi") -> ChatEngine:
    return ChatEngine(MockLLMProvider(default_response=response), Conversation())


async def _drain(events: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in events]


async def test_run_repl_sends_each_line_until_eof():
    inputs = iter(["hello", "world"])
    sent: list[str] = []

    def read_input() -> str:
        try:
            return next(inputs)
        except StopIteration as exc:
            raise EOFError from exc

    async def render(events: AsyncIterator[Event]) -> None:
        sent.append("".join(e.content for e in await _drain(events)))

    errors: list[Exception] = []

    await run_repl(
        _engine(), read_input=read_input, render=render, on_error=errors.append
    )

    assert sent == ["hi", "hi"]
    assert errors == []


async def test_run_repl_stops_on_exit_command():
    inputs = iter(["exit"])
    calls = 0

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        nonlocal calls
        calls += 1

    await run_repl(
        _engine(), read_input=read_input, render=render, on_error=lambda exc: None
    )

    assert calls == 0


async def test_run_repl_stops_on_eof():
    def read_input() -> str:
        raise EOFError

    async def render(events: AsyncIterator[Event]) -> None:
        raise AssertionError("should not be called")

    await run_repl(
        _engine(), read_input=read_input, render=render, on_error=lambda exc: None
    )


async def test_run_repl_reports_empty_input_and_continues():
    inputs = iter(["", "exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(
        _engine(), read_input=read_input, render=render, on_error=errors.append
    )

    assert len(errors) == 1
    assert isinstance(errors[0], EmptyInputError)


async def test_run_repl_reports_provider_error_and_continues():
    class FailingProvider:
        async def chat_stream(self, messages, tools=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    engine = ChatEngine(FailingProvider(), Conversation())
    inputs = iter(["hi", "exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(engine, read_input=read_input, render=render, on_error=errors.append)

    assert len(errors) == 1
    assert isinstance(errors[0], ProviderError)
