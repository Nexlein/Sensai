from collections.abc import AsyncIterator

import pytest

from sensai.core.commands import (
    CommandContext,
    ParsedCommand,
    dispatch_command,
    parse_commands,
    run_repl,
)
from sensai.core.config import AppConfig
from sensai.core.engine import ChatEngine
from sensai.domain.errors import EmptyInputError, ProviderError
from sensai.domain.events import Event
from sensai.domain.models import Conversation
from sensai.providers.mock import MockLLMProvider


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", None),
        ("exit", None),
        ("hello /exit", None),
        ("/", None),
        ("/help", ParsedCommand(name="help", arguments=())),
        ("  /EXIT  ", ParsedCommand(name="exit", arguments=())),
        (
            "/config set model llama3.2",
            ParsedCommand(name="config", arguments=("set", "model", "llama3.2")),
        ),
    ],
)
def test_parse_commands(text, expected):
    assert parse_commands(text) == expected


def _engine(response: str = "hi") -> ChatEngine:
    return ChatEngine(MockLLMProvider(default_response=response), Conversation())


def _context(response: str = "hi", output: list[str] | None = None) -> CommandContext:
    messages = output if output is not None else []
    return CommandContext(
        config=AppConfig(),
        engine=_engine(response),
        output=messages.append,
    )


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
        _context(), read_input=read_input, render=render, on_error=errors.append
    )

    assert sent == ["hi", "hi"]
    assert errors == []


async def test_run_repl_treats_bare_exit_as_chat_message():
    inputs = iter(["exit", "/exit"])
    rendered: list[str] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        rendered.append("".join(e.content for e in await _drain(events)))

    await run_repl(
        _context(),
        read_input=read_input,
        render=render,
        on_error=lambda exc: None,
    )

    assert rendered == ["hi"]


async def test_run_repl_stops_on_slash_exit_command():
    inputs = iter(["/exit"])
    calls = 0

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        nonlocal calls
        calls += 1

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=lambda exc: None
    )

    assert calls == 0


async def test_run_repl_stops_on_eof():
    def read_input() -> str:
        raise EOFError

    async def render(events: AsyncIterator[Event]) -> None:
        raise AssertionError("should not be called")

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=lambda exc: None
    )


async def test_run_repl_reports_empty_input_and_continues():
    inputs = iter(["", "/exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(
        _context(), read_input=read_input, render=render, on_error=errors.append
    )

    assert len(errors) == 1
    assert isinstance(errors[0], EmptyInputError)


async def test_run_repl_reports_provider_error_and_continues():
    class FailingProvider:
        async def chat_stream(self, messages, tools=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    engine = ChatEngine(FailingProvider(), Conversation())
    context = CommandContext(
        config=AppConfig(),
        engine=engine,
        output=lambda _: None,
    )
    inputs = iter(["hi", "/exit"])
    errors: list[Exception] = []

    def read_input() -> str:
        return next(inputs)

    async def render(events: AsyncIterator[Event]) -> None:
        async for _ in events:
            pass

    await run_repl(
        context, read_input=read_input, render=render, on_error=errors.append
    )

    assert len(errors) == 1
    assert isinstance(errors[0], ProviderError)


async def test_dispatch_exit_requests_repl_exit():
    should_exit = await dispatch_command(
        ParsedCommand(name="exit", arguments=()),
        _context(),
    )

    assert should_exit


async def test_dispatch_unknown_command_reports_error_and_continues():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="unknown", arguments=()),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Unknown command: /unknown"]


async def test_dispatch_clear_empties_current_conversation():
    output: list[str] = []
    context = _context(output=output)
    context.engine.conversation.add_message(role="user", content="hello")

    should_exit = await dispatch_command(
        ParsedCommand(name="clear", arguments=()),
        context,
    )

    assert not should_exit
    assert context.engine.conversation.messages == []
    assert output == ["Conversation cleared."]


async def test_dispatch_help_lists_commands():
    output: list[str] = []

    should_exit = await dispatch_command(
        ParsedCommand(name="help", arguments=()),
        _context(output=output),
    )

    assert not should_exit
    assert output == ["Available commands: /exit, /help, /clear"]
